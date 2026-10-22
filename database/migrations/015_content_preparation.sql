-- Persisted preparation and simulation only. Never stores provider credentials or media bytes.
CREATE TABLE IF NOT EXISTS socialmei.content_preparation_jobs (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 id UUID NOT NULL,
 account_id UUID,
 requested_by BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
 idempotency_key UUID NOT NULL,
 fingerprint CHAR(64) NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
 title VARCHAR(120) NOT NULL DEFAULT '',
 format VARCHAR(10) NOT NULL CHECK(format IN ('feed','story','reel')),
 caption TEXT NOT NULL CHECK(length(caption)<=2200),
 media_manifest JSONB NOT NULL CHECK(jsonb_typeof(media_manifest)='array'),
 scheduled_for TIMESTAMPTZ,
 timezone VARCHAR(80) NOT NULL DEFAULT 'America/Fortaleza',
 status VARCHAR(20) NOT NULL CHECK(status IN ('draft','pending_review','scheduled','processing','simulated','failed','uncertain','cancelled')),
 attempts SMALLINT NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 run_after TIMESTAMPTZ,
 claim_token UUID,
 lease_until TIMESTAMPTZ,
 last_error_code VARCHAR(40),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id),
 UNIQUE(workspace_id,idempotency_key),
 FOREIGN KEY(workspace_id,account_id) REFERENCES socialmei.instagram_sim_accounts(workspace_id,id),
 CHECK(status NOT IN ('scheduled','processing','simulated') OR (account_id IS NOT NULL AND scheduled_for IS NOT NULL AND jsonb_array_length(media_manifest)>0))
);
CREATE INDEX IF NOT EXISTS ix_content_preparation_due ON socialmei.content_preparation_jobs(workspace_id,run_after,id) WHERE status='scheduled';
CREATE INDEX IF NOT EXISTS ix_content_preparation_history ON socialmei.content_preparation_jobs(workspace_id,created_at DESC,id);
CREATE TABLE IF NOT EXISTS socialmei.content_preparation_events (
 workspace_id BIGINT NOT NULL,
 job_id UUID NOT NULL,
 id BIGSERIAL PRIMARY KEY,
 status VARCHAR(20) NOT NULL,
 code VARCHAR(40),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 FOREIGN KEY(workspace_id,job_id) REFERENCES socialmei.content_preparation_jobs(workspace_id,id) ON DELETE CASCADE
);
COMMENT ON TABLE socialmei.content_preparation_jobs IS 'Preparation and isolated simulated scheduling, never a real publication. Metadata only; media must be uploaded through a future reviewed contract.';
