CREATE TABLE IF NOT EXISTS socialmei.agenda_appointment_reminder_preferences (
    workspace_id BIGINT NOT NULL,
    appointment_id UUID NOT NULL,
    appointment_revision BIGINT NOT NULL CHECK (appointment_revision > 0),
    revision BIGINT NOT NULL CHECK (revision > 0),
    lead_minutes INTEGER NOT NULL CHECK (lead_minutes IN (30, 60, 120, 1440)),
    enabled BOOLEAN NOT NULL,
    consented_at TIMESTAMPTZ NOT NULL,
    consented_by BIGINT NOT NULL CHECK (consented_by > 0),
    revoked_at TIMESTAMPTZ,
    revoked_by BIGINT CHECK (revoked_by > 0),
    PRIMARY KEY (workspace_id, appointment_id, appointment_revision),
    FOREIGN KEY (workspace_id, appointment_id)
        REFERENCES socialmei.agenda_appointments(workspace_id, id) ON DELETE CASCADE,
    CHECK ((enabled AND revoked_at IS NULL AND revoked_by IS NULL)
        OR (NOT enabled AND revoked_at IS NOT NULL AND revoked_by IS NOT NULL))
);

DO $grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='socialmei_candidate040') THEN
        GRANT SELECT, INSERT, UPDATE ON socialmei.agenda_appointment_reminder_preferences TO socialmei_candidate040;
    END IF;
END
$grants$;
