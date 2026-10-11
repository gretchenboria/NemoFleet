# Brodel — Fine-Tuning & Ephemeral Eval Pipeline

Streamlined LoRA fine-tuning on **Nebius Token Factory** and ephemeral GPU evaluation on **Nebius Compute (SkyPilot)**.

---

## 🔑 Credentials Setup (`.env`)

Your [`.env`](file:///Users/jorgeajimenez/repos/NemoFleet/finetuning/brodel/.env) file manages both Nebius keys:

```bash
NEBIUS_API_KEY_TOKEN_FACTORY=v1.Cm...   # For fine-tuning jobs & checkpoint downloads
NEBIUS_API_KEY_AI_CLOUD=v1.Cm...        # For Nebius Compute / SkyPilot VMs
```

---

## ⚡ 3-Step Workflow

### 1. Fine-Tune (OpenOrca via YAML Config)
Prepare dataset and trigger a LoRA fine-tuning job using a structured YAML config:
```bash
# 1. Prepare dataset slice (2.5k train / 200 val)
uv run python prepare_openorca.py --samples 2500 --val-samples 200

# 2. Trigger fine-tuning from YAML config (default: configs/default.yaml)
uv run python train_openorca.py --config configs/default.yaml

# Or run high capacity / custom sweeps:
uv run python train_openorca.py --config configs/openorca_v2_high_capacity.yaml
```
*(Every run automatically saves an immutable `config.yaml` artifact inside its checkpoint and logs parameters & step loss to local MLflow).*

### 2. Deploy Ephemeral Evaluation VM
Provision an H100 GPU instance with your fine-tuned checkpoint:
```bash
# Launch with latest checkpoint (or specify a checkpoint ID)
./launch_vm.sh

# Or launch with a specific checkpoint:
./launch_vm.sh ftckpt_9f8b99e4-556a-4c74-b08b-836a11152d5b
```

### 3. Evaluate & Sync Results
Run tests on the VM and sync logs back locally:
```bash
# SSH into VM and test
sky ssh brodel-eval
cd sky_workdir && uv run python test_model.py

# Pull logs & markdown report back to local machine
./sync_results.sh
```

---

## 📁 Project Structure

```
├── .env                              # Token Factory & AI Cloud API keys
├── .archive/                         # Archived legacy scripts and older datasets
├── OPENORCA_FINE_TUNING_STRATEGY.md  # Hyperparameter hunting & evaluation strategy
│
├── prepare_openorca.py               # Generates openorca_train.jsonl & val.jsonl
├── train_openorca.py                 # Submits LoRA jobs to Token Factory
├── fetch_checkpoint.py               # Downloads checkpoints from Token Factory
│
├── launch_vm.sh                      # Deploys Nebius H100 VM via SkyPilot
├── sync_results.sh                   # Reverse syncs evaluation logs to local
├── test_model.py                     # Interactive & scripted model evaluator
├── sky-nebius-eval.yaml              # SkyPilot cluster configuration
│
├── model_files_v2/                   # Downloaded LoRA adapter checkpoints
└── eval_results/                     # Synced evaluation logs (JSONL + Markdown)
```

---

## 🛠️ Helpful Commands

| Action | Command |
| :--- | :--- |
| **View Local Loss Curves & Runs** | `uv run python track_experiments.py` |
| **Launch Local MLflow Web UI** | `uv run python track_experiments.py --ui` *(Opens http://localhost:5000)* |
| **Sync Runs from Nebius** | `uv run python track_experiments.py --sync-nebius` |
| **List Token Factory Checkpoints** | `uv run python fetch_checkpoint.py --list` |
| **Download Specific Checkpoint** | `uv run python fetch_checkpoint.py --checkpoint <ckpt_id>` |
| **Compare with Base Model** | `uv run python test_model.py --base_only` (on VM) |
| **Pull Results Anytime** | `./sync_results.sh` |
| **Tear Down VM** | `sky down brodel-eval --yes` *(Auto-stops after 20m idle)* |
