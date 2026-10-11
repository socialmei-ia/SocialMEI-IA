-- Lançamentos compartilhados; exclusão lógica e recuperação de operações.
CREATE TABLE IF NOT EXISTS socialmei.crm_financeiro (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    cliente_id BIGINT REFERENCES socialmei.crm_clientes(id) ON DELETE SET NULL,
    descricao VARCHAR(240) NOT NULL,
    pessoa VARCHAR(160) NOT NULL DEFAULT '',
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('receita', 'despesa')),
    valor NUMERIC(15,2) NOT NULL CHECK (valor >= 0),
    vencimento DATE NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('aberto', 'atrasado', 'pago')),
    data_pagamento DATE,
    importada BOOLEAN NOT NULL DEFAULT false,
    excluida BOOLEAN NOT NULL DEFAULT false,
    versao BIGINT NOT NULL DEFAULT 1 CHECK (versao > 0),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status = 'pago' OR data_pagamento IS NULL)
);
CREATE INDEX IF NOT EXISTS ix_crm_financeiro_workspace_vencimento
    ON socialmei.crm_financeiro (workspace_id, vencimento DESC, id);
CREATE TABLE IF NOT EXISTS socialmei.crm_financeiro_operacoes (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    operation_id UUID NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    resposta JSONB NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, operation_id)
);
CREATE TABLE IF NOT EXISTS socialmei.crm_financeiro_importacoes (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    origem UUID NOT NULL,
    local_id BIGINT NOT NULL CHECK (local_id >= 0 AND local_id <= 9007199254740991),
    lancamento_id BIGINT NOT NULL REFERENCES socialmei.crm_financeiro(id),
    fingerprint CHAR(64) NOT NULL,
    snapshot JSONB NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, origem, local_id)
);
