-- "Render tonight" start time (specs/09-local-setup.md) and the subject-to-follow tap point
-- (specs/08-osmo360.md#ui-additions).

ALTER TABLE render_job ADD COLUMN start_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE render_job ADD COLUMN follow_x DOUBLE PRECISION;
ALTER TABLE render_job ADD COLUMN follow_y DOUBLE PRECISION;
ALTER TABLE render_job ADD COLUMN follow_time_sec DOUBLE PRECISION;

-- A queued job is not handed to the worker before not_before.
ALTER TABLE job ADD COLUMN not_before TIMESTAMP WITH TIME ZONE;
