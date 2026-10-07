# Demo use case: one hazard, two sites

**One sentence:** a floor hazard is seen once, understood once by Cosmos on Nebius, spread to the whole fleet without another model call, made safe by Ultra when a person walks in, and learned overnight on Nebius, so the next morning a different robot handles a harder version of it alone.

The demo runs at either of two sites. The fleet design, the escalation gate and Night Shift are identical; only the scenario file changes. The operator picks the site with the **Warehouse / Data center** switch in the console.

| | Warehouse | Data center |
|---|---|---|
| Site | Fulfillment center DC-04, zone B, aisles 1–5 | Hyperscale hall B, cold aisles 1–3 |
| Scenario file | `scenarios/aisle4-spill.json` | `scenarios/hall-b-coolant-leak.json` |
| Hazard (first sighting) | Liquid spill at the aisle 4 blind corner | Coolant leak on the floor tiles at the end of row C2 |
| Person (always Ultra) | Picker in aisle 4 | Technician in cold aisle 2, zone C2 |
| Quarantine zone | A4 | C2 |
| Day 2 variant | Spill plus a forklift crossing | Leak plus a lift cart crossing |
| Robots | Picking AMRs, pallet movers | Inspection rovers (thermal + LED camera), drive-swap robots, rack-mover lifts |

## Why this scenario

- **It's a real, everyday problem at both sites.** Spills in fulfillment centers and coolant leaks in liquid-cooled halls are routine. The expensive part is the minutes between "someone sees it" and "everyone knows about it".
- **Every Nebius service does visible work**, and each one appears exactly once with a clear job:

  | Service | Its job in the demo |
  |---|---|
  | Cosmos (dedicated endpoint) | Sees the hazard |
  | Nemotron Ultra (Token Factory) | Decides the novel and safety-critical moments |
  | Nemotron Nano (Token Factory) | Settles routine events and the Day 2 variant |
  | Batch + Data Lab | Replays the day |
  | Serverless Jobs | Dream fan-out, gate, LoRA training |
  | MLflow | Promotion record |
  | vLLM Serverless Endpoint | Serves the improved Nano |

- **It shows the safety boundary in action.** The person in the lane is the one event the fleet is never allowed to settle on its own.
- **It ends in a measured before/after**, not a claim: Ultra calls per 100 events, latency and tokens, from stored runs.

## Operator surface

The NemoFleet Ops console at https://nemofleet.pages.dev/console. It is backed by a Pages Functions API with D1 (calls, alarms, precedents), KV (fading hazard tags, halts, τ) and R2 (raw model bodies). Every number on it comes from those stores, or it shows "—". See [RUNBOOK.md](RUNBOOK.md) for how to drive it.

## Script (3 minutes; acts 1–3 run as one continuous take of at least 60 seconds)

### Act 1 · Day 1, live (0:20–1:05)

The operator clicks **Run scenario**. The Scenario run panel fills in event by event, and every row is a real call.

1. **Routine (10 s).**
   - R07 sends a clear-aisle frame. Nano settles it (`proceed`) in about 2 s.
   - The model call log shows an S1 row with its model ID, latency and tokens.
2. **First sighting (15 s).**
   - R14's camera frame shows the hazard: the spill at the aisle 4 blind corner, or the coolant on the tiles at the row C2 end.
   - **Cosmos3 Super Reasoner on the Token Factory dedicated endpoint** describes it, and its answer appears on R14's camera tile.
   - No precedent exists, so the gate marks the event **novel** and sends it to **Ultra**. Ultra's decision becomes the first precedent.
   - A warning alarm appears.
3. **Spread by handshake (15 s).**
   - R09 passes R14, then R05 passes R09. Each row reads "received precedent (hop 1)", then "(hop 2)", with **0 model calls**.
   - The handshakes show up as fading tags in the console's KV tag list.
4. **The twist (15 s).**
   - A person walks into the aisle near the hazard: the picker in aisle 4, or the technician in cold aisle 2.
   - A person in the lane is always safety-critical, so the gate escalates to **Nemotron Ultra on Token Factory**, whatever the peers say.
   - Ultra returns, for example: halt R03, quarantine A4 (or C2), alert a human.
   - The JSON passes the FleetAction schema check. The quarantine is written to KV with a TTL, and the floor map draws the zone.
   - A critical alarm appears with **Acknowledge**, **Release** and **Review episodes** buttons.

