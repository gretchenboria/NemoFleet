-- Fleet memory: precedents are keyed by the map cell where the hazard is, so any robot
-- approaching that cell can reuse the decision instead of calling Ultra again.
ALTER TABLE precedents ADD COLUMN hazard_key TEXT;
CREATE INDEX IF NOT EXISTS precedents_hazard ON precedents (scene, hazard_key, expires_at);
