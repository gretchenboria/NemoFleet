# Product review: is the console a coherent product?

Written 2026-10-11 as a technical product manager's review of the live console. Short answer: not yet. It proves the technology and explains the idea, but it is organised around how the system works, not around what an operator has to get done.

## Verdict

- **What it is today:** a model-operations showcase. It shows that Ultra decides once, memory reuses it, and Nano learns overnight, with real numbers.
- **What is missing:** a job to do. Nobody can run a shift from it. The floor map moves robots that carry no information, peer handoff is narrated rather than needed, and the one real asset the product creates, the fleet's stored decisions, cannot be seen, edited or revoked.
- **The value proposition is stated in system terms** (Ultra calls avoided, agreement with Ultra) when the buyer's terms are: fewer zone-wide halts, nobody hurt, fewer interruptions for the operator, a known cost per decision, and an audit trail.

## Who it is for

| Persona | What they need | Served today? |
|---|---|---|
| **Hall operations lead** (primary). Runs a shift in a data hall with a robot fleet. | Know what needs them now, decide quickly with evidence, keep the hall moving, hand over cleanly. | Partly: alarms exist, but there is no incident view and no way to correct the fleet. |
| **Fleet reliability engineer** (secondary). Owns the models and the autonomy level. | See whether a new adapter is better, promote or roll back, set how much the fleet settles on its own. | Mostly: the Night Shift tables serve this person. There is no promote or rollback. |
| **Site safety and compliance lead.** | Who decided what, on what evidence, and what changed afterwards. | No: the call log is raw calls, not a record of decisions. |

## The operator's journey, and where it breaks

1. **A robot meets something.** The operator should see one incident: where, what the camera saw, what was decided, by which model, and what the fleet did. *Today:* that is spread over the event list, the alarm list, the camera strip and the call log.
2. **Decide.** Accept the decision, or override it. *Today:* acknowledge and release only. An override is impossible.
3. **Teach.** The operator's correction should become the fleet's stored decision for that place. *Today:* only Ultra can write to fleet memory.
4. **Contain.** Quarantine with an expiry, see which robots are affected. *Today:* works, but the zone is fixed by the scenario.
5. **Clear.** Mark it resolved; the stored decision expires or is kept. *Today:* release clears tags; stored decisions simply time out.
6. **Morning review.** "What did the fleet learn last night, and do I approve it?" *Today:* the evidence is there; the decision is not.

## Pain points worth targeting

1. **Zone-wide halts** for hazards one robot already understood. This is the headline.
2. **The same question, again.** Every robot asks about the same spill. Fleet memory fixes this, and it is measured.
3. **Confidence nobody can trust.** Today's Nano reports high confidence on 99% of events. The tuned model's own probability separates right from wrong (it settles 61% of unseen-hazard events with 1 error in 201). This is the most defensible technical claim in the product.
4. **People.** Any person in the lane must reach a human-grade decision every time.
5. **Unknown cost and no audit trail.**

## Feature review

| Area | Today | Gap |
|---|---|---|
| Incidents | Alarms with acknowledge and release | No single incident record linking sighting, evidence, decision, actions and outcome |
| Fleet memory (stored decisions) | Created by Ultra, reused by Nano, expire on a timer | Invisible. No list, edit, expire, pin, revoke or scope. This is the product's core object |
| Autonomy policy | One threshold slider on stated confidence | Stated confidence does not work. Should be "acceptable error rate when settling without Ultra", per hazard class, with people locked to always escalate |
| Model lifecycle | Adapters trained and evaluated offline | No registry, promotion, rollback or serving; the tuned Nano is not in the loop |
| Floor map | Simulated motion | Carries no state. Should show stored decisions, quarantines and where robots asked for help, per cell, clickable |
| Peer handoff | Counted and animated | An operator does not care how decisions travel, only whether every robot has them: show coverage and time to fleet-wide awareness |
| Event intake | "Run scenario" button | A demo affordance. Production needs an events endpoint that robots post to; the scenario runner becomes a labelled rehearsal mode |
| Night Shift | Before and after tables | Should end in a decision: promote or hold, with the evidence beside the button |

## What can be created, read, changed and removed

| Object | Create | Read | Update | Delete |
|---|---|---|---|---|
| Incident | by robots (today: scenario) | list only | acknowledge | release |
| Stored decision | Ultra only | no | no | timer only |
| Quarantine | yes | yes | no | yes |
| Autonomy policy | no | threshold | threshold | no |
| Adapter | offline | results | no | no |
| Site, cells, robots, hazard classes | in files | partly | no | no |

