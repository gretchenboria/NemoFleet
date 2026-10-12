-- Fleet awareness: which robot holds each stored decision.
ALTER TABLE precedents ADD COLUMN robot     TEXT;   -- the robot that met the hazard (ultra rows) or received the copy (peer rows)
ALTER TABLE precedents ADD COLUMN origin_id TEXT;   -- peer rows: the stored decision this copy came from
CREATE INDEX IF NOT EXISTS precedents_origin ON precedents (origin_id);
