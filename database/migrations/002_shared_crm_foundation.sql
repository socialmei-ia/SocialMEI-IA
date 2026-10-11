-- 002_shared_crm_foundation.sql
-- Fundação segura para persistência compartilhada da gestão.
-- Não altera as tabelas atuais de atendimento (clientes/conversas/mensagens).

CREATE TABLE IF NOT EXISTS socialmei.workspaces (
    id BIGSERIAL PRIMARY KEY,
    slug VARCHAR(80) NOT NULL UNIQUE,
    nome VARCHAR(160) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS socialmei.users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    nome VARCHAR(160) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS socialmei.workspace_members (
    workspace_id BIGINT NOT NULL
        REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL
        REFERENCES socialmei.users(id) ON DELETE CASCADE,
    role VARCHAR(30) NOT NULL DEFAULT 'member'
        CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, user_id)
);

CREATE TABLE IF NOT EXISTS socialmei.crm_clientes (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL
        REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    nome VARCHAR(160) NOT NULL,
    telefone VARCHAR(40),
    email VARCHAR(255),
    instagram VARCHAR(160),
    status VARCHAR(30) NOT NULL DEFAULT 'Ativo',
    observacao TEXT,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    legacy_local_id BIGINT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(tags) = 'array')
);

CREATE INDEX IF NOT EXISTS ix_crm_clientes_workspace
    ON socialmei.crm_clientes (workspace_id);

CREATE INDEX IF NOT EXISTS ix_crm_clientes_workspace_nome
    ON socialmei.crm_clientes (workspace_id, LOWER(nome));

CREATE UNIQUE INDEX IF NOT EXISTS ux_crm_clientes_workspace_legacy_local
    ON socialmei.crm_clientes (workspace_id, legacy_local_id)
    WHERE legacy_local_id IS NOT NULL;

COMMENT ON TABLE socialmei.workspaces IS
    'Fronteira de negócio para dados compartilhados do SocialMEI.';
COMMENT ON TABLE socialmei.crm_clientes IS
    'Cadastro de clientes da gestão compartilhada; separado temporariamente do histórico de atendimento.';