### Act 2 · Night 1 on Nebius, time-lapse with timestamps (1:05–1:55)

The operator clicks **Run Night Shift now**. Real Nebius console footage runs next to the Night Shift panel.

1. **Replay (live today).**
   - Ultra re-judges every Nano decision of the day and flags the confident mistakes.
   - Verdicts appear in **Review episodes**.
   - Production replay uses a Token Factory batch over the Data Lab export; the console button runs the same prompts per-token so it can be shown live.
2. **Dream (planned).**
   - Ultra writes variants of the episode: the hazard plus a vehicle, low light, a different aisle, a second robot arriving late.
   - Dozens of **Serverless Jobs** simulate them in parallel.
3. **Gate (planned).**
   - Each candidate lesson must fix its variants without regressing normal operations.
   - Most are rejected, and the funnel shows it.
4. **Consolidate (planned).**
   - A LoRA fine-tune of Nano runs on an H200 Serverless Job.
   - The **MLflow** run shows it beating yesterday's Nano on the held-out set, and it's promoted on the **vLLM Serverless Endpoint**.

### Act 3 · Day 2, live (1:55–2:25)

1. A different robot, R12, reaches the same spot and meets a combination no robot saw on Day 1: the spill plus a forklift, or the leak plus a lift cart.
2. R12's Nano decision carries the peer precedent, settles the event at or above τ, and reroutes (for example via aisle 3 or cold aisle 3).
3. **Ultra calls for this event: 0.**

### Act 4 · Proof (2:25–2:50)

- The learning curve shows the Ultra share of model decisions run over run, from stored calls.
- The frontier chart from the Serverless Jobs sweep (planned) compares Nano only, Ultra only, the hybrid, and the hybrid with Night Shift on success, latency and cost per task.

### Close (2:50–3:00)

"The edge lives it once. Nebius lives it hundreds of times." Then the repo link and the model IDs.

## What is real, what is simulated

| Part | Status |
|---|---|
| Cosmos, Ultra and Nano calls; schema validation; the escalation gate; safe stop | **Real today.** Every call is in D1 and R2, traceable by run ID |
| Peer handshakes, hazard tags, quarantine, halts, alarms, operator actions | **Real today.** D1 rows and KV tags with TTLs |
| Night Shift Replay | **Real today.** Ultra re-judges Nano decisions; verdicts stored on each call |
| Night Shift Dream, Gate, Consolidate; LoRA; MLflow; vLLM endpoint | Planned: needs the Serverless Jobs runner |
| Warehouse, data center hall, robots, physics, people | Simulated. The floor animation in the console is labelled as a simulation; quarantine zones and halts on it come from live KV tags |
| Camera frames | Rendered sim frames, the same four per site |

## Fallbacks

- **The fine-tune shows no accuracy gain** (headroom test, plan decision 4). Act 3 stays, and R12 handles it from the promoted precedent memory instead. The narration says "consolidated into fleet memory", and the proof becomes Ultra calls, cost and latency.
- **Cosmos endpoint unavailable on recording day.** The run continues: each frame row reads "Cosmos unavailable", the model is told the camera content is unknown, and the novelty and safety gates still route to Ultra. Or show a stored Cosmos response from an earlier session, labelled with its timestamp.
- **Ultra p95 latency is too high to show live.** Live escalations go to Nemotron Super (plan decision 2), and Ultra stays on Night Shift.

## Optional beats (only if the plan's day-14 gate is green)

- **Safety data sheet lookup.** Ultra identifies the substance (solvent or coolant), Tavily retrieves its safety data sheet, and the exclusion radius in the quarantine comes from it. This adds one call to Act 1, step 4.
- **Jetson Orin Nano.** A real camera on a Jetson performs the first sighting in Act 1, step 2.

## Success criteria for the recording

- [ ] At least 60 continuous seconds of modules running (eligibility rule)
- [ ] Each Nebius service appears once, doing its job, with its name on screen
- [ ] Every number on screen comes from a stored run (run ID or storage path in the description)
- [ ] The person-in-lane escalation happens on camera, and the planner, not the model, moves the robots
- [ ] Day 2 shows zero Ultra calls for the unseen variant, or the honest fallback wording
- [ ] The site shown (warehouse or data center) is named on screen
