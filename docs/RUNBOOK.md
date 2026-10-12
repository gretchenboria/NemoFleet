# Runbook: running NemoFleet for real on Nebius

This runs Day 1 of the [demo use case](DEMO.md) at either site (warehouse aisle 4 spill or data center hall B coolant leak) with real model calls. There are two ways to run it: the **operator console** (section 3) or the **command line** (section 4). In both:
- **Cosmos3 Super Reasoner** looks at four robot camera frames.
- **Nemotron Nano** handles routine decisions.
- **Nemotron Ultra** handles safety-critical and novel events, plus anything Nano isn't confident about.

Every call is logged so tonight's Night Shift can replay it.

## What's real and what isn't

| | |
|---|---|
| Real | Every model call, its latency, tokens and output; the safety gate; schema validation; the call log |
| Simulated | The robots, the warehouse and the data center hall; the camera frames are rendered images (`site/assets/scenes/<scene>/frames/`) |

## 1. One-time setup

```bash
cd ~/Nebius/NemoFleet
cd docs/video && npm install && cd ../..             # puppeteer-core + marked for builds and QA
printf 'NEBIUS_API_KEY=%s\n' 'YOUR_TOKEN_FACTORY_KEY' >> .env   # .env is gitignored
```

## 2. Start Cosmos and run preflight

1. In the Token Factory console, start the `Cosmos3-Super-Reasoner` dedicated endpoint and wait for **Ready**.
   - It bills about **$0.37/min** while running.
2. Run preflight:

```bash
node tools/preflight.cjs            # checks key and catalog, makes one real call to Ultra, Nano, Super and Cosmos; exit 0 only if all answer
node tools/preflight.cjs --write    # writes the chosen Ultra / Nano / Super ids into config/models.yaml
```

Preflight picks the newest Nemotron Ultra, Nano and Super it finds in your catalog. If it picks the wrong one, edit `config/models.yaml` by hand.

## 3. Run it from the console

Open https://nemofleet.pages.dev/console. The badge next to the scene switch says **Live · D1 · KV · R2** when the API answers. Anywhere else (a local static file preview) it says **Offline preview** and shows no data.

| Control | What it really does |
|---|---|
| **Warehouse / Data center / San Francisco** | Picks the site. Everything on the page is scoped per site |
| **Send test incidents** (`#act-run`) | `POST /api/scenario/start`, then `/scenario/step` once per event (camera perception, person-in-the-way check, fleet-memory lookup, then Nano or Ultra through the gate), then `/scenario/finish` |
| **Latest run only / Show all runs** (`#scope-toggle`) | Switches the KPI strip and Station 01 readout between the latest run and cumulative multi-run history in D1 |
| **Audit Nano with Ultra** (`#act-night`) | Loops `POST /api/night-shift/replay`: Ultra re-judges up to 4 un-judged Nano decisions per call until none remain |
| **Spatial Command & Fleet Memory Map** (`#floor` + `#map-hud`) | Interactive floor canvas showing live robot telemetry pills, clickable robots and map cells, Fleet Memory sync halos (`MEM`) on robots holding the active cell precedent, animated peer-to-peer antennation arcs on pass, cell decision badges (`ULTRA · REROUTE · 3×`, `QUARANTINED`, `OPERATOR · 1×`), and one-click spatial actions (**Halt / Resume robot**, **Quarantine / Release cell**, **Cell rule** jump) |
| **Incident panel — Accept / Override / Release** (`#incident`) | Clicking any open alarm opens the linked sighting, camera perception, model decision, fleet actions, and stored precedent. **Override** writes a new `operator` precedent for that cell (never cached when a person is involved) |
| **Fleet memory tab** (`#pane-dec`) | Lists every stored cell precedent with `Known by n of m robots`, reuse count, and TTL; supports **Keep (Pin)**, **Keep longer (+10m)**, and **Stop using (Revoke)**, plus the unified **Recent event decisions across the fleet (Nano, Fleet Memory & Ultra)** table |
| **Alarm rules tab** (`#pane-rules`) | Full CRUD (`Create`, `Edit`, `Enable/Disable`, `Delete`, `Reset defaults`) for automatic alarm triggers (`person_in_lane`, `quarantine_action`, `alert_human_action`, `low_confidence`, `high_severity`, `any_hazard`) enforced live in `runEvent` |
| **Autonomy level & Promote / Hold** (`#auto`, `#adapters`) | Sets the acceptable error-rate target (`≤ 1%`, `≤ 2%`, `≤ 5%`, `≤ 10%`) backed by the measured action-token probability gate, and promotes or holds the dual-LoRA Nano endpoint (`decide-1` + `plan-1`) |
| **Quarantine zone, Halt robot, Broadcast hazard** | Writes a KV tag with a TTL (10 min, 1 h, 10 min) and logs the action in D1 |
| **Pause fleet / Resume fleet** (`#act-pause`) | KV flag. While paused, scenario steps and posted events return without making model calls |

