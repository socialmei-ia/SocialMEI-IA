-- Catálogo da gestão compartilhada, sem alterar tabelas legadas de atendimento.
CREATE TABLE IF NOT EXISTS socialmei.crm_produtos (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    nome VARCHAR(160) NOT NULL,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('Produto', 'Serviço')),
    preco NUMERIC NOT NULL CHECK (preco >= 0),
    custo NUMERIC NOT NULL DEFAULT 0 CHECK (custo >= 0),
    estoque BIGINT CHECK (estoque >= 0 AND estoque <= 9007199254740991),
    minimo BIGINT CHECK (minimo >= 0 AND minimo <= 9007199254740991),
    status VARCHAR(30) NOT NULL DEFAULT 'Ativo',
    versao BIGINT NOT NULL DEFAULT 1 CHECK (versao > 0),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((tipo = 'Produto' AND estoque IS NOT NULL AND minimo IS NOT NULL)
        OR (tipo = 'Serviço' AND estoque IS NULL AND minimo IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_crm_produtos_workspace_nome
    ON socialmei.crm_produtos (workspace_id, LOWER(nome));

CREATE TABLE IF NOT EXISTS socialmei.crm_produto_importacoes (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    origem UUID NOT NULL,
    local_id BIGINT NOT NULL CHECK (local_id >= 0 AND local_id <= 9007199254740991),
    produto_id BIGINT REFERENCES socialmei.crm_produtos(id) ON DELETE SET NULL,
    fingerprint CHAR(64) NOT NULL,
    snapshot JSONB NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, origem, local_id)
);
