# Runbook: the hall B coolant leak, for real on Nebius

This runs Day 1 of the [demo use case](DEMO.md) with real model calls:
- **Cosmos3 Super Reasoner** looks at four robot camera frames.
- **Nemotron Nano** handles routine decisions.
- **Nemotron Ultra** handles the safety-critical one, plus anything Nano isn't confident about.

Every call is logged so tonight's Night Shift can replay it.

## What's real and what isn't

| | |
|---|---|
| Real | Every model call, its latency, tokens and output; the safety gate; schema validation; the call log |
| Simulated | The robots and the data center hall; the camera frames are rendered images (`site/assets/frames/`) |

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
node tools/preflight.cjs            # checks key, lists Nemotron/Cosmos models, pings Cosmos
node tools/preflight.cjs --write    # writes the chosen Ultra / Nano / Super ids into config/models.yaml
```

Preflight picks the newest Nemotron Ultra, Nano and Super it finds in your catalog. If it picks the wrong one, edit `config/models.yaml` by hand.

## 3. Rehearse offline, then run

```bash
node tools/run_scenario.cjs scenarios/hall-b-coolant-leak.json --dry-run   # no network, no cost
node tools/run_scenario.cjs scenarios/hall-b-coolant-leak.json      # real calls
```

### What happens, event by event

| t | Robot | Event | Route |
|---|---|---|---|
| 0 s | R07 | Clear cold aisle | Cosmos, then Nano |
| 5 s | R14 | First sighting of the coolant leak at the row end | Cosmos, then Nano; escalates to Ultra if confidence < τ (0.62) |
| 12 s | R09 | Handshake from R14 | No model call |
| 14 s | R05 | Handshake from R09 (hop 2) | No model call |
| 20 s | R03 | Technician in the aisle | Cosmos, then **always Ultra** |
| 30 s | R12 | Leak plus a lift cart crossing (Day 2 preview) | Cosmos, then Nano with the peer precedent |

### The safety gate

- **Schema check:** every model answer must pass the FleetAction schema. If it doesn't, the model gets one retry with the error. If it fails again, no action is executed and the robot makes a safe stop.
- **Motion:** models never output coordinates.

## 4. Where the results go

| Output | Path |
|---|---|
| Every call (Night Shift replay input) | `runs/hall-b-coolant-leak-<timestamp>/calls.jsonl` |
| Decisions and totals | `runs/hall-b-coolant-leak-<timestamp>/summary.json` |
| Cosmos results (shown on the console's camera tiles) | `site/assets/perception/*.json` |

## 5. Publish and stop

```bash
node tests/qa.cjs && npx wrangler pages deploy site/dist --project-name nemofleet --branch main
```

Then **stop the Cosmos endpoint** in the Token Factory console. Add what you measured (latency, cold start, cost) to [FEEDBACK.md](FEEDBACK.md).

## Expected cost for one run

| Item | Cost |
|---|---|
| Cosmos endpoint, about 15 minutes including warm-up | about $5.50 |
| Nano + Ultra calls | well under $1 |
| **Total** | **about $6** |
