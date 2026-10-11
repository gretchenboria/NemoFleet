import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Dict, Any, List

EXP_DIR = Path(__file__).parent / "experiments"
EXP_LOG = EXP_DIR / "runs.jsonl"
MLFLOW_DB = Path(__file__).parent / "mlflow.db"

def init_tracking():
    EXP_DIR.mkdir(parents=True, exist_ok=True)

def log_experiment_to_mlflow(
    run_name: str,
    params: Dict[str, Any],
    checkpoints_metrics: List[Dict[str, Any]],
    tags: Dict[str, str] = None,
    eval_summary: str = None
):
    """Log fine-tuning run to local MLflow SQLite instance."""
    try:
        import mlflow
        os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{MLFLOW_DB.resolve()}"
        mlflow.set_tracking_uri(f"sqlite:///{MLFLOW_DB.resolve()}")
        mlflow.set_experiment("brodel-finetuning")

        with mlflow.start_run(run_name=run_name):
            # Log Hyperparameters
            clean_params = {}
            for k, v in params.items():
                if isinstance(v, (int, float, str, bool)):
                    clean_params[k] = v
                else:
                    clean_params[k] = str(v)
            mlflow.log_params(clean_params)

            if tags:
                mlflow.set_tags(tags)

            # Log Step-by-Step Metrics
            for cp in checkpoints_metrics:
                step = cp.get("step_number") or cp.get("step") or 0
                train_loss = cp.get("train_loss")
                val_loss = cp.get("valid_loss")
                train_acc = cp.get("train_mean_token_accuracy")
                val_acc = cp.get("valid_mean_token_accuracy")

                if train_loss is not None:
                    mlflow.log_metric("train_loss", float(train_loss), step=int(step))
                if val_loss is not None:
                    mlflow.log_metric("val_loss", float(val_loss), step=int(step))
                if train_acc is not None:
                    mlflow.log_metric("train_accuracy", float(train_acc), step=int(step))
                if val_acc is not None:
                    mlflow.log_metric("val_accuracy", float(val_acc), step=int(step))

            # Log evaluation markdown artifact if provided
            if eval_summary and Path(eval_summary).exists():
                mlflow.log_artifact(eval_summary)

        print(f"📊 Run '{run_name}' successfully logged to local MLflow (sqlite:///mlflow.db)")
    except Exception as e:
        print(f"⚠️ MLflow logging notice: {e}")

def record_local_run(run_data: Dict[str, Any]):
    """Record run metadata and step losses to experiments/runs.jsonl."""
    init_tracking()
    with open(EXP_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(run_data, default=str) + "\n")

