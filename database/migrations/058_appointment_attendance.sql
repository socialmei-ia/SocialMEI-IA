ALTER TABLE socialmei.agenda_appointments
    ADD COLUMN IF NOT EXISTS attendance TEXT CHECK (attendance IN ('confirmed','no_show'));

CREATE TABLE IF NOT EXISTS socialmei.agenda_attendance_events (
    workspace_id BIGINT NOT NULL,
    operation_id UUID NOT NULL,
    appointment_id UUID NOT NULL,
    expected_revision BIGINT NOT NULL CHECK (expected_revision > 0),
    revision BIGINT NOT NULL CHECK (revision = expected_revision + 1),
    status TEXT NOT NULL CHECK (status IN ('confirmed','no_show')),
    scheduled_for TIMESTAMPTZ NOT NULL,
    actor_id BIGINT NOT NULL CHECK (actor_id > 0),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id,operation_id),
    UNIQUE (workspace_id,appointment_id,revision),
    FOREIGN KEY (workspace_id,appointment_id)
        REFERENCES socialmei.agenda_appointments(workspace_id,id) ON DELETE CASCADE
);

CREATE OR REPLACE FUNCTION socialmei.reset_appointment_attendance() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.scheduled_for IS DISTINCT FROM OLD.scheduled_for OR NEW.status='cancelled' THEN
        NEW.attendance := NULL;
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS reset_appointment_attendance ON socialmei.agenda_appointments;
CREATE TRIGGER reset_appointment_attendance
BEFORE UPDATE OF scheduled_for,status ON socialmei.agenda_appointments
FOR EACH ROW EXECUTE FUNCTION socialmei.reset_appointment_attendance();

DO $grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='socialmei_candidate040') THEN
        GRANT SELECT, INSERT ON socialmei.agenda_attendance_events TO socialmei_candidate040;
    END IF;
END
$grants$;
