-- Durable requests, never plaintext codes or SMTP credentials.
CREATE TABLE IF NOT EXISTS socialmei.auth_recuperacao_envios (
    user_id BIGINT PRIMARY KEY REFERENCES socialmei.users(id) ON DELETE CASCADE,
    generation UUID NOT NULL,
    status VARCHAR(12) NOT NULL CHECK (status IN ('pending','processing','sent','uncertain','expired')),
    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_auth_recuperacao_envios_pending ON socialmei.auth_recuperacao_envios(queued_at,user_id) WHERE status='pending';
COMMENT ON TABLE socialmei.auth_recuperacao_envios IS 'Durable recovery delivery requests. Processing interrupted or SMTP errors are uncertain; never retried automatically.';
