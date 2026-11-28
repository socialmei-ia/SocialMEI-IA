CREATE TABLE IF NOT EXISTS socialmei.mei_das_revisions (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    competencia DATE NOT NULL CHECK (EXTRACT(DAY FROM competencia)=1),
    revision INTEGER NOT NULL CHECK (revision > 0),
    operation_id UUID NOT NULL,
    actor_id BIGINT NOT NULL,
    pago_em DATE,
    valor NUMERIC(15,2),
    referencia TEXT NOT NULL CHECK (length(btrim(referencia)) BETWEEN 1 AND 300),
    registrado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id,competencia,revision),
    UNIQUE (workspace_id,operation_id),
    CHECK ((pago_em IS NULL AND valor IS NULL)
        OR (pago_em IS NOT NULL AND valor IS NOT NULL AND valor > 0 AND pago_em >= competencia))
);
