import os
import sys
import re
import json
import argparse
from pathlib import Path
from openai import OpenAI

OUTPUT_DIR = Path(__file__).parent / "model_files_v2"

def get_jobs_api_key() -> str:
    """Read API key from .env (fine-tuning jobs / Token Factory account)"""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            content = f.read()
            m = re.search(r"NEBIUS_API_KEY_TOKEN_FACTORY=([^\s]+)", content)
            if m:
                return m.group(1).strip("\"'")
            m = re.search(r"NEBIUS_API_KEY=([^\s]+)", content)
            if m:
                return m.group(1).strip("\"'")
    key = os.environ.get("NEBIUS_API_KEY_TOKEN_FACTORY") or os.environ.get("NEBIUS_API_KEY")
    if key:
        return key
    print("❌ Error: NEBIUS_API_KEY_TOKEN_FACTORY (or NEBIUS_API_KEY) not found in .env")
    sys.exit(1)

def get_client() -> OpenAI:
    api_key = get_jobs_api_key()
    return OpenAI(
        base_url="https://api.tokenfactory.nebius.com/v1/",
        api_key=api_key,
    )

def download_checkpoint_files(client: OpenAI, cp, target_dir: Path):
    target_dir.mkdir(parents=True, exist_ok=True)
    step = getattr(cp, "step_number", getattr(cp, "step", "N/A"))
    print(f"📦 Downloading Checkpoint: {cp.id} (Step: {step}) -> {target_dir}")
    
    # Save checkpoint metadata
    metrics_data = {}
    if hasattr(cp, "metrics") and cp.metrics is not None:
        if hasattr(cp.metrics, "model_dump"):
            metrics_data = cp.metrics.model_dump()
        elif hasattr(cp.metrics, "dict"):
            metrics_data = cp.metrics.dict()
        elif isinstance(cp.metrics, dict):
            metrics_data = cp.metrics
        else:
            metrics_data = str(cp.metrics)

    meta = {
        "id": cp.id,
        "created_at": getattr(cp, "created_at", None),
        "metrics": metrics_data,
        "step_number": step
    }
    with open(target_dir / "checkpoint.meta", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)

    result_files = getattr(cp, "result_files", [])
    if not result_files:
        print(f"⚠️ No result files found in checkpoint object {cp.id}")
        return

    for file_id in result_files:
        try:
            file_obj = client.files.retrieve(file_id)
            filename = Path(file_obj.filename).name
            output_file = target_dir / filename
            if output_file.exists() and output_file.stat().st_size > 0:
                print(f"   ✓ {filename} (already downloaded)")
                continue
            print(f"   ⬇️ Downloading {filename}...")
            file_content = client.files.content(file_id)
            file_content.write_to_file(str(output_file))
        except Exception as e:
            print(f"   ❌ Error downloading file {file_id}: {e}")

    print(f"✅ Checkpoint {cp.id} ready at: {target_dir}\n")

def list_all(client: OpenAI):
    print("📋 Fetching fine-tuning jobs and checkpoints from Token Factory...\n")
    jobs = client.fine_tuning.jobs.list(limit=50).data
    found_ckpts = set()
    for j in jobs:
        print(f"Job: {j.id} | Status: {j.status} | Model: {j.model} | Created: {getattr(j, 'created_at', 'N/A')}")
        if j.status == "succeeded":
            try:
                ckpts = client.fine_tuning.jobs.checkpoints.list(j.id, limit=50).data
                for cp in ckpts:
                    found_ckpts.add(cp.id)
                    step = getattr(cp, "step_number", "N/A")
                    metrics = getattr(cp, "metrics", {})
                    loss = metrics.get("train_loss", "N/A") if isinstance(metrics, dict) else "N/A"
                    print(f"   └─ Checkpoint: {cp.id} | Step: {step} | Train Loss: {loss}")
            except Exception as e:
                print(f"   └─ Error fetching checkpoints: {e}")
        print()

    # Also check file storage for standalone / archived checkpoints
    try:
        files = client.files.list(limit=1000).data
        storage_ckpts = {}
        for f in files:
            m = re.match(r"(ftckpt_[^/]+)/(.*)", f.filename)
            if m:
                cid, fname = m.group(1), m.group(2)
                storage_ckpts.setdefault(cid, []).append((f.id, fname))

        archived = [cid for cid in storage_ckpts if cid not in found_ckpts]
        if archived:
            print("📦 Additional Checkpoints in File Storage:")
            for cid in sorted(archived):
                file_count = len(storage_ckpts[cid])
                print(f"   └─ {cid} ({file_count} files stored)")
            print()
    except Exception as e:
        print(f"Note: Could not inspect file storage: {e}")

