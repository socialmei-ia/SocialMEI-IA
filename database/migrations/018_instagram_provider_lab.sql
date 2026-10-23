-- Isolated fake provider only. No credentials, remote tokens or real delivery.
CREATE TABLE IF NOT EXISTS socialmei.ig_lab_states (
 state_hash CHAR(64) PRIMARY KEY,
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 user_id BIGINT NOT NULL REFERENCES socialmei.users(id) ON DELETE CASCADE,
 session_hash CHAR(64) NOT NULL,
 expires_at TIMESTAMPTZ NOT NULL,
 consumed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS socialmei.ig_lab_connections (
 workspace_id BIGINT PRIMARY KEY REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 account_id UUID NOT NULL UNIQUE,
 status TEXT NOT NULL CHECK(status IN ('connected','disconnected','expired','revoked')),
 expires_at TIMESTAMPTZ NOT NULL,
 FOREIGN KEY(workspace_id,account_id) REFERENCES socialmei.instagram_sim_accounts(workspace_id,id)
);
CREATE TABLE IF NOT EXISTS socialmei.ig_lab_events (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 event_id UUID NOT NULL,
 fingerprint CHAR(64) NOT NULL,
 result JSONB NOT NULL,
 PRIMARY KEY(workspace_id,event_id)
);
CREATE TABLE IF NOT EXISTS socialmei.ig_lab_publications (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 id UUID NOT NULL,
 account_id UUID NOT NULL,
 idempotency_key UUID NOT NULL,
 fingerprint CHAR(64) NOT NULL,
 payload JSONB NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processing','simulated-published','failed')),
 approved_by BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 provider_result JSONB,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(workspace_id,id),
 UNIQUE(workspace_id,account_id,idempotency_key),
 FOREIGN KEY(workspace_id,account_id) REFERENCES socialmei.instagram_sim_accounts(workspace_id,id)
);
