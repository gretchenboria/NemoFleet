# NemoFleet: project briefing

**Hackathon:** Nebius × NVIDIA Global AI Hackathon, Physical AI track. Deadline **Fri Oct 30, 2026, 10:00 PDT**.

**Repo:** https://github.com/gretchenboria/NemoFleet. It is private and must be made **public** before submitting.

**Live site:** https://nemofleet.pages.dev (Cloudflare Pages project `nemofleet`).

## What it is

A robot fleet that learns from itself, in two selectable scenes: a **warehouse** (fulfillment center DC-04) and a **data center** (hyperscale hall B). Both scenes are unbranded.

| Tier | What | Where it runs |
|---|---|---|
| System 1 · reflex | Nemotron Nano: an action plus a confidence score | Token Factory (later: our vLLM Serverless Endpoint with nightly LoRA) |
| System 1.5 · peers | Handshakes when robots pass; fading hazard tags; countercurrent pairing | On the robots, with no model call |
| System 2 · deliberation | Nemotron Ultra for novel or safety-critical events | Token Factory |
| Perception | Cosmos3 Super Reasoner on the first sighting of a hazard | Token Factory dedicated endpoint (4× H200, **$0.37/min while running**) |
| Night Shift | Replay → Dream → Gate → Consolidate (LoRA) every night | Token Factory batch + Serverless Jobs + MLflow |

**Safety invariants:**
- A person in the lane always escalates to Ultra.
- Every model output is validated against the FleetAction schema; anything invalid is retried once, then the robot makes a safe stop.
- The deterministic planner owns motion; models never output coordinates.

**Pitch line:** "The edge lives it once. Nebius lives it hundreds of times."

## Verified model ids (`config/models.yaml`)

| Role | Model id |
|---|---|
| Ultra | `nvidia/Nemotron-3-Ultra-550b-a55b` |
| Nano | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` |
| Super | `nvidia/nemotron-3-super-120b-a12b` |
| Cosmos | `dedicated/nvidia/Cosmos3-Super-Reasoner-g_EjNm` |

- **Base URL:** `https://api.tokenfactory.us-central1.nebius.com/v1`
- **Cosmos status at handoff:** answered "starting", so it was not yet Ready.

## Infrastructure

| Thing | Id or name |
|---|---|
| Cloudflare account | id in `.env` (`CLOUDFLARE_ACCOUNT_ID`) |
| Pages project | `nemofleet` (created with `--force` as classic Pages) |
| D1 | `nemofleet-memory` (`eb9d266f-5753-45da-9378-5797b5cf1fdc`); migration 0001 applied, **0002 not yet applied** |
| R2 | `nemofleet-runs` |
| KV | `NEMOFLEET_TAGS` (`51e4053c22464b5dbe31b0069ed10281`) |
| Google Secret Manager | `gemini-api-key`, version 2 (project `gen-lang-client-0221638641`) |

**Secrets** live only in `.env`, which is gitignored and has 600 permissions: `NEBIUS_API_KEY`, `GEMINI_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and the `R2_*` keys. The QA suite fails if any `.env` value appears in a tracked or built file.

## Repository map

| Path | What |
|---|---|
| `docs/ARCHITECTURE.md` + `NemoFleet-Architecture.pdf` | Architecture (8-page PDF). **Warehouse framing only** |
| `docs/NEBIUS_PLAN.md` + PDF | The implementation plan three review agents agreed on (decisions, schedule, votes) |
| `docs/DEMO.md` + PDF | Demo script. **Warehouse only** |
| `docs/RUNBOOK.md` | How to run a scenario for real on Nebius |
| `docs/FEEDBACK.md` + PDF | Platform feedback for the submission (problem, measured, workaround, fix) |
| `docs/NemoFleet-Countercurrent-Options.pdf` | The peer-learning design options considered |
| `docs/NemoFleet-Peer-Learning-Explainer.mp4` + `docs/video/` | 3:19 explainer (Gemini TTS, Achird voice). **Warehouse only** |
| `site/` | Static site: `build.cjs` → `site/dist`; console source in `site/src/console.body.html` |
| `functions/api/[[path]].js` | **New:** Pages Functions API (D1, KV, R2 + Token Factory). Not yet deployed |
| `cloudflare/` | `wrangler.jsonc` (bindings for migrations) + `migrations/0001`, `0002` |
| `tools/` | `tf.cjs` (client), `preflight.cjs`, `run_scenario.cjs`, `cosmos_perceive.cjs` |
| `scenarios/` | `aisle4-spill.json` (warehouse), `hall-b-coolant-leak.json` (data center), each with a `device` per robot |
| `config/models.yaml` | Single model registry |
| `tests/qa.cjs` | QA suite (84 checks). Deploy only when it exits 0 |

## Status

**Works today:**
- The site and docs.
- Both console scenes: photoreal floor and camera frames, the scene switch.
- The command-line runner (`tools/run_scenario.cjs`) with real model calls.
- The D1, KV and R2 stores.

**Not yet working:**
- The console's buttons are still front-end placeholders that show "example only".
- The backend API exists but isn't deployed or wired up.
- Night Shift's Dream, Gate and Consolidate stages need a Serverless Jobs runner, which isn't built.

See [HANDOFF.md](HANDOFF.md) for next steps.