def ascii_sparkline(values: List[float], width: int = 24) -> str:
    """Generate an ASCII curve visualization for loss."""
    if not values:
        return "N/A"
    chars = [" ", " ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    min_v, max_v = min(values), max(values)
    if min_v == max_v:
        return chars[4] * min(len(values), width)
    
    res = []
    # Sample down to width
    step_size = max(1, len(values) // width)
    sampled = values[::step_size]
    for v in sampled:
        idx = int((v - min_v) / (max_v - min_v) * (len(chars) - 1))
        idx = max(0, min(len(chars) - 1, idx))
        res.append(chars[idx])
    return "".join(res)

def print_terminal_dashboard():
    """Print terminal comparison table and loss sparklines."""
    init_tracking()
    print("\n" + "=" * 90)
    print("📈 Brodel Local Experiment Tracker — Runs & Hyperparameters")
    print("=" * 90)

    if not EXP_LOG.exists() or EXP_LOG.stat().st_size == 0:
        print("ℹ️ No local runs recorded yet.")
        print("Tip: Run `uv run python track_experiments.py --sync-nebius` to import past jobs from Nebius!")
        print("=" * 90 + "\n")
        return

    runs = []
    with open(EXP_LOG, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                runs.append(json.loads(line))

    # Header
    print(f"{'Run / Job ID':<26} | {'Suffix / Name':<16} | {'LR':<8} | {'r/α':<8} | {'Ep':<3} | {'Steps':<6} | {'Loss Curve':<10} | {'Final Loss':<10}")
    print("-" * 90)

    for r in runs:
        job_id = r.get("job_id", "N/A")[:24]
        suffix = r.get("suffix", "N/A")[:15]
        params = r.get("hyperparameters", {})
        lr = f"{params.get('learning_rate', 'N/A')}"
        r_alpha = f"{params.get('lora_r', '-')}/{params.get('lora_alpha', '-')}"
        epochs = f"{params.get('n_epochs', '-')}"
        
        cps = r.get("checkpoints", [])
        step_count = len(cps)
        train_losses = [cp["train_loss"] for cp in cps if cp.get("train_loss") is not None]
        
        spark = ascii_sparkline(train_losses, width=8) if train_losses else "N/A"
        final_loss = f"{train_losses[-1]:.4f}" if train_losses else "N/A"
        
        print(f"{job_id:<26} | {suffix:<16} | {lr:<8} | {r_alpha:<8} | {epochs:<3} | {step_count:<6} | {spark:<10} | {final_loss:<10}")

    print("=" * 90)
    print(f"📁 Local MLflow DB: sqlite:///{MLFLOW_DB.resolve()}")
    print("🌐 View full interactive web graphs: `uv run python track_experiments.py --ui`")
    print("=" * 90 + "\n")

def sync_from_nebius():
    """Sync past jobs & checkpoint loss metrics directly from Nebius Token Factory."""
    from fetch_checkpoint import get_client
    print("🔄 Connecting to Nebius Token Factory to import fine-tuning runs...")
    client = get_client()
    jobs = client.fine_tuning.jobs.list(limit=20).data
    
    init_tracking()
    imported_count = 0

    # Read existing job IDs
    existing_job_ids = set()
    if EXP_LOG.exists():
        with open(EXP_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        existing_job_ids.add(json.loads(line).get("job_id"))
                    except Exception:
                        pass

    for job in jobs:
        if job.id in existing_job_ids:
            continue

        try:
            cps_obj = client.fine_tuning.jobs.checkpoints.list(job.id).data
            cps_data = []
            for cp in cps_obj:
                m = getattr(cp, "metrics", None)
                train_loss = getattr(m, "train_loss", None) if m else None
                valid_loss = getattr(m, "valid_loss", None) if m else None
                train_acc = getattr(m, "train_mean_token_accuracy", None) if m else None
                valid_acc = getattr(m, "valid_mean_token_accuracy", None) if m else None
                step = getattr(cp, "step_number", None)

                cps_data.append({
                    "id": cp.id,
                    "step_number": step,
                    "train_loss": train_loss,
                    "valid_loss": valid_loss,
                    "train_mean_token_accuracy": train_acc,
                    "valid_mean_token_accuracy": valid_acc,
                })

            # Sort by step number
            cps_data.sort(key=lambda x: x.get("step_number") or 0)

            run_entry = {
                "job_id": job.id,
                "status": job.status,
                "model": job.model,
                "suffix": getattr(job, "suffix", ""),
                "created_at": getattr(job, "created_at", None),
                "hyperparameters": getattr(job, "hyperparameters", {}) if isinstance(getattr(job, "hyperparameters", {}), dict) else getattr(getattr(job, "hyperparameters", None), "__dict__", {}),
                "checkpoints": cps_data,
            }

            # Record local JSONL
            record_local_run(run_entry)

            # Log to local MLflow
            run_name = getattr(job, "suffix", None) or job.id
            params = run_entry["hyperparameters"] or {}
            params["model"] = job.model
            params["job_id"] = job.id
            log_experiment_to_mlflow(run_name=run_name, params=params, checkpoints_metrics=cps_data)

            imported_count += 1
            print(f" -> Imported Job: {job.id} ({len(cps_data)} checkpoints)")
        except Exception as e:
            print(f"⚠️ Error syncing job {job.id}: {e}")

    print(f"\n✅ Synced {imported_count} new runs from Nebius Token Factory into local tracking.")
    print_terminal_dashboard()

def start_ui():
    """Launch local MLflow UI server."""
    os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{MLFLOW_DB.resolve()}"
    print(f"🚀 Starting local MLflow UI at http://127.0.0.1:5000 ...")
    print(f"📦 Tracking Database: sqlite:///{MLFLOW_DB.resolve()}")
    print("Press Ctrl+C to stop.")
    subprocess.run(["mlflow", "ui", "--backend-store-uri", f"sqlite:///{MLFLOW_DB.resolve()}", "--port", "5000"])

def main():
    parser = argparse.ArgumentParser(description="Brodel Local Experiment & Hyperparameter Tracker")
    parser.add_argument("--sync-nebius", action="store_true", help="Sync past jobs and loss curves from Nebius Token Factory")
    parser.add_argument("--ui", action="store_true", help="Launch local MLflow web dashboard on http://127.0.0.1:5000")
    args = parser.parse_args()

    if args.sync_nebius:
        sync_from_nebius()
    elif args.ui:
        start_ui()
    else:
        print_terminal_dashboard()

if __name__ == "__main__":
    main()
