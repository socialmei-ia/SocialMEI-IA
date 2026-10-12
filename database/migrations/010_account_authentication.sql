-- Autenticacao opt-in. Nenhuma conta, senha ou permissao administrativa e criada.
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email_normalizado
    ON socialmei.users (LOWER(BTRIM(email)));
ALTER TABLE socialmei.users ADD COLUMN IF NOT EXISTS telefone VARCHAR(40);
ALTER TABLE socialmei.workspaces ADD COLUMN IF NOT EXISTS configuracao JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(configuracao) = 'object');

CREATE TABLE IF NOT EXISTS socialmei.auth_credenciais (
    user_id BIGINT PRIMARY KEY REFERENCES socialmei.users(id) ON DELETE CASCADE,
    senha_hash TEXT NOT NULL CHECK (senha_hash LIKE '$argon2id$%'),
    ativo BOOLEAN NOT NULL DEFAULT true,
    administrador_plataforma BOOLEAN NOT NULL DEFAULT false,
    senha_alterada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS socialmei.auth_sessoes (
    token_hash CHAR(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    user_id BIGINT NOT NULL,
    workspace_id BIGINT NOT NULL,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_em TIMESTAMPTZ NOT NULL,
    revogada_em TIMESTAMPTZ,
    FOREIGN KEY (workspace_id, user_id) REFERENCES socialmei.workspace_members(workspace_id, user_id) ON DELETE CASCADE,
    CHECK (expira_em > criada_em)
);
CREATE INDEX IF NOT EXISTS ix_auth_sessoes_usuario ON socialmei.auth_sessoes (user_id);
CREATE INDEX IF NOT EXISTS ix_auth_sessoes_expira ON socialmei.auth_sessoes (expira_em);

CREATE TABLE IF NOT EXISTS socialmei.auth_convites (
    token_hash CHAR(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    email VARCHAR(255) NOT NULL,
    criado_por BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_em TIMESTAMPTZ NOT NULL,
    usado_em TIMESTAMPTZ,
    revogado_em TIMESTAMPTZ,
    user_id BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
    CHECK (expira_em > criado_em)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_auth_convite_email_ativo ON socialmei.auth_convites (email)
    WHERE usado_em IS NULL AND revogado_em IS NULL;

CREATE TABLE IF NOT EXISTS socialmei.auth_limites (
    chave CHAR(64) PRIMARY KEY,
    inicio TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tentativas INTEGER NOT NULL DEFAULT 1 CHECK (tentativas > 0)
);
CREATE TABLE IF NOT EXISTS socialmei.auth_auditoria (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
    alvo_user_id BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
    acao VARCHAR(40) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE socialmei.auth_credenciais IS 'Hashes Argon2id e papel administrativo global; nunca senhas em texto.';
COMMENT ON TABLE socialmei.auth_sessoes IS 'Somente SHA-256 de tokens aleatorios. Credencial de sessao fica em cookie HttpOnly/Secure.';
COMMENT ON TABLE socialmei.auth_convites IS 'Convites por email, com token somente como hash, validade e consumo unico.';
