-- Decision book and incident record.
-- precedents: operators can write stored decisions (source 'operator'), pin them (never expire) and revoke them.
-- SQLite cannot alter a CHECK, so rebuild the table (as in 0004) and copy every row.
PRAGMA defer_foreign_keys = true;
CREATE TABLE precedents_new (
  id            TEXT PRIMARY KEY,
  scene         TEXT NOT NULL CHECK (scene IN ('warehouse', 'datacenter', 'sanfrancisco')),
  situation     TEXT NOT NULL,
  decision_json TEXT NOT NULL,
  source        TEXT NOT NULL CHECK (source IN ('ultra', 'peer', 'night_shift', 'operator')),
  model         TEXT,
  confidence    REAL CHECK (confidence BETWEEN 0 AND 1),
  hops          INTEGER NOT NULL DEFAULT 0,
  safety        INTEGER NOT NULL DEFAULT 0,
  run_id        TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  expires_at    TEXT,
  superseded_by TEXT REFERENCES precedents_new(id),
  hazard_key    TEXT,
  pinned        INTEGER NOT NULL DEFAULT 0,    -- 1 = never expires until unpinned
  revoked_at    TEXT,                          -- set = never reused again; the row stays for the audit trail
  alarm_id      TEXT                           -- the incident an operator decision was written from
);
INSERT INTO precedents_new (id, scene, situation, decision_json, source, model, confidence, hops, safety, run_id, created_at, expires_at, superseded_by, hazard_key)
  SELECT id, scene, situation, decision_json, source, model, confidence, hops, safety, run_id, created_at, expires_at, superseded_by, hazard_key FROM precedents;
DROP TABLE precedents;
ALTER TABLE precedents_new RENAME TO precedents;
CREATE INDEX IF NOT EXISTS precedents_scene_live ON precedents (scene, expires_at);
CREATE INDEX IF NOT EXISTS precedents_hazard ON precedents (scene, hazard_key, expires_at);

-- alarms: what led to the alarm, recorded when it is raised.
ALTER TABLE alarms ADD COLUMN event_index   INTEGER;           -- index of the event in its run
ALTER TABLE alarms ADD COLUMN event_json    TEXT;              -- {robot, where, text, cell, kind, frame}
ALTER TABLE alarms ADD COLUMN safety        INTEGER NOT NULL DEFAULT 0;  -- 1 = a person is involved
ALTER TABLE alarms ADD COLUMN call_id       INTEGER;           -- calls.id of the deciding model call
ALTER TABLE alarms ADD COLUMN perception_id TEXT;              -- perception.id for this event
ALTER TABLE alarms ADD COLUMN precedent_id  TEXT;              -- stored decision this event created or reused
ALTER TABLE alarms ADD COLUMN precedent_link TEXT;             -- 'created' | 'reused'

-- actions: tie each fleet action to its event and, for operator actions, to the alarm.
ALTER TABLE actions ADD COLUMN event_index INTEGER;
ALTER TABLE actions ADD COLUMN alarm_id    TEXT;
CREATE INDEX IF NOT EXISTS actions_run_event ON actions (run_id, event_index);
CREATE INDEX IF NOT EXISTS actions_alarm ON actions (alarm_id);
