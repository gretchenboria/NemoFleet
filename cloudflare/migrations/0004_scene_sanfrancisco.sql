-- Experimental San Francisco robotaxi scene: precedents.scene was CHECKed to warehouse/datacenter.
-- SQLite cannot alter a CHECK, so rebuild the table with the third scene and copy every row.
PRAGMA defer_foreign_keys = true;
CREATE TABLE precedents_new (
  id            TEXT PRIMARY KEY,
  scene         TEXT NOT NULL CHECK (scene IN ('warehouse', 'datacenter', 'sanfrancisco')),
  situation     TEXT NOT NULL,
  decision_json TEXT NOT NULL,
  source        TEXT NOT NULL CHECK (source IN ('ultra', 'peer', 'night_shift')),
  model         TEXT,
  confidence    REAL CHECK (confidence BETWEEN 0 AND 1),
  hops          INTEGER NOT NULL DEFAULT 0,
  safety        INTEGER NOT NULL DEFAULT 0,
  run_id        TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  expires_at    TEXT,
  superseded_by TEXT REFERENCES precedents_new(id),
  hazard_key    TEXT
);
INSERT INTO precedents_new (id, scene, situation, decision_json, source, model, confidence, hops, safety, run_id, created_at, expires_at, superseded_by, hazard_key)
  SELECT id, scene, situation, decision_json, source, model, confidence, hops, safety, run_id, created_at, expires_at, superseded_by, hazard_key FROM precedents;
DROP TABLE precedents;
ALTER TABLE precedents_new RENAME TO precedents;
CREATE INDEX IF NOT EXISTS precedents_scene_live ON precedents (scene, expires_at);
CREATE INDEX IF NOT EXISTS precedents_hazard ON precedents (scene, hazard_key, expires_at);
