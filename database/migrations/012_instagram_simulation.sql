-- Instagram simulation: tenant-scoped metadata only, no Meta credentials or media bytes.
CREATE TABLE IF NOT EXISTS socialmei.instagram_sim_accounts (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 id UUID NOT NULL,
 label VARCHAR(80) NOT NULL CHECK(length(btrim(label))>0),
 created_by BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id)
);
CREATE TABLE IF NOT EXISTS socialmei.instagram_sim_publications (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 id UUID NOT NULL,
 account_id UUID NOT NULL,
 requested_by BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
 idempotency_key UUID NOT NULL,
 fingerprint CHAR(64) NOT NULL,
 format VARCHAR(10) NOT NULL CHECK(format IN ('feed','story','reel')),
 caption TEXT NOT NULL CHECK(length(caption)<=2200),
 media_manifest JSONB NOT NULL CHECK(jsonb_typeof(media_manifest)='array'),
 scheduled_for TIMESTAMPTZ,
 status VARCHAR(20) NOT NULL DEFAULT 'simulated' CHECK(status='simulated'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id),
 UNIQUE(workspace_id,account_id,idempotency_key),
 FOREIGN KEY(workspace_id,account_id) REFERENCES socialmei.instagram_sim_accounts(workspace_id,id)
);
CREATE INDEX IF NOT EXISTS ix_instagram_sim_workspace_recent
 ON socialmei.instagram_sim_publications(workspace_id,created_at DESC);
COMMENT ON TABLE socialmei.instagram_sim_publications IS
 'Somente metadados, sem upload, entrega n8n ou publicacao na Meta.';
