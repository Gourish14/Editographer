-- The 360 clip a follow point was tapped on (specs/08-osmo360.md rule 5, CR-014).
-- Null means the first 360 clip, as before.
ALTER TABLE render_job ADD COLUMN follow_asset_id UUID;
