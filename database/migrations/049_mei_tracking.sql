CREATE TABLE IF NOT EXISTS socialmei.mei_tracking_revisions (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL CHECK (revision > 0),
    operation_id UUID NOT NULL,
    actor_id BIGINT NOT NULL,
    opened_on DATE NOT NULL,
    prior_through DATE,
    prior_amount NUMERIC(15,2),
    source_note TEXT NOT NULL CHECK (length(source_note) <= 300),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, revision),
    UNIQUE (workspace_id, operation_id),
    CHECK (
        (prior_through IS NULL AND prior_amount IS NULL AND source_note = '')
        OR (prior_through IS NOT NULL AND prior_amount IS NOT NULL AND prior_amount >= 0
            AND prior_through >= opened_on AND length(btrim(source_note)) > 0)
    )
);
