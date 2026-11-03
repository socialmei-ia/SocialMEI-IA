-- Service bookings are separate from manual reminders; no provider sending.
ALTER TABLE socialmei.crm_produtos ADD COLUMN IF NOT EXISTS duracao_minutos INTEGER;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.crm_produtos'::regclass AND conname='ck_service_duration') THEN
        ALTER TABLE socialmei.crm_produtos ADD CONSTRAINT ck_service_duration
            CHECK (duracao_minutos IS NULL OR (tipo='Serviço' AND duracao_minutos BETWEEN 1 AND 1440));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS socialmei.agenda_resources (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    id UUID NOT NULL,
    nome VARCHAR(160) NOT NULL CHECK (char_length(btrim(nome))>0),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision BETWEEN 1 AND 9007199254740991),
    creation_fingerprint CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(workspace_id,id)
);

CREATE TABLE IF NOT EXISTS socialmei.agenda_appointments (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    id UUID NOT NULL,
    cliente_id BIGINT,
    servico_id BIGINT,
    resource_id UUID NOT NULL,
    client_name VARCHAR(160) NOT NULL,
    service_name VARCHAR(160) NOT NULL,
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes BETWEEN 1 AND 1440),
    price NUMERIC NOT NULL CHECK (price>=0),
    scheduled_for TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    notes VARCHAR(1000) NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done','cancelled')),
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision BETWEEN 1 AND 9007199254740991),
    creation_fingerprint CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(workspace_id,id),
    CHECK (ends_at=scheduled_for+duration_minutes*INTERVAL '1 minute'),
    FOREIGN KEY(workspace_id,cliente_id) REFERENCES socialmei.crm_clientes(workspace_id,id) ON DELETE SET NULL(cliente_id),
    FOREIGN KEY(workspace_id,servico_id) REFERENCES socialmei.crm_produtos(workspace_id,id) ON DELETE SET NULL(servico_id),
    FOREIGN KEY(workspace_id,resource_id) REFERENCES socialmei.agenda_resources(workspace_id,id)
);
CREATE INDEX IF NOT EXISTS ix_appointments_resource_schedule ON socialmei.agenda_appointments(workspace_id,resource_id,scheduled_for,ends_at) WHERE status!='cancelled';

CREATE TABLE IF NOT EXISTS socialmei.agenda_appointment_history (
    workspace_id BIGINT NOT NULL,
    appointment_id UUID NOT NULL,
    revision BIGINT NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','done','cancelled')),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(workspace_id,appointment_id,revision),
    FOREIGN KEY(workspace_id,appointment_id) REFERENCES socialmei.agenda_appointments(workspace_id,id) ON DELETE CASCADE
);
