-- Uma transferência inicial por workspace; impede duplicação com outra origem.
CREATE TABLE IF NOT EXISTS socialmei.crm_transferencias (
    workspace_id BIGINT PRIMARY KEY REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    origem UUID NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    snapshot JSONB NOT NULL,
    resposta JSONB NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
