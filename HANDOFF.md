# Handoff: make the console work end to end

Read [PROJECT_BRIEFING.md](PROJECT_BRIEFING.md) first.

**What the user expects:** every console button really works, end to end. No "example only" messages. Any number shown comes from real data, or the console shows "—" or "no data yet". They tried "Review episodes" and "Run Night Shift" and were frustrated when the console said "example only".

## State at handoff

**Committed:**
- `functions/api/[[path]].js`: the backend API (routes below). Never deployed, never run.
- `cloudflare/migrations/0002_console.sql`: adds `alarms` and `actions` tables, plus `calls.scene`, `calls.decision_json` and `calls.replay_json`. **Not applied.**
- `config/models.yaml` filled in by `tools/preflight.cjs --write`.
- Scenarios with data-center-appropriate devices and tasks.

**Not done:** steps 1–6 below.

**Cosmos:** the endpoint was starting at handoff. It bills about $0.37/min; remind the user to stop it after testing.

## API routes (`functions/api/[[path]].js`)

| Route | What it does |
|---|---|
| `GET /api/health` | Whether D1, KV, R2 and the Nebius key are available, plus the model ids (from `/config/models.json`) |
| `GET /api/state?scene=` | Alarms, actions, calls, perception, precedent counts, night_shift rows, KV tags |
| `POST /api/alarms/ack {id}` | Toggles the alarm between open and acked |
| `POST /api/alarms/release {id}` | Releases the alarm and deletes the scene's KV zone tags |
| `POST /api/actions {scene, type, ...}` | `quarantine_zone{zone}` · `halt{robot}` · `broadcast_hazard{message}` · `rollback_nano` · `escalate` (calls Ultra) |
| `POST /api/scenario/start {scene}` | Returns `{run_id, events}` |
| `POST /api/scenario/step {scene, run_id, i}` | Runs one event: Cosmos, then Nano/Ultra through the gate; writes D1, R2, KV and alarms. ≤ 30 s per call |
| `POST /api/scenario/finish {run_id}` | Writes the run totals |
| `GET /api/episodes?scene=` | The last 50 Nano/Ultra decisions with replay verdicts |
| `POST /api/night-shift/replay {scene}` | Ultra re-judges up to 4 Nano decisions per call; returns `remaining`. Call it in a loop until `remaining` is 0 |

The function reads `/config/models.json` and `/scenarios/*.json` from `env.ASSETS`, so the site build must publish them (step 1).

## Next steps, in order

1. **Wire Pages to the stores.**
   - Create a root `wrangler.toml`:
     - `name = "nemofleet"`
     - `pages_build_output_dir = "site/dist"`
     - `compatibility_date = "2026-10-01"`
     - `[[d1_databases]]` binding `MEMORY`, `nemofleet-memory`, id `eb9d266f-5753-45da-9378-5797b5cf1fdc`
     - `[[kv_namespaces]]` binding `TAGS`, id `51e4053c22464b5dbe31b0069ed10281`
     - `[[r2_buckets]]` binding `RUNS`, bucket `nemofleet-runs`
   - In `site/build.cjs`:
     - copy `scenarios/*.json` → `dist/scenarios/`
     - write `dist/config/models.json` from `require('../tools/tf.cjs').models()`
   - Deploy from the repo root so Wrangler picks up `./functions`.
2. **Apply the migration and set the secret.**
   - `npx wrangler d1 migrations apply nemofleet-memory --remote -c cloudflare/wrangler.jsonc`
   - Set the key as a Pages secret: `printf %s "$NEBIUS_API_KEY" | npx wrangler pages secret put NEBIUS_API_KEY --project-name nemofleet`
3. **Wire the console** (`site/src/console.body.html`; keep the scratch copy and artifact in sync if republishing).
   - **Mode detection:** on load, `fetch('/api/health')`.
     - If it responds → LIVE mode.
     - If not (for example on the claude.ai artifact) → keep the example data, but label it clearly.
   - **LIVE mode, per scene, via `/api/state`:**
     - **Alarms:** Acknowledge and Release call the API. Add a "Review episodes" button.
     - **Call log:** rows from real `calls`.
     - **Camera tiles:** the latest `perception` per frame.
     - **KPIs:** computed from `calls`: settled share, Ultra per 100, p50 latency, tokens. Show "—" when there's no data.
     - **Night Shift cards:** from `night_shift` rows. Dream, Gate and Consolidate show "not built yet".
     - **Services panel:** health from `/api/health`.
   - **Buttons:**
     - **Run scenario** (new primary button): `start` → loop `step` for each event, updating the UI live → `finish`.
     - **Run Night Shift now:** loop `night-shift/replay`.
     - **Action buttons:** `/api/actions`. Re-wire them with `cloneNode` to drop the old toast listeners.
     - **Stop Cosmos endpoint:** link to the Token Factory console. There is no verified API for this.
     - **Review episodes:** opens a panel listing `/api/episodes`.
   - **Remove fake numbers:** take out the static example numbers in the Night Shift, learning curve, spend and peer stat panels, or replace them with live values.
   - The floor animation stays a labelled simulation.
4. **Extend QA** (`tests/qa.cjs`).
   - The local test server can't run Functions. Either use `npx wrangler pages dev site/dist` for an API smoke test, or test against the deployed preview URL.
   - Add checks:
     - `/api/health` returns `d1`, `kv` and `r2` true.
     - An alarm ack round-trip.
     - A `/api/actions` quarantine writes a KV tag.
     - The console has no "example only" text in LIVE mode.
5. **Run end to end once Cosmos shows Ready.**
   - Click Run scenario for each scene on https://nemofleet.pages.dev/console, then Review episodes, then Run Night Shift.
   - Record the real latencies, cold start and cost in `docs/FEEDBACK.md`.
   - **Then remind the user to stop Cosmos.**
6. **Docs** (the user wants them fully updated).
   - Re-theme or extend these for the data center scene: `DEMO.md`, the architecture PDF (`docs/build_architecture_pdf.py`), the video (`docs/video/scenes.json` + `make_video.js`).
   - Regenerate the PDFs: `node docs/build_doc_pdfs.cjs`.
   - Update RUNBOOK with console usage.

## Rules the user has set (keep to them)

- Commit and deploy only after `node tests/qa.cjs` exits 0.
- Never fabricate results. Cosmos tiles show only stored real responses; QA enforces this.
- No company branding in renders (no Google, Nebius or NVIDIA logos).
- The biology analogy stays light. Lead with the technical design.
- Keep warehouse **and** data center; the user picks between them.
- Wrangler: the `nemofleet` Pages project already exists, so never pass `--force` again.
- `~/package.json` has `"type": "module"`, so new Node scripts should be `.cjs`.
- Python pip is broken in this sandbox. Use Node: `docs/video/node_modules` has `puppeteer-core` and `marked`.
