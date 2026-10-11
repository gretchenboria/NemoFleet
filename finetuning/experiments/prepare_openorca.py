import json
import argparse
from pathlib import Path
from datasets import load_dataset

def prepare_openorca(
    sample_count: int = 3000,
    val_count: int = 200,
    output_dir: str = ".",
    dataset_name: str = "Open-Orca/SlimOrca",
    min_response_len: int = 30,
    max_response_len: int = 4000
):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    train_file = output_path / "openorca_train.jsonl"
    val_file = output_path / "openorca_val.jsonl"

    print(f"📥 Streaming dataset '{dataset_name}' from Hugging Face...")
    ds = load_dataset(dataset_name, split="train", streaming=True)

    train_data = []
    val_data = []
    total_target = sample_count + val_count

    print(f"🎯 Target: {sample_count} training samples + {val_count} validation samples")

    for i, item in enumerate(ds):
        if len(train_data) + len(val_data) >= total_target:
            break

        convs = item.get("conversations", [])
        if not convs:
            continue

        messages = []
        valid_turn = True
        
        for turn in convs:
            role_raw = turn.get("from", "").lower()
            content = turn.get("value", "").strip()

            if not content:
                valid_turn = False
                break

            if role_raw in ["system"]:
                role = "system"
            elif role_raw in ["human", "user"]:
                role = "user"
            elif role_raw in ["gpt", "assistant", "agent"]:
                role = "assistant"
            else:
                role = "user"

            messages.append({"role": role, "content": content})

        if not valid_turn or len(messages) < 2:
            continue

        # Length & quality filters
        last_asst = [m for m in messages if m["role"] == "assistant"]
        if not last_asst or len(last_asst[-1]["content"]) < min_response_len:
            continue
        if len(last_asst[-1]["content"]) > max_response_len:
            continue

        # Strict total conversation length filter to guarantee < 8192 tokens
        total_chars = sum(len(m["content"]) for m in messages)
        total_words = sum(len(m["content"].split()) for m in messages)
        if total_chars > 12000 or total_words > 2500:
            continue

        sample_obj = {"messages": messages}

        if len(val_data) < val_count and (i % (total_target // max(val_count, 1)) == 0):
            val_data.append(sample_obj)
        elif len(train_data) < sample_count:
            train_data.append(sample_obj)
        else:
            val_data.append(sample_obj)

    # Save training file
    with open(train_file, "w", encoding="utf-8") as f:
        for entry in train_data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Save validation file
    with open(val_file, "w", encoding="utf-8") as f:
        for entry in val_data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n✅ Dataset Preparation Complete:")
    print(f"   • Train: {train_file} ({len(train_data)} samples, {train_file.stat().st_size / 1024:.1f} KB)")
    print(f"   • Val:   {val_file} ({len(val_data)} samples, {val_file.stat().st_size / 1024:.1f} KB)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare OpenOrca dataset for Nebius Token Factory fine-tuning")
    parser.add_argument("--samples", type=int, default=2500, help="Number of training samples (default: 2500)")
    parser.add_argument("--val-samples", type=int, default=200, help="Number of validation samples (default: 200)")
    parser.add_argument("--dataset", type=str, default="Open-Orca/SlimOrca", help="HuggingFace dataset repo")
    parser.add_argument("--outdir", type=str, default=".", help="Output directory")
    args = parser.parse_args()

    prepare_openorca(
        sample_count=args.samples,
        val_count=args.val_samples,
        output_dir=args.outdir,
        dataset_name=args.dataset
    )
