-- Console backend: alarms, operator/model actions, and episode fields on calls.
CREATE TABLE IF NOT EXISTS alarms (
  id         TEXT PRIMARY KEY,
  scene      TEXT NOT NULL,
  sev        TEXT NOT NULL CHECK (sev IN ('crit', 'warn', 'info')),
  title      TEXT NOT NULL,
  meta       TEXT,
  status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acked', 'released')),
  run_id     TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS alarms_scene ON alarms (scene, status, created_at);

CREATE TABLE IF NOT EXISTS actions (
  id           TEXT PRIMARY KEY,
  scene        TEXT NOT NULL,
  type         TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  source       TEXT NOT NULL CHECK (source IN ('operator', 'nano', 'ultra')),
  run_id       TEXT,
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS actions_scene ON actions (scene, created_at);

ALTER TABLE calls ADD COLUMN scene TEXT;
ALTER TABLE calls ADD COLUMN decision_json TEXT;
ALTER TABLE calls ADD COLUMN replay_json TEXT;   -- Night Shift replay verdict from Ultra
