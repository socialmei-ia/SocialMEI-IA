-- Vendas com snapshots históricos; operações e estoque são gravados atomicamente.
CREATE TABLE IF NOT EXISTS socialmei.crm_vendas (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    cliente_id BIGINT REFERENCES socialmei.crm_clientes(id) ON DELETE SET NULL,
    produto_id BIGINT REFERENCES socialmei.crm_produtos(id) ON DELETE SET NULL,
    cliente VARCHAR(160) NOT NULL,
    item VARCHAR(160) NOT NULL,
    tipo_item VARCHAR(20) CHECK (tipo_item IN ('Produto', 'Serviço')),
    data DATE NOT NULL,
    quantidade BIGINT NOT NULL CHECK (quantidade > 0 AND quantidade <= 9007199254740991),
    preco NUMERIC(15,2) CHECK (preco >= 0),
    desconto NUMERIC(15,2) NOT NULL DEFAULT 0 CHECK (desconto >= 0),
    valor NUMERIC(15,2) NOT NULL CHECK (valor >= 0),
    pagamento VARCHAR(40) NOT NULL,
    observacao TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL CHECK (status IN ('Rascunho', 'Pendente', 'Pago', 'Cancelado')),
    estoque_aplicado BOOLEAN NOT NULL DEFAULT false,
    importada BOOLEAN NOT NULL DEFAULT false,
    excluida BOOLEAN NOT NULL DEFAULT false,
    versao BIGINT NOT NULL DEFAULT 1 CHECK (versao > 0),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (importada OR preco IS NOT NULL),
    CHECK (NOT estoque_aplicado OR (tipo_item = 'Produto' AND status IN ('Pendente', 'Pago') AND NOT excluida))
);
CREATE INDEX IF NOT EXISTS ix_crm_vendas_workspace_data
    ON socialmei.crm_vendas (workspace_id, data DESC, id);
CREATE TABLE IF NOT EXISTS socialmei.crm_venda_operacoes (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    operation_id UUID NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    resposta JSONB NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, operation_id)
);
CREATE TABLE IF NOT EXISTS socialmei.crm_venda_importacoes (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    origem UUID NOT NULL,
    local_id BIGINT NOT NULL CHECK (local_id >= 0 AND local_id <= 9007199254740991),
    venda_id BIGINT NOT NULL REFERENCES socialmei.crm_vendas(id),
    fingerprint CHAR(64) NOT NULL,
    snapshot JSONB NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, origem, local_id)
);
