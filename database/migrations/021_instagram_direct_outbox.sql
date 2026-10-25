-- Approved Direct replies only. No real transport or scheduler is installed.
CREATE TABLE IF NOT EXISTS socialmei.ig_direct_jobs (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 id UUID NOT NULL,
 conversation_id BIGINT NOT NULL,
 source_message_id BIGINT NOT NULL,
 origin TEXT NOT NULL DEFAULT 'instagram' CHECK(origin='instagram'),
 connection_id UUID NOT NULL,
 external_account_id VARCHAR(40) NOT NULL,
 recipient_id VARCHAR(40) NOT NULL CHECK(recipient_id ~ '^[0-9]{1,40}$'),
 text TEXT NOT NULL CHECK(octet_length(text) BETWEEN 1 AND 1000 AND length(btrim(text))>0),
 fingerprint CHAR(64) NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$'),
 revision BIGINT NOT NULL DEFAULT 1 CHECK(revision>0),
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','dispatching','confirmed','retry_ready','failed','uncertain','cancelled')),
 created_by BIGINT,
 created_session CHAR(64) NOT NULL CHECK(created_session ~ '^[0-9a-f]{64}$'),
 approved_by BIGINT,
 approved_session CHAR(64) CHECK(approved_session ~ '^[0-9a-f]{64}$'),
 approved_revision BIGINT,
 approved_fingerprint CHAR(64),
 attempts SMALLINT NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 claim_token UUID,
 lease_until TIMESTAMPTZ,
 run_after TIMESTAMPTZ,
 provider_message_id VARCHAR(1024),
 last_error TEXT CHECK(last_error IN ('rate_limited','rejected','outcome_unknown','lease_expired')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(workspace_id,id),
 FOREIGN KEY(workspace_id,conversation_id,origin) REFERENCES socialmei.me_conversations(workspace_id,id,origin),
 FOREIGN KEY(workspace_id,source_message_id,origin) REFERENCES socialmei.me_messages(workspace_id,id,origin),
 FOREIGN KEY(workspace_id,connection_id,external_account_id) REFERENCES socialmei.ig_meta_connections(workspace_id,id,external_account_id),
 FOREIGN KEY(workspace_id,created_by) REFERENCES socialmei.workspace_members(workspace_id,user_id) ON DELETE SET NULL (created_by),
 FOREIGN KEY(workspace_id,approved_by) REFERENCES socialmei.workspace_members(workspace_id,user_id) ON DELETE SET NULL (approved_by),
 CHECK(approved_fingerprint IS NULL OR approved_fingerprint ~ '^[0-9a-f]{64}$'),
 CHECK(status NOT IN ('approved','dispatching','confirmed','retry_ready','failed','uncertain') OR (approved_revision IS NOT NULL AND approved_fingerprint IS NOT NULL AND approved_revision=revision AND approved_fingerprint=fingerprint)),
 CHECK((status='dispatching')=(claim_token IS NOT NULL AND lease_until IS NOT NULL)),
 CHECK((status='confirmed')=(provider_message_id IS NOT NULL)),
 CHECK(provider_message_id IS NULL OR (provider_message_id ~ '^[!-~]+$' AND octet_length(provider_message_id)<=1024))
);
CREATE INDEX IF NOT EXISTS ix_ig_direct_jobs_workspace ON socialmei.ig_direct_jobs(workspace_id,created_at DESC,id);
CREATE TABLE IF NOT EXISTS socialmei.ig_direct_operations (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 operation_id UUID NOT NULL,
 fingerprint CHAR(64) NOT NULL,
 response JSONB NOT NULL CHECK(jsonb_typeof(response)='object'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(workspace_id,operation_id)
);
CREATE TABLE IF NOT EXISTS socialmei.ig_direct_attempts (
 workspace_id BIGINT NOT NULL,
 job_id UUID NOT NULL,
 attempt SMALLINT NOT NULL CHECK(attempt BETWEEN 1 AND 3),
 claim_token UUID NOT NULL UNIQUE,
 status TEXT NOT NULL CHECK(status IN ('dispatching','confirmed','rejected','rate_limited','uncertain')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 finished_at TIMESTAMPTZ,
 PRIMARY KEY(workspace_id,job_id,attempt),
 FOREIGN KEY(workspace_id,job_id) REFERENCES socialmei.ig_direct_jobs(workspace_id,id) ON DELETE CASCADE,
 CHECK((status='dispatching')=(finished_at IS NULL))
);
CREATE TABLE IF NOT EXISTS socialmei.ig_direct_events (
 id BIGSERIAL PRIMARY KEY,
 workspace_id BIGINT NOT NULL,
 job_id UUID NOT NULL,
 actor_id BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
 action TEXT NOT NULL CHECK(action IN ('created','edited','approved','cancelled','dispatching','confirmed','retry_ready','failed','uncertain')),
 revision BIGINT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 FOREIGN KEY(workspace_id,job_id) REFERENCES socialmei.ig_direct_jobs(workspace_id,id) ON DELETE CASCADE
);
