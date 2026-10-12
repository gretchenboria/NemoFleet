-- Alarm rules per scene: CRUD for routing, severity, automatic response and operator guidance.
CREATE TABLE IF NOT EXISTS alarm_rules (
  id              TEXT PRIMARY KEY,
  scene           TEXT NOT NULL CHECK (scene IN ('warehouse', 'datacenter', 'sanfrancisco')),
  name            TEXT NOT NULL,
  sev             TEXT NOT NULL CHECK (sev IN ('crit', 'warn', 'info')),
  when_kind       TEXT NOT NULL CHECK (when_kind IN ('safety', 'hazard', 'unknown_hazard', 'operator', 'custom')),
  match_text      TEXT,
  when_label      TEXT NOT NULL,
  response        TEXT NOT NULL,
  operator_action TEXT NOT NULL,
  enabled         INTEGER NOT NULL DEFAULT 1,
  builtin         INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS alarm_rules_scene ON alarm_rules (scene, created_at);