def fetch_specific_checkpoint(client: OpenAI, checkpoint_id: str) -> Path:
    target_dir = OUTPUT_DIR / checkpoint_id
    
    # 1. Search across recent fine-tuning jobs
    try:
        jobs = client.fine_tuning.jobs.list(limit=50).data
        for j in jobs:
            if j.status != "succeeded":
                continue
            try:
                ckpts = client.fine_tuning.jobs.checkpoints.list(j.id, limit=50).data
                for cp in ckpts:
                    if cp.id == checkpoint_id:
                        download_checkpoint_files(client, cp, target_dir)
                        return target_dir
            except Exception:
                pass
    except Exception as e:
        print(f"⚠️ Error checking jobs: {e}")

    # 2. Fallback: Search directly in file storage by checkpoint ID prefix
    print(f"🔍 Searching file storage for checkpoint '{checkpoint_id}'...")
    try:
        files = client.files.list(limit=1000).data
        matching_files = []
        for f in files:
            if f.filename.startswith(f"{checkpoint_id}/"):
                matching_files.append(f)
            elif checkpoint_id in f.filename:
                matching_files.append(f)

        if matching_files:
            target_dir.mkdir(parents=True, exist_ok=True)
            print(f"📦 Found {len(matching_files)} files for {checkpoint_id} in file storage -> {target_dir}")
            for f_obj in matching_files:
                filename = Path(f_obj.filename).name
                output_file = target_dir / filename
                if output_file.exists() and output_file.stat().st_size > 0:
                    print(f"   ✓ {filename} (already downloaded)")
                    continue
                print(f"   ⬇️ Downloading {filename}...")
                content = client.files.content(f_obj.id)
                content.write_to_file(str(output_file))
            print(f"✅ Checkpoint {checkpoint_id} ready at: {target_dir}\n")
            return target_dir
    except Exception as e:
        print(f"❌ Error searching file storage: {e}")

    print(f"❌ Checkpoint '{checkpoint_id}' not found in jobs or file storage.")
    sys.exit(1)

def fetch_latest_checkpoint(client: OpenAI, job_id: str = None) -> Path:
    if job_id:
        target_job = client.fine_tuning.jobs.retrieve(job_id)
        if target_job.status != "succeeded":
            print(f"❌ Job {job_id} is not in 'succeeded' state (Current: {target_job.status})")
            sys.exit(1)
        succeeded_jobs = [target_job]
    else:
        jobs = client.fine_tuning.jobs.list(limit=10).data
        succeeded_jobs = [j for j in jobs if j.status == "succeeded"]
        if not succeeded_jobs:
            print("❌ No succeeded fine-tuning jobs found.")
            sys.exit(1)

    latest_job = succeeded_jobs[0]
    print(f"🎯 Selected Job: {latest_job.id} (Created: {getattr(latest_job, 'created_at', 'N/A')})")
    
    ckpts = client.fine_tuning.jobs.checkpoints.list(latest_job.id).data
    if not ckpts:
        print(f"❌ No checkpoints found for job {latest_job.id}")
        sys.exit(1)

    # Sort by step number descending to get the latest/final checkpoint
    def step_key(c):
        val = getattr(c, "step_number", 0)
        return int(val) if isinstance(val, (int, str)) and str(val).isdigit() else 0

    sorted_ckpts = sorted(ckpts, key=step_key, reverse=True)
    best_cp = sorted_ckpts[0]
    
    target_dir = OUTPUT_DIR / best_cp.id
    download_checkpoint_files(client, best_cp, target_dir)
    return target_dir

def main():
    parser = argparse.ArgumentParser(description="Download Nebius fine-tuning checkpoints")
    parser.add_argument("--list", action="store_true", help="List all available jobs and checkpoints")
    parser.add_argument("--checkpoint", type=str, default=None, help="Specific checkpoint ID to download (e.g. ftckpt_...)")
    parser.add_argument("--job", type=str, default=None, help="Specific job ID to download latest checkpoint from")
    args = parser.parse_args()

    client = get_client()

    if args.list:
        list_all(client)
        return

    if args.checkpoint:
        target = fetch_specific_checkpoint(client, args.checkpoint)
    else:
        target = fetch_latest_checkpoint(client, job_id=args.job)

    print(f"LOCATION={target}")

if __name__ == "__main__":
    main()
