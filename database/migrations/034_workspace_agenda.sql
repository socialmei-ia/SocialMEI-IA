-- Persistent manual reminders; no messages, workers or provider calls are enabled.
CREATE TABLE IF NOT EXISTS socialmei.agenda_reminders (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    id UUID NOT NULL,
    title VARCHAR(160) NOT NULL CHECK (char_length(btrim(title)) > 0),
    scheduled_for TIMESTAMPTZ NOT NULL,
    notes VARCHAR(1000) NOT NULL DEFAULT '',
    cliente_id BIGINT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'done', 'cancelled')),
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision BETWEEN 1 AND 9007199254740991),
    creation_fingerprint CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(workspace_id, id),
    FOREIGN KEY(workspace_id, cliente_id)
        REFERENCES socialmei.crm_clientes(workspace_id, id)
        ON DELETE SET NULL (cliente_id)
);

CREATE INDEX IF NOT EXISTS ix_agenda_reminders_workspace_schedule
    ON socialmei.agenda_reminders(workspace_id, scheduled_for, id);
