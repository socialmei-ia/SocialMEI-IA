-- Explicit read-only WAHA/n8n catalog access; unrelated workflows stay unchanged.
-- Credentials are only stored as SHA-256 hashes, issued once to an owner/admin.
CREATE TABLE IF NOT EXISTS socialmei.wa_catalog_access (
    workspace_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    instance VARCHAR(80) NOT NULL,
    token_hash CHAR(64) NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    issued_by BIGINT,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, channel_id),
    UNIQUE (token_hash),
    FOREIGN KEY (workspace_id, channel_id)
        REFERENCES socialmei.crm_canais(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, issued_by)
        REFERENCES socialmei.workspace_members(workspace_id, user_id)
        ON DELETE SET NULL (issued_by)
);
CREATE INDEX IF NOT EXISTS ix_wa_catalog_instance_active
    ON socialmei.wa_catalog_access(instance) WHERE enabled;
