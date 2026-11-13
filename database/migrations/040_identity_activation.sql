-- Optional identity activation; legacy accounts are not silently marked verified.
CREATE TABLE IF NOT EXISTS socialmei.auth_email_activation (
    user_id BIGINT PRIMARY KEY REFERENCES socialmei.users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS socialmei.auth_identity_mail (
    id UUID PRIMARY KEY,
    purpose VARCHAR(12) NOT NULL CHECK (purpose IN ('verification','invitation')),
    user_id BIGINT REFERENCES socialmei.users(id) ON DELETE CASCADE,
    workspace_id BIGINT REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    created_by BIGINT REFERENCES socialmei.users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(20) CHECK (role IN ('admin','member','viewer','report_viewer')),
    status VARCHAR(12) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','sent','uncertain','expired','used','revoked')),
    token_hash CHAR(64) UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '30 minutes',
    finished_at TIMESTAMPTZ,
    CHECK (expires_at>created_at),
    CHECK ((purpose='verification' AND user_id IS NOT NULL AND workspace_id IS NULL AND role IS NULL)
        OR (purpose='invitation' AND workspace_id IS NOT NULL AND created_by IS NOT NULL AND role IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_identity_verification_active ON socialmei.auth_identity_mail(user_id)
    WHERE purpose='verification' AND status IN ('pending','processing','sent');
CREATE UNIQUE INDEX IF NOT EXISTS ux_identity_invitation_active ON socialmei.auth_identity_mail(workspace_id,email)
    WHERE purpose='invitation' AND status IN ('pending','processing','sent');
CREATE INDEX IF NOT EXISTS ix_identity_mail_pending ON socialmei.auth_identity_mail(created_at,id) WHERE status='pending';
COMMENT ON TABLE socialmei.auth_identity_mail IS 'Durable opt-in verification and business invitations; token hashes only, uncertain sends never retried.';
