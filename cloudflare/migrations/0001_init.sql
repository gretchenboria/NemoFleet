-- NemoFleet memory (Cloudflare D1). Large bodies (prompts, raw outputs, frames) live in R2; rows keep the R2 key.

-- Fleet memory: what the fleet has learned, with provenance (ARCHITECTURE.md, peer safety rules).
CREATE TABLE IF NOT EXISTS precedents (
  id            TEXT PRIMARY KEY,
  scene         TEXT NOT NULL CHECK (scene IN ('warehouse', 'datacenter')),
  situation     TEXT NOT NULL,                 -- normalized description of the event
  decision_json TEXT NOT NULL,                 -- validated FleetAction decision
  source        TEXT NOT NULL CHECK (source IN ('ultra', 'peer', 'night_shift')),
  model         TEXT,                          -- model id that produced it (null for peer copies)
  confidence    REAL CHECK (confidence BETWEEN 0 AND 1),
  hops          INTEGER NOT NULL DEFAULT 0,    -- 0 = decided here; +1 per handshake
  safety        INTEGER NOT NULL DEFAULT 0,    -- 1 = safety-critical: never settled by peers
  run_id        TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  expires_at    TEXT,                          -- TTL; expired rows are ignored
  superseded_by TEXT REFERENCES precedents(id)
);
CREATE INDEX IF NOT EXISTS precedents_scene_live ON precedents (scene, expires_at);

-- One row per scenario run (real or dry).
CREATE TABLE IF NOT EXISTS runs (
  id          TEXT PRIMARY KEY,                -- e.g. hall-b-coolant-leak-2026-10-08T...
  scenario    TEXT NOT NULL,
  scene       TEXT NOT NULL,
  dry_run     INTEGER NOT NULL DEFAULT 0,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  totals_json TEXT,
  r2_prefix   TEXT                             -- runs/<id>/ in the nemofleet-runs bucket
);

-- Index of every model call (bodies in R2). This is Night Shift's replay input.
CREATE TABLE IF NOT EXISTS calls (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id            TEXT REFERENCES runs(id),
  ts                TEXT NOT NULL,
  tier              TEXT NOT NULL CHECK (tier IN ('perception', 'nano', 'ultra')),
  model             TEXT NOT NULL,
  robot             TEXT,
  event             TEXT,
  latency_ms        INTEGER,
  prompt_tokens     INTEGER,
  completion_tokens INTEGER,
  valid             INTEGER,                   -- passed FleetAction schema
  r2_key            TEXT
);
CREATE INDEX IF NOT EXISTS calls_run ON calls (run_id);
CREATE INDEX IF NOT EXISTS calls_tier_ts ON calls (tier, ts);

-- Cosmos perception results shown on the console camera tiles.
CREATE TABLE IF NOT EXISTS perception (
  id          TEXT PRIMARY KEY,                -- <scene>/<frame>/<called_at>
  scene       TEXT NOT NULL,
  frame       TEXT NOT NULL,
  robot       TEXT,
  model       TEXT NOT NULL,
  called_at   TEXT NOT NULL,
  latency_ms  INTEGER,
  result_json TEXT,
  raw_r2_key  TEXT
);
CREATE INDEX IF NOT EXISTS perception_scene ON perception (scene, called_at);

-- Night Shift pipeline stages (replay, dream, gate, consolidate).
CREATE TABLE IF NOT EXISTS night_shift (
  id           TEXT PRIMARY KEY,               -- <night>/<stage>
  night        TEXT NOT NULL,                  -- e.g. night-07
  stage        TEXT NOT NULL CHECK (stage IN ('replay', 'dream', 'gate', 'consolidate')),
  status       TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'skipped')),
  metrics_json TEXT,
  mlflow_run   TEXT,
  started_at   TEXT,
  finished_at  TEXT
);
