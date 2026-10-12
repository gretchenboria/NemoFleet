# Fine-tune plan v3: Nemotron 3 Nano, "person in the way"

Written 2026-10-11. Replaces the data and budget pages of `NemoFleet-FineTune-Plan.pdf` (v2, which trained on Waymo alone and listed BDD100K as optional). Nothing in this plan has been launched or spent.

**Goal.** A LoRA adapter for `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (the reflex tier) that reads the people around an ego as text and answers whether one of them will be in its way in the next 5 s, better than constant-velocity extrapolation and better than the untuned model.

**Budget.** $25 of Nebius credits. Expected spend $9, worst case inside the plan $20, $5 held back.

## 1. Data (built, in `data/`, gitignored)

| | Source | Viewpoint | Labels | Licence |
|---|---|---|---|---|
| Human ego | THÖR-MAGNI demo subset, 22 runs | from each person's helmet | motion capture | CC BY 4.0 |
| Robot ego | same 22 runs | from the robot | motion capture | CC BY 4.0 |
| Vehicle ego | Waymo Open Motion v1.3.1, 70 training + 20 validation shards | from the car | Waymo tracks | Waymo non-commercial |

Label, fixed: a listed person is inside the ego's zone at any recorded instant in the next 5 s. The zone is 2.5 m ahead and 0.6 m either side for a robot or person, 7.5 m and 1.5 m for a car, and is stated in every prompt.

Split (identical val and test for every training mix below; SHA-256 prefixes `445780d9` val, `ab6cdeb3` test):

| | Train pool | Val | Test | Positive rate |
|---|---|---|---|---|
| Human ego | 83% (18 runs) | 922 (2 runs) | 890 (2 runs) | 43–45% |
| Robot ego | 82% (18 runs) | 441 (2 runs) | 339 (2 runs) | 27–30% |
| Vehicle ego | 16,359 scenarios | 4,212 (1,404 scenarios) | 4,212 (1,404 scenarios) | 3.3% |

A whole run or scenario sits in one split with all its viewpoints. Waymo training shards go only to train; Waymo validation shards are halved into val and test.

Bar to beat on test, constant-velocity extrapolation (`tools/ego_mix/baseline.py`):

| | Recall | False-alarm rate |
|---|---|---|
| Human ego | 54.5% | 6.7% |
| Robot ego | 73.6% | 10.9% |
| Vehicle ego | 86.7% | 0.7% |

## 2. Training mix: equal thirds is not the best use of the data

Equal thirds sized every viewpoint to the scarcest one and discarded most human-ego samples. The real limits are different for each source:

- **Robot ego is the scarce, most relevant data** (about 3,500 train samples). Use nearly all of it.
- **Human ego has about 8,900 train samples.** Equal thirds used 3,567 of them.
- **Waymo is limited by positives, not by volume.** Only 3.3% of samples are positive, so the cap of three negatives per positive sets its size: 70 shards give 1,608 usable positives. More shards cost about 12 s each and no money.

Main run uses **human 2 : robot 1 : vehicle 2** (16,080 samples, 34% positive). It keeps Waymo at 40% of training because a model trained mostly on cars may learn car habits, and the test that matters is robot ego.

Whether Waymo helps at all is an open question, so it is measured rather than assumed:

| Run | Train set | Samples | Purpose |
|---|---|---|---|
| A (main) | `data/ego_mix` | 16,080 | human 2 : robot 1 : vehicle 2 |
| B | `data/ego_mix_no_waymo` | 7,134 | does Waymo help robot-ego recall? |
| C | `data/ego_mix_thirds` | 10,701 | does the 2:1:2 mix beat equal thirds? |

The adapter that ships is the one with the best robot-ego result on val. Test is read once, for that adapter only.

## 3. Evaluation

- **Primary metric:** robot-ego recall at the baseline's false-alarm rate. The score is the model's probability of `true` after `{"in_way":`, read from one forward pass, so the threshold can be set to match the baseline exactly.
- **Also reported:** the same for human ego and vehicle ego; recall on positives where the person is not yet in the zone (57 of 91 robot-ego test positives); JSON validity and timing error on 300 generated answers.
- **Compared against:** constant velocity, untuned Nemotron 3 Nano on the same prompts, and runs B and C.
- **Success:** run A beats constant velocity on robot-ego test by at least 5 points of recall at the same false-alarm rate, and beats the untuned model. If it does not, that is the result that gets written up.
- **Known weakness:** robot-ego test is 339 samples and 91 positives, so one recall figure carries roughly ±9 points. Report the interval, and report val and test together as a second view.

## 4. Jobs and cost

Prices are the ones recorded in plan v2 for this project: RTX PRO 6000 (96 GB) $1.80/h, H200 $4.50/h, CPU from $0.10/h. Training speed is an assumption (2,000 tokens/s, about 300 tokens per sample) until the pilot measures it.

| Step | What | GPU time | Cost |
|---|---|---|---|
| 0 | Upload the three sets to a private HF dataset repo | none | $0 |
| 1 | Smoke test: model downloads (63 GB), LoRA attaches to the intended layers, loss falls on 50 steps (`MODE=smoke`, self-stops at 40 min) | 0.4 h | $0.7 |
| 2 | Main job: setup, untuned-model eval, 300-step pilot with automatic gate, run A for 2 epochs, eval, upload | 2.2 h | $4.0 |
| 3 | Comparison job: runs B and C, 2 epochs each, eval, upload | 2.2 h | $4.0 |
| | **Expected total** | 4.8 h | **$8.7** |
| | If training runs at half the assumed speed | 7.6 h | $13.7 |
| | Plus one full rerun of step 2 after a failure | | $17.7 |

Stop rules, so the credits cannot run out by accident:

1. Every job stops itself after `MAX_MINUTES` (40 for step 1, 210 for steps 2 and 3). The platform's own `--timeout` cannot go below 1 h, so it is set as a backstop.
2. After the pilot, the job prints measured tokens/s and the projected cost of the main run. If the projection for step 2 exceeds $8, it stops and uploads the log.
3. Total spend is capped at $20. $5 stays in reserve for a rerun or a short demo.
4. If the RTX PRO 6000 cannot load the model, step 2 moves to one H200 ($9.9 for the same 2.2 h) and step 3 shrinks to run B only at 1 epoch ($4). Total about $15.
5. Spot pricing (from $0.79/h) is not used until checkpoint-resume has worked once.

**Blocker found 2026-10-11: the Nebius tenant is suspended.** `black-hamster-tenant-qpx` (where the earlier NemoFleet jobs ran) and its us-central1 project report `suspension_state: SUSPENDED`, and every job create, even a 2-vCPU CPU job, is refused with PermissionDenied. `RobotOps-t82` is suspended too; `emerald-quelea-tenant-ctt` is active but has zero quota. Nothing can launch until the tenant is reactivated in the Nebius console (billing).

**Before any of this: check that nothing else is billing.** `config/models.yaml` lists a Gemma 4 endpoint on one H200 billed per hour while running, and the Cosmos endpoint at $0.37/min. Either one left on would consume the $25 in hours. Checked 2026-10-11 across all 24 projects in the three tenants: the only endpoint is `nemofleet-gemma4` (tenant `black-hamster-tenant-qpx`, us-central1) and it is STOPPED; there are no unfinished jobs and no compute instances. The Cosmos endpoint is a Token Factory dedicated endpoint, which that listing does not cover; you deleted it (confirmed by you 2026-10-11), and it is absent from Token Factory's model list. Re-run the endpoint scan before each job.

## 5. Job design

One container per job, following `tools/cosmos_dream/dream.sh`: pinned versions, log and partial results uploaded from an EXIT trap, private HF repo for outputs.

- Plain Transformers 5.19 + PEFT 0.21 (the model is supported natively, so no Unsloth and no kernel build). LoRA r=16 on the Mamba `in_proj`, the attention projections and each MoE layer's shared-expert MLP; bf16; 2 epochs; learning rate 1e-4 with warm-up. PEFT refuses the Mamba `out_proj`, and the 128 routed experts are raw tensors LoRA cannot wrap.
- `tools/ego_mix/train.py` has been run end to end on a miniature random copy of the architecture (both modes, two back-to-back runs). It has not yet run on the real model or a GPU.
- The job asserts the trainable-parameter fraction before training. Plan v2 recorded that the default LoRA targets for this architecture silently cover about 7% of layers.
- Checkpoint every 500 steps to the HF repo; keep the checkpoint with the lowest val loss.
- Evaluation runs inside the same job with the same inference code, because serving this adapter through vLLM is unverified.
- Fixed seeds; the manifest and the two split hashes are logged with every run.

## 6. Risks

| Risk | What happens | Response |
|---|---|---|
| Mamba kernels fail on RTX PRO 6000 | step 1 fails | H200 (stop rule 4) |
| Nano 3 does not fit or stalls | step 1 or pilot fails | Nemotron Nano 9B v2 with plain PEFT, same data and eval |
| Model learns "vehicle means no" | high overall accuracy, no gain on robot ego | run B shows it; ship B |
| Overfits 22 lab runs | train loss falls, val loss rises | keep best-val checkpoint; stop at 1 epoch |
| Robot-ego test too small to separate runs | intervals overlap | pool val and test for the comparison; add the full THÖR-MAGNI release |
| Adapter cannot be served on Token Factory | no live demo of the tuned model | show offline eval; serve on a short-lived endpoint from the reserve |

## 7. Licence

You confirmed on 2026-10-11 that Waymo data may be used for the hackathon. Waymo's terms still apply to what is produced: sets A and C, and any adapter trained on them, stay in private repos and out of the public repo, site and video, and carry the Waymo attribution. Only aggregate numbers and our own plots are published. Run B's training set is CC BY 4.0 only, so its adapter can be public.

## 8. Not in this plan

- No data from an actual data center or AI factory exists in any of the three sources. The model sees positions, not images, so what transfers is how people move around an ego, not what a data hall looks like.
- The full THÖR-MAGNI release (22 GB) would enlarge the robot-ego pool and tighten the test intervals. It does not fit on this laptop (about 1 GB free) and would run as a CPU job for well under $1.
- JRDB (approval pending) and MuSoHu adapters exist in `tools/ego_mix/` but are not used here.

## 9. Results (run `main-1`, 2026-10-11)

Ran through SkyPilot on one spot H200 in eu-west1 ($0.79/h) in tenant `emerald-quelea-tenant-ctt`: 12 min smoke test, then one 107 min job for the untuned baseline and all three mixes. About $2 of GPU time plus about $1 of failed RTX PRO 6000 probes (that platform does not start in this tenant, and the model peaks at 129 GiB at batch 8, so it would not fit 96 GB anyway). Training ran at about 5,500 tokens/s at batch 4. Adapters and scores are in the private HF repo `gretchenboria/nemofleet-ego-lora`; scores are also in `data/ego_runs/main-1`.

Recall at the constant-velocity baseline's false-alarm rate, val and test pooled (`tools/ego_mix/score.py` gives the per-split view):

| Viewpoint (positives) | Baseline | Main mix 2:1:2 | No Waymo | Equal thirds |
|---|---|---|---|---|
| Human ego (798) | 53.9% | 57.6% (+3.8, CI +1.0 to +6.4) | 55.3% | 56.8% |
| Robot ego (216) | 74.1% | 74.5% (+0.5, CI -4.0 to +5.2) | 74.5% | 75.5% |
| Vehicle ego (271) | 87.8% | 90.0% (+2.2, CI -1.7 to +6.1) | 9.2% | 84.5% |

- The untuned model is at chance (AUROC 0.40 to 0.57). Fine-tuning takes it to AUROC 0.86 human, 0.90 robot, 0.99 vehicle on test, with 300 of 300 valid JSON answers.
- The success criterion (at least 5 points over the baseline on robot ego) was **not met**: on robot ego the tuned model matches constant velocity and does not beat it.
- Waymo makes no measurable difference to robot-ego recall. It is what makes vehicle ego work at all, and it improves the written answers (271 vs 256 of 300 correct; timing error 0.23 s vs 0.44 s).
- The three mixes are indistinguishable on robot ego at this sample size.
- A threshold chosen on val does not hold its false-alarm rate on test (for example 17% instead of 11% on robot ego), because val and test are two lab runs each.

## 10. Review and headroom test (2026-10-11)

An independent ML review concluded that this formulation should not be fine-tuned further: a gradient-boosted model on features from the same prompts matches the tuned LLM (robot ego 73.6% vs 74.5%), 46% of robot-ego positives are already in the zone, and the misses come from the ego's own motion, which the prompt does not contain.

`tools/ego_mix/headroom.py` then tested what extra input would help, on all 22 runs with leave-runs-out CV (robot ego, recall at the constant-velocity baseline's 12.2% false-alarm rate; per-run difference with 95% interval):

| Input | Recall | Not-yet-in-zone positives | Gain over baseline |
|---|---|---|---|
| Constant velocity in the ego frame (baseline) | 69.0% | 51.8% | |
| What today's prompt holds | 73.9% | 59.4% | +2.1 (-3.8 to +6.6) |
| + ego speed and turn rate, person velocity in the world frame | 76.0% | 62.7% | +3.6 (-1.6 to +8.2) |
| + the ego's planned path | 80.6% | 69.8% | +7.1 (+0.2 to +13.1) |

Ego speed and turn rate alone do not give a reliable gain. The planned path does, and even plain constant velocity checked against the planned path reaches 75.1%. Human ego gains far more (55.7% to 81.3%), but a person's future path and head direction are not known in deployment, so that number does not transfer.

## 11. Run `plan-1`: the ego's planned path in the prompt (2026-10-11)

Same 16,080 training samples, same val and test rows and same labels as `main-1`; only the prompt changed (`featurize.py --plan`): every point is expressed in the ego's frame at decision time, and the prompt adds the ego's own past path and its planned path for the next 5 s. One spot H200, 70 min, about $0.95.

Recall at the baseline's false-alarm rate, val and test pooled (95% interval over samples for the gain of run 2):

| Viewpoint (positives) | Baseline A: constant velocity, ego frame | Run 1 | Run 2 (planned path) | Baseline B: constant velocity against the planned path | Run 2 at B's false-alarm rate |
|---|---|---|---|---|---|
| Human ego (798) | 53.9% | 57.6% | 68.5% (+14.7, +11.5 to +17.9) | 78.6% | 77.1% (-1.5, -4.3 to +1.5) |
| Robot ego (216) | 74.1% | 74.5% | 80.1% (+6.0, +0.5 to +11.7) | 74.1% | 80.1% (+6.0, +0.5 to +11.3) |
| Vehicle ego (271) | 87.8% | 90.0% | 90.0% (+2.2, -1.6 to +5.9) | 86.3% | 84.9% (-1.5, -5.9 to +2.8) |

- Robot ego now clears the 5-point criterion against both baselines, and on positives where the person is not yet in the zone it gets 62.9% against 51.7%. The interval's lower edge is close to zero and, as the review noted, sample-level intervals are optimistic because the 216 positives come from 26 episodes.
- Test AUROC rose from 0.86 / 0.90 / 0.99 to 0.90 / 0.92 / 0.995 (human / robot / vehicle). 300 of 300 answers are valid JSON, 274 agree with the label, timing error 0.21 s.
- Human ego gains 15 points over the original baseline but only ties the plan-aware one: knowing where a person's head will point explains most of that gain.
- The untuned model stays near chance with the new prompt (test AUROC 0.57 to 0.67), so the gain comes from fine-tuning, not from the prompt alone.

## 12. Simulated data ready to mix in

`adapt_smartspaces.py` turns NVIDIA's Omniverse-generated PhysicalAI-SmartSpaces scenes (CC BY 4.0) into the same track format: 19 scenes, 54,736 planned-path samples, 14,613 of them robot ego (NovaCarter and Transporter robots among 3 to 120 people). Every track is hinted train-only, so val and test stay real. Half its samples are positive against about 30% in the real robot-ego data, so its share of training should be capped. Not yet trained on.
