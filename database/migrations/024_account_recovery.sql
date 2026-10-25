-- Optional password recovery; no account or mail configuration is created.
CREATE TABLE IF NOT EXISTS socialmei.auth_recuperacoes (
    user_id BIGINT PRIMARY KEY REFERENCES socialmei.users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    senha_alterada_em TIMESTAMPTZ NOT NULL,
    expira_em TIMESTAMPTZ NOT NULL,
    usado_em TIMESTAMPTZ
);
COMMENT ON TABLE socialmei.auth_recuperacoes IS 'One expiring recovery token hash per account; never plaintext tokens.';
