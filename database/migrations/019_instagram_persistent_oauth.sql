-- Prepared OAuth persistence. No real provider, credentials or accounts are enabled.
CREATE UNIQUE INDEX IF NOT EXISTS ux_auth_session_tenant_user
    ON socialmei.auth_sessoes (token_hash, workspace_id, user_id);

CREATE TABLE IF NOT EXISTS socialmei.ig_meta_oauth_states (
    state_hash CHAR(64) PRIMARY KEY CHECK (state_hash ~ '^[0-9a-f]{64}$'),
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    session_hash CHAR(64) NOT NULL,
    callback_uri TEXT NOT NULL CHECK (length(callback_uri) BETWEEN 1 AND 2048),
    scopes TEXT[] NOT NULL CHECK (cardinality(scopes) BETWEEN 1 AND 4),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','exchanging','connected','failed','cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    FOREIGN KEY (session_hash, workspace_id, user_id)
        REFERENCES socialmei.auth_sessoes(token_hash, workspace_id, user_id) ON DELETE CASCADE,
    CHECK (expires_at > created_at),
    CHECK ((status = 'pending') = (consumed_at IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_ig_meta_states_workspace
    ON socialmei.ig_meta_oauth_states (workspace_id, status);

CREATE TABLE IF NOT EXISTS socialmei.ig_meta_connections (
    id UUID PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    external_account_id VARCHAR(40) NOT NULL CHECK (external_account_id ~ '^[0-9]{1,40}$'),
    account_type TEXT NOT NULL CHECK (account_type IN ('BUSINESS','MEDIA_CREATOR')),
    status TEXT NOT NULL CHECK (status IN ('connected','disconnected','expired')),
    scopes TEXT[] NOT NULL CHECK (cardinality(scopes) BETWEEN 1 AND 4),
    encrypted_token TEXT CHECK (length(encrypted_token) BETWEEN 1 AND 24000),
    token_kind TEXT NOT NULL CHECK (token_kind = 'long'),
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    disconnected_at TIMESTAMPTZ,
    UNIQUE(workspace_id, id),
    FOREIGN KEY (workspace_id, created_by)
        REFERENCES socialmei.workspace_members(workspace_id,user_id) ON DELETE SET NULL (created_by),
    CHECK (expires_at > issued_at),
    CHECK ((status = 'connected') = (encrypted_token IS NOT NULL)),
    CHECK ((status <> 'connected') = (disconnected_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ig_meta_connected_account
    ON socialmei.ig_meta_connections(external_account_id) WHERE status='connected';
CREATE UNIQUE INDEX IF NOT EXISTS ux_ig_meta_connected_workspace
    ON socialmei.ig_meta_connections(workspace_id) WHERE status='connected';
CREATE INDEX IF NOT EXISTS ix_ig_meta_connections_workspace_history
    ON socialmei.ig_meta_connections(workspace_id,created_at DESC,id);

CREATE TABLE IF NOT EXISTS socialmei.ig_meta_audit (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    user_id BIGINT,
    connection_id UUID,
    action TEXT NOT NULL CHECK (action IN ('started','connected','failed','disconnected','expired','key_rotated')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (workspace_id,user_id)
        REFERENCES socialmei.workspace_members(workspace_id,user_id) ON DELETE SET NULL (user_id),
    FOREIGN KEY (workspace_id,connection_id)
        REFERENCES socialmei.ig_meta_connections(workspace_id,id)
);
CREATE INDEX IF NOT EXISTS ix_ig_meta_audit_workspace
    ON socialmei.ig_meta_audit(workspace_id,created_at DESC,id);
