-- Identidade estável do dataset, independente dos IDs gerados pelo navegador.
CREATE TABLE IF NOT EXISTS socialmei.crm_cliente_importacoes (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    origem UUID NOT NULL,
    local_id BIGINT NOT NULL CHECK (local_id >= 0 AND local_id <= 9007199254740991),
    cliente_id BIGINT REFERENCES socialmei.crm_clientes(id) ON DELETE SET NULL,
    fingerprint CHAR(64) NOT NULL,
    snapshot JSONB NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, origem, local_id)
);

COMMENT ON TABLE socialmei.crm_cliente_importacoes IS
    'Mapeamento e snapshot de importação; cliente_id nulo impede recriar cliente excluído.';
