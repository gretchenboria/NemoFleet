import os
import sys
import time
import argparse
from pathlib import Path
from openai import OpenAI

OUTPUT_DIR = Path(__file__).parent / "model_files_v2"

def resolve_api_key(passed_key: str = None) -> str:
    """Resolve Nebius Token Factory API key prioritizing .env file."""
    if passed_key:
        return passed_key

    # 1. Check local .env file
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        import re
        with open(env_file) as f:
            content = f.read()
            m = re.search(r"NEBIUS_API_KEY_TOKEN_FACTORY=([^\s]+)", content)
            if m:
                return m.group(1).strip("\"'")
            m = re.search(r"NEBIUS_API_KEY=([^\s]+)", content)
            if m:
                return m.group(1).strip("\"'")

    # 2. Check process environment
    if os.environ.get("NEBIUS_API_KEY_TOKEN_FACTORY"):
        return os.environ["NEBIUS_API_KEY_TOKEN_FACTORY"]
    if os.environ.get("NEBIUS_API_KEY"):
        return os.environ["NEBIUS_API_KEY"]

    # 3. Check ~/.zshrc
    zshrc = Path.home() / ".zshrc"
    if zshrc.exists():
        import re
        with open(zshrc) as f:
            content = f.read()
            m = re.search(r"export NEBIUS_API_KEY_TOKEN_FACTORY=([^\s]+)", content) or re.search(r"export NEBIUS_API_KEY=([^\s]+)", content)
            if m:
                return m.group(1).strip("\"'")

    return ""

import yaml

