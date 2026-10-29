-- Provider sentiment integration for *verified* inbox messages only.
-- No outbound messaging, provider request, or n8n workflow is activated.
CREATE TABLE IF NOT EXISTS socialmei.me_provider_sentiment_jobs (
    workspace_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    claim_id UUID NOT NULL UNIQUE,
    attempt SMALLINT NOT NULL DEFAULT 1 CHECK (attempt BETWEEN 1 AND 3),
    status TEXT NOT NULL DEFAULT 'processing'
        CHECK (status IN ('processing', 'completed')),
    lease_until TIMESTAMPTZ NOT NULL,
    sentiment TEXT CHECK (sentiment IN ('positive', 'negative', 'neutral', 'uncertain')),
    confidence TEXT CHECK (confidence IN ('low', 'medium', 'high')),
    explanation VARCHAR(500),
    result_fingerprint CHAR(64),
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(workspace_id, message_id),
    FOREIGN KEY(workspace_id, message_id)
        REFERENCES socialmei.me_messages(workspace_id, id) ON DELETE CASCADE,
    CHECK (
        (status = 'processing'
            AND sentiment IS NULL AND confidence IS NULL
            AND explanation IS NULL AND result_fingerprint IS NULL AND completed_at IS NULL)
        OR
        (status = 'completed'
            AND sentiment IS NOT NULL AND confidence IS NOT NULL
            AND explanation IS NOT NULL AND result_fingerprint IS NOT NULL AND completed_at IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS ix_me_provider_sentiment_pending
    ON socialmei.me_provider_sentiment_jobs(status, lease_until)
    WHERE status = 'processing';
