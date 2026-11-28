ALTER TABLE socialmei.crm_financeiro
    ADD COLUMN IF NOT EXISTS liquidado_parcial NUMERIC(15,2) NOT NULL DEFAULT 0
    CHECK (liquidado_parcial BETWEEN 0 AND valor);

CREATE TABLE IF NOT EXISTS socialmei.crm_financeiro_liquidacoes (
    workspace_id BIGINT NOT NULL,
    id UUID NOT NULL,
    lancamento_id BIGINT NOT NULL,
    valor NUMERIC(15,2) NOT NULL CHECK (valor > 0),
    data DATE NOT NULL,
    autor_id BIGINT NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    estornado_em TIMESTAMPTZ,
    estornado_por BIGINT,
    motivo_estorno TEXT,
    PRIMARY KEY (workspace_id,id),
    FOREIGN KEY (workspace_id,lancamento_id)
        REFERENCES socialmei.crm_financeiro(workspace_id,id) ON DELETE CASCADE,
    CHECK (
        (estornado_em IS NULL AND estornado_por IS NULL AND motivo_estorno IS NULL)
        OR (estornado_em IS NOT NULL AND estornado_por IS NOT NULL
            AND motivo_estorno IS NOT NULL AND length(btrim(motivo_estorno)) BETWEEN 1 AND 300)
    )
);
CREATE INDEX IF NOT EXISTS ix_financeiro_liquidacoes_lancamento
    ON socialmei.crm_financeiro_liquidacoes(workspace_id,lancamento_id,data);
CREATE INDEX IF NOT EXISTS ix_financeiro_liquidacoes_caixa
    ON socialmei.crm_financeiro_liquidacoes(workspace_id,data) WHERE estornado_em IS NULL;

CREATE OR REPLACE VIEW socialmei.crm_financeiro_caixa AS
SELECT workspace_id,id AS lancamento_id,tipo,categoria,valor,data_pagamento AS data
FROM socialmei.crm_financeiro
WHERE NOT excluida AND status='pago' AND data_pagamento IS NOT NULL AND liquidado_parcial=0
UNION ALL
SELECT q.workspace_id,q.lancamento_id,f.tipo,f.categoria,q.valor,q.data
FROM socialmei.crm_financeiro_liquidacoes q
JOIN socialmei.crm_financeiro f ON f.workspace_id=q.workspace_id AND f.id=q.lancamento_id
WHERE q.estornado_em IS NULL AND NOT f.excluida;
