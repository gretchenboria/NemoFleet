import os
import sys
import json
import shutil
import argparse
import torch
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

MODEL_DIR = Path(__file__).parent / "model_files"

def ensure_adapter_file(model_dir: Path):
    """Ensure adapter_model.safetensors exists if downloaded as adapter_model (1).safetensors"""
    standard_file = model_dir / "adapter_model.safetensors"
    download_dup = model_dir / "adapter_model (1).safetensors"
    
    if not standard_file.exists() and download_dup.exists():
        print(f"Renaming '{download_dup.name}' to '{standard_file.name}' for PEFT compatibility...")
        shutil.copy(download_dup, standard_file)

def get_base_model_path(model_dir: Path, default: str = "unsloth/gpt-oss-20b-BF16") -> str:
    config_path = model_dir / "adapter_config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("base_model_name_or_path", default)
    return default

def generate_response(model, tokenizer, prompt_text: str, max_new_tokens: int = 512, force_final_channel: bool = False) -> tuple[str, str]:
    messages = [
        {"role": "user", "content": prompt_text}
    ]
    if hasattr(tokenizer, "apply_chat_template"):
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        if force_final_channel:
            # Force the model directly into final answer channel for gpt-oss models
            prompt += "<|channel|>final<|message|>"
    else:
        prompt = f"User: {prompt_text}\nAssistant: "

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    # Stop tokens for gpt-oss and llama-3
    stop_tokens = ["<|eot_id|>", "<|end_of_text|>", "<|end|>", "<|return|>", "<|call|>", "<|endoftext|>"]
    eos_token_ids = [tokenizer.eos_token_id] if tokenizer.eos_token_id is not None else []
    for st in stop_tokens:
        tok_id = tokenizer.convert_tokens_to_ids(st)
        if tok_id is not None and tok_id != tokenizer.unk_token_id and tok_id not in eos_token_ids:
            eos_token_ids.append(tok_id)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.1,
            do_sample=True,
            pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id,
            eos_token_id=eos_token_ids,
        )

    generated_tokens = outputs[0][inputs["input_ids"].shape[-1]:]
    raw_output = tokenizer.decode(generated_tokens, skip_special_tokens=False)

    # Clean channel markers and stop tokens
    cleaned = raw_output
    if "<|channel|>final<|message|>" in cleaned:
        cleaned = cleaned.split("<|channel|>final<|message|>")[-1]
    for tag in ["<|begin_of_text|>", "<|eot_id|>", "<|end_of_text|>", "<|start_header_id|>", "<|end_header_id|>", "<|start|>", "<|end|>", "<|return|>", "<|call|>", "<|message|>", "<|channel|>analysis", "<|channel|>final", "<|channel|>commentary", "<|endoftext|>"]:
        cleaned = cleaned.replace(tag, "")
    cleaned = cleaned.strip()

    return cleaned, raw_output

def find_latest_checkpoint() -> Path:
    base_v2 = Path(__file__).parent / "model_files_v2"
    if base_v2.exists():
        ckpts = [d for d in base_v2.glob("ftckpt_*") if d.is_dir()]
        if ckpts:
            # Sort by checkpoint.meta step_number or mtime
            def get_step(d):
                meta = d / "checkpoint.meta"
                if meta.exists():
                    try:
                        with open(meta) as f:
                            return json.load(f).get("step_number", 0)
                    except Exception:
                        pass
                return d.stat().st_mtime
            ckpts.sort(key=get_step, reverse=True)
            return ckpts[0]
    return Path(__file__).parent / "model_files"