def load_yaml_config(config_path: Path) -> dict:
    if config_path and config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def main():
    parser = argparse.ArgumentParser(description="Launch Nebius Token Factory Fine-Tuning Job from YAML Config")
    parser.add_argument("--config", "-c", type=str, default="configs/default.yaml", help="Path to run YAML configuration (default: configs/default.yaml)")
    parser.add_argument("--api_key", type=str, default=None, help="Nebius API key (defaults to .env)")
    parser.add_argument("--train-data", type=str, default=None, help="Override training dataset path")
    parser.add_argument("--val-data", type=str, default=None, help="Override validation dataset path")
    parser.add_argument("--model", type=str, default=None, help="Override base model")
    parser.add_argument("--suffix", type=str, default=None, help="Override custom model suffix")
    parser.add_argument("--lr", type=float, default=None, help="Override learning rate")
    parser.add_argument("--batch-size", type=int, default=None, help="Override batch size")
    parser.add_argument("--epochs", type=int, default=None, help="Override training epochs")
    parser.add_argument("--r", type=int, default=None, help="Override LoRA rank r")
    parser.add_argument("--alpha", type=int, default=None, help="Override LoRA alpha")
    parser.add_argument("--dropout", type=float, default=None, help="Override LoRA dropout")
    parser.add_argument("--context-length", type=int, default=None, help="Override context length")
    parser.add_argument("--no-packing", action="store_true", help="Disable sequence packing")
    parser.add_argument("--no-wait", action="store_true", help="Submit job and exit without waiting for completion")
    args = parser.parse_args()

    # 1. Load Base Config from YAML
    config_file = Path(args.config) if args.config else None
    if config_file and not config_file.is_absolute():
        config_file = Path(__file__).parent / config_file

    cfg = load_yaml_config(config_file) if (config_file and config_file.exists()) else {}
    run_cfg = cfg.get("run", {})
    hp_cfg = cfg.get("hyperparameters", {})
    lora_cfg = cfg.get("lora", {})

    # 2. Resolve Parameters (CLI flags override YAML)
    model_name = args.model or run_cfg.get("model", "unsloth/gpt-oss-20b-BF16")
    suffix_name = args.suffix or run_cfg.get("name", "openorca-lora-v1")
    train_data_str = args.train_data or run_cfg.get("train_data", "openorca_train.jsonl")
    val_data_str = args.val_data or run_cfg.get("val_data", "openorca_val.jsonl")
    seed_val = run_cfg.get("seed", 42)

    learning_rate = args.lr if args.lr is not None else float(hp_cfg.get("learning_rate", 3e-5))
    batch_size = args.batch_size if args.batch_size is not None else int(hp_cfg.get("batch_size", 4))
    epochs = args.epochs if args.epochs is not None else int(hp_cfg.get("n_epochs", 3))
    warmup_ratio = float(hp_cfg.get("warmup_ratio", 0.05))
    weight_decay = float(hp_cfg.get("weight_decay", 0.01))
    max_grad_norm = float(hp_cfg.get("max_grad_norm", 1.0))
    context_length = args.context_length if args.context_length is not None else int(hp_cfg.get("context_length", 4096))
    packing_val = False if args.no_packing else bool(hp_cfg.get("packing", True))

    lora_r = args.r if args.r is not None else int(lora_cfg.get("r", 16))
    lora_alpha = args.alpha if args.alpha is not None else int(lora_cfg.get("alpha", 32))
    lora_dropout = args.dropout if args.dropout is not None else float(lora_cfg.get("dropout", 0.05))

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print("❌ Error: NEBIUS_API_KEY_TOKEN_FACTORY is not set.")
        print("Please ensure NEBIUS_API_KEY_TOKEN_FACTORY is set in .env or pass --api_key <key>")
        sys.exit(1)

    train_path = Path(train_data_str)
    if not train_path.is_absolute():
        train_path = Path(__file__).parent / train_path

    if not train_path.exists():
        print(f"❌ Error: Training file not found at {train_path}")
        print("Run `uv run python prepare_openorca.py` first to generate datasets.")
        sys.exit(1)

    val_path = None
    if val_data_str:
        val_candidate = Path(val_data_str)
        if not val_candidate.is_absolute():
            val_candidate = Path(__file__).parent / val_candidate
        if val_candidate.exists():
            val_path = val_candidate

    print("================================================================================")
    print("🚀 Nebius Token Factory — Fine-Tuning Execution")
    print("================================================================================")
    print(f"📄 Config File:  {config_file.name if config_file else 'None (CLI defaults)'}")
    print(f"📡 API Base URL: https://api.tokenfactory.nebius.com/v1/")
    print(f"🔑 Key Origin:   .env (Jobs Account: {api_key[:10]}...{api_key[-4:]})")
    print(f"📦 Base Model:   {model_name}")
    print(f"🏷️ Run Name:     {suffix_name}")
    print("--------------------------------------------------------------------------------")

    client = OpenAI(
        base_url="https://api.tokenfactory.nebius.com/v1/",
        api_key=api_key,
    )

    print(f"📤 Uploading training data: {train_path.name} ({train_path.stat().st_size / 1024:.1f} KB)...")
    with open(train_path, "rb") as f:
        train_file_obj = client.files.create(file=f, purpose="fine-tune")
    print(f"✅ Training File ID: {train_file_obj.id}")

    val_file_id = None
    if val_path:
        print(f"📤 Uploading validation data: {val_path.name} ({val_path.stat().st_size / 1024:.1f} KB)...")
        with open(val_path, "rb") as f:
            val_file_obj = client.files.create(file=f, purpose="fine-tune")
        val_file_id = val_file_obj.id
        print(f"✅ Validation File ID: {val_file_id}")

    hyperparameters = {
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "n_epochs": epochs,
        "warmup_ratio": warmup_ratio,
        "weight_decay": weight_decay,
        "lora": True,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "lora_dropout": lora_dropout,
        "packing": packing_val,
        "max_grad_norm": max_grad_norm,
        "context_length": context_length,
    }

    job_request = {
        "model": model_name,
        "training_file": train_file_obj.id,
        "suffix": suffix_name,
        "hyperparameters": hyperparameters,
        "seed": seed_val,
    }
    if val_file_id:
        job_request["validation_file"] = val_file_id

    # Create local snapshot of finalized config artifact
    artifact_config = {
        "run": {
            "name": suffix_name,
            "model": model_name,
            "train_data": str(train_path),
            "val_data": str(val_path) if val_path else None,
            "seed": seed_val,
            "source_config_file": str(config_file) if config_file else "cli",
        },
        "hyperparameters": hyperparameters,
        "lora": {
            "enabled": True,
            "r": lora_r,
            "alpha": lora_alpha,
            "dropout": lora_dropout,
        }
    }

    print("\n⚙️ Resolved Hyperparameters & Run Config:")
    for k, v in hyperparameters.items():
        print(f"   • {k:16s}: {v}")

    print("\n🚀 Submitting fine-tuning job...")
    job = client.fine_tuning.jobs.create(**job_request)
    print(f"✅ Job Created! ID: {job.id}")
    print(f"📊 Status: {job.status}")

    if args.no_wait:
        print("\n👋 Non-blocking mode requested. You can monitor the job with:")
        print(f"   uv run python fetch_checkpoint.py --list")
        return

    ACTIVE_STATUSES = ["validating_files", "queued", "running"]
    POLL_INTERVAL_SECONDS = 15

    print("\n⏳ Polling job progress (every 15s)...")
    last_status = None

    while job.status in ACTIVE_STATUSES:
        if job.status != last_status:
            print(f"[{time.strftime('%H:%M:%S')}] Status: {job.status.upper()}")
            last_status = job.status
        
        time.sleep(POLL_INTERVAL_SECONDS)
        try:
            job = client.fine_tuning.jobs.retrieve(job.id)
        except Exception as e:
            print(f"⚠️ Polling retry: {e}")

    print(f"\n🏁 Final Job Status: {job.status.upper()}")
    
    if job.status == "failed":
        print(f"❌ Job failed with error: {getattr(job, 'error', 'Unknown error')}")
        sys.exit(1)

    # Print events
    try:
        events = client.fine_tuning.jobs.list_events(job.id)
        print("\n📜 Training Events & Checkpoint History:")
        for event in events.data:
            print(f"   [{event.created_at}] {event.level}: {event.message}")
    except Exception as e:
        print(f"Note: Could not fetch events: {e}")

    # Download checkpoints & Record Experiment
    if job.status == "succeeded":
        print(f"\n📦 Downloading Checkpoints...")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        cps_data = []
        try:
            checkpoints = client.fine_tuning.jobs.checkpoints.list(job.id).data
            for cp in checkpoints:
                step_str = f"Step {cp.step_number}" if hasattr(cp, 'step_number') and cp.step_number else ""
                print(f" -> Checkpoint: {cp.id} ({step_str})")
                cp_dir = OUTPUT_DIR / cp.id
                cp_dir.mkdir(parents=True, exist_ok=True)
                
                m = getattr(cp, "metrics", None)
                train_loss = getattr(m, "train_loss", None) if m else None
                valid_loss = getattr(m, "valid_loss", None) if m else None
                train_acc = getattr(m, "train_mean_token_accuracy", None) if m else None
                valid_acc = getattr(m, "valid_mean_token_accuracy", None) if m else None

                cps_data.append({
                    "id": cp.id,
                    "step_number": getattr(cp, "step_number", None),
                    "train_loss": train_loss,
                    "valid_loss": valid_loss,
                    "train_mean_token_accuracy": train_acc,
                    "valid_mean_token_accuracy": valid_acc,
                })

                for file_id in getattr(cp, "result_files", []):
                    file_obj = client.files.retrieve(file_id)
                    filename = Path(file_obj.filename).name
                    output_file = cp_dir / filename
                    print(f"    📥 Downloading {filename}...")
                    file_content = client.files.content(file_id)
                    file_content.write_to_file(str(output_file))
            print(f"\n🎉 All checkpoints successfully downloaded to: {OUTPUT_DIR}/")

            # Save immutable config artifact
            config_artifact_dir = Path(__file__).parent / "experiments" / "configs"
            config_artifact_dir.mkdir(parents=True, exist_ok=True)
            saved_config_path = config_artifact_dir / f"{job.id}_{suffix_name}.yaml"
            with open(saved_config_path, "w", encoding="utf-8") as f:
                yaml.dump(artifact_config, f, default_flow_style=False, sort_keys=False)
            print(f"📄 Saved Run Config Artifact: {saved_config_path}")

            # Also copy config.yaml inside each checkpoint directory
            for cp in cps_data:
                cp_cfg_path = OUTPUT_DIR / cp["id"] / "config.yaml"
                if (OUTPUT_DIR / cp["id"]).exists():
                    with open(cp_cfg_path, "w", encoding="utf-8") as f:
                        yaml.dump(artifact_config, f, default_flow_style=False, sort_keys=False)

            # Local Experiment Tracking (MLflow + JSONL)
            try:
                from track_experiments import record_local_run, log_experiment_to_mlflow, print_terminal_dashboard
                run_entry = {
                    "job_id": job.id,
                    "status": job.status,
                    "model": model_name,
                    "suffix": suffix_name,
                    "created_at": getattr(job, "created_at", None),
                    "hyperparameters": hyperparameters,
                    "checkpoints": cps_data,
                    "config_path": str(saved_config_path),
                }
                record_local_run(run_entry)
                log_experiment_to_mlflow(
                    run_name=suffix_name,
                    params={**hyperparameters, "model": model_name, "job_id": job.id},
                    checkpoints_metrics=cps_data,
                    eval_summary=str(saved_config_path)
                )
                print_terminal_dashboard()
            except Exception as e:
                print(f"⚠️ Notice logging to tracker: {e}")

            if checkpoints:
                latest_ckpt = checkpoints[-1].id
                print("\n🚀 Ready for Ephemeral Eval! Deploy with:")
                print(f"   ./launch_vm.sh {latest_ckpt}")
        except Exception as e:
            print(f"⚠️ Warning downloading checkpoints: {e}")

if __name__ == "__main__":
    main()