A production console needs every row filled for the first three objects, and "read, update" for the rest.

## Configuration that should be atomic

Site and map cells; robot registry; hazard classes; the action vocabulary; expiry per hazard class; the autonomy target per hazard class; escalation contacts; which adapter is serving. Today these live in scenario files and code.

## Innovation: where this could be new

1. **Case law for robots.** Every decision cites the stored decision it relied on; operators can read, correct and revoke them; a correction is a new precedent. Stored decisions become an inspectable, human-governed policy that sits between a rule book and a model. Shared across halls and sites, each site's incidents make every other site's fleet safer, which is a network effect no single-site system has.
2. **Autonomy as a service level.** The operator sets a target such as "at most 1 in 100 self-settled decisions may differ from Ultra". The gate uses the model's own probability, which we have measured, and the console shows what that target costs in Ultra calls. No other knob.
3. **Every resolved incident becomes a test.** Night Shift trains on yesterday, and no adapter is promoted unless it still passes every past incident. The morning brief reads: learned 4 things, regressed on none, promote?
4. **Rehearsal before reality.** Generate variants of last night's incidents (the Cosmos job already makes the frames) and decide them overnight, so the first real sighting of a variant already has a stored decision.
5. **Anticipation, not reaction.** The person-in-the-way model reads the planner's path, so escalation can happen before the robot arrives.

## Build order

1. **Incident record with override.** One view per incident; accept or override; an override writes a stored decision.
2. **Decision book.** List, inspect, edit expiry, pin and revoke stored decisions; the map shows them per cell.
3. **Autonomy target and adapter promotion.** Replace the threshold slider with an error-rate target backed by the measured gate; promote or hold the tuned adapter with the evidence shown; serve it.
4. **Events endpoint.** Robots post events; "Run scenario" becomes a rehearsal mode.

Items 1 and 2 turn the console from a showcase into a tool. Item 3 turns the fine-tuning work into a product feature. Item 4 removes the last piece of demo mode.

## Implementation status (2026-10-12)

All four items above—plus configurable alarm rules CRUD, dual-adapter serving, and the interactive Spatial Command & Fleet Memory Map—are implemented and covered by `tests/qa.cjs`:

| Item | Implementation |
|---|---|
| **1. Incident record with override** | `GET /api/incident`, `POST /api/incident/override`, and `#incident` panel in `site/src/console.body.html`. Links alarm → sighting → camera perception → model decision → fleet actions → stored decision. Operator overrides write a new `source='operator'` precedent for the cell (and never cache person-involved incidents). |
| **2. Decision book (Fleet memory)** | `GET /api/decisions`, `POST /api/decisions/update`, `POST /api/decisions/revoke`, and `#pane-dec`. Shows `Known by n of m robots`, reuse count, and TTL with **Keep (Pin)**, **Keep longer (+10m)**, and **Stop using (Revoke)**, plus the unified **Recent event decisions across the fleet (Nano, Fleet Memory & Ultra)** table. |
| **3. Autonomy target & dual-adapter promotion** | `POST /api/autonomy`, `POST /api/adapter`, `tools/night_shift/publish.py`, `tools/ego_mix/serve.py`, and `tools/ego_mix/sky_serve.yaml`. Serves both `decide-1` (decisions + action-token probability gate) and `plan-1` (`in_way` 5 s planned-path safety trigger with calibrated threshold `-0.75`) on one spot H200. |
| **4. Events intake (`POST /api/events`)** | Authenticated event intake (`EVENTS_TOKEN`) running the full perception → `in_way` trigger → fleet memory → Nano/Ultra gate → alarm rule evaluation pipeline. |
| **5. Configurable alarm rules CRUD** | `0007_alarm_rules.sql`, `GET /api/rules`, `POST /api/rules/create`, `/update`, `/delete`, `/reset`, and `#pane-rules` UI. Enforces custom and default alarm triggers (`person_in_lane`, `quarantine_action`, `alert_human_action`, `low_confidence`, `high_severity`, `any_hazard`) live in `runEvent`. |
| **6. Spatial Command & Fleet Memory Map** | `#floor` + `#map-hud` in `site/src/console.body.html`, plus `unhalt` and `release_zone` in `POST /api/actions`. Interactive robot telemetry pills, clickable robots and cells, Fleet Memory sync halos (`MEM`), peer-to-peer antennation arcs, and one-click **Halt / Resume robot** and **Quarantine / Release cell**. |