def main():
    parser = argparse.ArgumentParser(description="Test fine-tuned LoRA model")
    parser.add_argument("--model_dir", type=str, default=None, help="Directory containing LoRA checkpoint")
    parser.add_argument("--prompt", type=str, default=None, help="Single prompt to evaluate non-interactively")
    parser.add_argument("--max_tokens", type=int, default=256, help="Maximum new tokens to generate")
    parser.add_argument("--base_only", action="store_true", help="Run base model without LoRA adapter to compare")
    parser.add_argument("--skip_cot", action="store_true", help="Skip thinking channel and force final channel")
    parser.add_argument("--show_raw", action="store_true", help="Display raw output including special tokens (<|channel|>, etc.)")
    parser.add_argument("--load_in_4bit", action="store_true", help="Load base model in 4-bit precision (BitsAndBytes)")
    parser.add_argument("--load_in_8bit", action="store_true", help="Load base model in 8-bit precision (BitsAndBytes)")
    args = parser.parse_args()

    if args.model_dir:
        p = Path(args.model_dir)
        if not p.is_absolute():
            # Check direct relative path, then model_files_v2/<name>, then model_files/<name>
            if (Path(__file__).parent / p).exists():
                model_dir = Path(__file__).parent / p
            elif (Path(__file__).parent / "model_files_v2" / p).exists():
                model_dir = Path(__file__).parent / "model_files_v2" / p
            else:
                model_dir = Path(__file__).parent / p
        else:
            model_dir = p
    else:
        model_dir = find_latest_checkpoint()

    ensure_adapter_file(model_dir)
    
    base_model_id = get_base_model_path(model_dir)
    print(f"Loading Base Model: {base_model_id}")
    print(f"Loading Adapter from: {model_dir}")

    # Determine device and dtype
    quantization_kwargs = {}
    if args.load_in_4bit:
        print("Using 4-bit Quantization (bitsandbytes)")
        quantization_kwargs["load_in_4bit"] = True
    elif args.load_in_8bit:
        print("Using 8-bit Quantization (bitsandbytes)")
        quantization_kwargs["load_in_8bit"] = True
    elif torch.cuda.is_available() and "70b" in base_model_id.lower():
        # Check if single GPU has < 120GB VRAM (e.g. single 80GB H100/A100)
        gpu_count = torch.cuda.device_count()
        total_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        if gpu_count == 1 and total_vram_gb < 120:
            print(f"Detected single GPU with {total_vram_gb:.1f} GB VRAM for 70B model -> auto-enabling 4-bit quantization")
            quantization_kwargs["load_in_4bit"] = True

    if torch.cuda.is_available():
        device_map = "auto"
        torch_dtype = torch.bfloat16
    elif torch.backends.mps.is_available():
        device_map = "mps"
        torch_dtype = torch.float16
    else:
        device_map = "cpu"
        torch_dtype = torch.float32

    print(f"Using device_map: {device_map}, dtype: {torch_dtype}")

    # Retrieve Hugging Face token if available
    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not hf_token:
        hf_cache_token = Path.home() / ".cache" / "huggingface" / "token"
        if hf_cache_token.exists():
            try:
                with open(hf_cache_token) as f:
                    hf_token = f.read().strip()
            except Exception:
                pass

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        str(model_dir),
        token=hf_token,
        trust_remote_code=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load base model
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        token=hf_token,
        torch_dtype=torch_dtype,
        device_map=device_map,
        trust_remote_code=True,
        **quantization_kwargs
    )

    if args.base_only:
        print("\n Running Base Model ONLY (LoRA disabled)\n")
        model = base_model
    else:
        # Load LoRA adapter
        print(f"\n Attaching LoRA adapter from {model_dir}...")
        model = PeftModel.from_pretrained(base_model, str(model_dir))
        print(" LoRA adapter attached successfully!\n")

    model.eval()

    RESULTS_DIR = Path(__file__).parent / "eval_results"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = RESULTS_DIR / "eval_log.jsonl"
    REPORT_FILE = RESULTS_DIR / "latest_run.md"

    def log_evaluation(prompt: str, response: str, raw: str):
        import time
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "checkpoint": str(model_dir.name),
            "base_only": args.base_only,
            "prompt": prompt,
            "response": response,
            "raw": raw,
        }
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        with open(REPORT_FILE, "a", encoding="utf-8") as f:
            f.write(f"### [{entry['timestamp']}] Model: `{entry['checkpoint']}` (Base only: {args.base_only})\n\n")
            f.write(f"**Prompt:**\n> {prompt}\n\n")
            f.write(f"**Response:**\n{response}\n\n---\n\n")

    def print_result(prompt: str, cleaned: str, raw: str):
        if args.show_raw:
            print(f"\n--- Raw Output (with special tokens) ---\n{raw}\n---------------------------------------")
        print(f"\nResponse:\n{cleaned}\n")
        log_evaluation(prompt, cleaned, raw)

    # If prompt passed via CLI
    if args.prompt:
        print(f"Prompt: {args.prompt}")
        cleaned, raw = generate_response(model, tokenizer, args.prompt, max_new_tokens=args.max_tokens, force_final_channel=True)
        print_result(args.prompt, cleaned, raw)
        return

    # If running non-interactively without TTY, run default test samples
    if not sys.stdin.isatty():
        sample_prompts = [
            "Explain quantum computing in simple terms.",
            "What is a programming language?"
        ]
        print("Running non-interactive test samples:")
        for sp in sample_prompts:
            print(f"\n=== Testing Prompt: '{sp}' ===")
            cleaned, raw = generate_response(model, tokenizer, sp, max_new_tokens=args.max_tokens, force_final_channel=True)
            print_result(sp, cleaned, raw)
        return

    # Interactive prompt loop
    print("Interactive Mode: Enter your prompt (or type 'exit' / 'quit' to exit):")
    while True:
        try:
            user_input = input("\nUser: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        cleaned, raw = generate_response(model, tokenizer, user_input, max_new_tokens=args.max_tokens, force_final_channel=True)
        print(f"\nAssistant: {cleaned}")
        if args.show_raw:
            print(f"[Raw]: {raw}")
        log_evaluation(user_input, cleaned, raw)

if __name__ == "__main__":
    main()