Notes:
- Robot motion on the floor map is simulated; quarantine zones, halted robots, stored cell decisions, and peer handoff counts come from live D1 and KV state.
- KV listings are eventually consistent, so a new tag can take a few seconds to appear in the raw tag list.
- If the perception endpoint is unreachable, each frame row reports it and the run continues with camera content marked unknown.

### Deploying the console and API

```bash
node tests/qa.cjs                                  # must exit 0 (includes live API checks via wrangler pages dev)
npx wrangler pages deploy --project-name nemofleet --branch main   # from the repo root; wrangler.jsonc binds D1/KV/R2
```

- One-time: `npx wrangler d1 migrations apply nemofleet-memory --remote -c cloudflare/wrangler.jsonc` and `printf %s "$NEBIUS_API_KEY" | npx wrangler pages secret put NEBIUS_API_KEY --project-name nemofleet`.
- Local: `npx wrangler pages dev site/dist --d1 MEMORY=eb9d266f-5753-45da-9378-5797b5cf1fdc --kv TAGS --r2 RUNS`. `pages dev` does not read `wrangler.jsonc`, so pass the bindings as flags; put `NEBIUS_API_KEY=...` in a gitignored `.dev.vars` for model calls.

## 4. Run it from the command line

```bash
# pick a scene: scenarios/aisle4-spill.json (warehouse) or scenarios/hall-b-coolant-leak.json (data center)
node tools/run_scenario.cjs scenarios/hall-b-coolant-leak.json --dry-run   # no network, no cost
node tools/run_scenario.cjs scenarios/hall-b-coolant-leak.json      # real calls
```

### What happens, event by event

| t | Robot | Event | Route |
|---|---|---|---|
| 0 s | R07 | Clear cold aisle | Cosmos, then Nano |
| 5 s | R14 | First sighting of the coolant leak at the row end | Cosmos, then Ultra (novel hazard: no precedent yet) |
| 12 s | R09 | Handshake from R14 | No model call |
| 14 s | R05 | Handshake from R09 (hop 2) | No model call |
| 20 s | R03 | Technician in the aisle | Cosmos, then **always Ultra** |
| 30 s | R12 | Leak plus a lift cart crossing (Day 2 preview) | Cosmos, then Nano with the peer precedent |

The warehouse scenario has the same six beats: R07 clear aisle 2, R14 spill at the aisle 4 blind corner, two handshakes, R03 with a picker in aisle 4, R12 spill plus forklift.

### The safety gate

- **Schema check:** every model answer must pass the FleetAction schema. If it doesn't, the model gets one retry with the error. If it fails again, no action is executed and the robot makes a safe stop.
- **Escalation:** a person or safety event always goes to Ultra. A hazard with no precedent yet in the run (a novel hazard) also goes to Ultra; anything else goes to Nano and escalates if its confidence is below τ.
- **Motion:** models never output coordinates.

## 5. Where the results go

| Output | Path |
|---|---|
| Console runs: call index, alarms, actions, precedents, Night Shift | D1 `nemofleet-memory` (tables `calls`, `alarms`, `actions`, `precedents`, `runs`, `perception`, `night_shift`) |
| Console runs: raw prompts and model outputs | R2 `nemofleet-runs`, `calls/<scene>/<date>/` and `perception/<scene>/` |
| Fading tags, halts, pause, τ | KV `NEMOFLEET_TAGS`, keys prefixed `<scene>:` |
| Every call (Night Shift replay input) | `runs/hall-b-coolant-leak-<timestamp>/calls.jsonl` |
| Decisions and totals | `runs/hall-b-coolant-leak-<timestamp>/summary.json` |
| Cosmos results (shown on the console's camera tiles) | `site/assets/perception/*.json` |

## 6. Publish and stop

```bash
node tests/qa.cjs && npx wrangler pages deploy --project-name nemofleet --branch main
```

Then **stop the Cosmos endpoint** in the Token Factory console. Add what you measured (latency, cold start, cost) to [FEEDBACK.md](FEEDBACK.md).

## Expected cost for one run

| Item | Cost |
|---|---|
| Cosmos endpoint, about 15 minutes including warm-up | about $5.50 |
| Nano + Ultra calls | well under $1 |
| **Total** | **about $6** |
