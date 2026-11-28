CREATE TABLE IF NOT EXISTS socialmei.editorial_draft_revisions (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    draft_id UUID NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    operation_id UUID NOT NULL,
    actor_id BIGINT NOT NULL,
    archived BOOLEAN NOT NULL DEFAULT false,
    document JSONB NOT NULL CHECK (jsonb_typeof(document) = 'object' AND octet_length(document::text) <= 22000),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id,draft_id,revision),
    UNIQUE (workspace_id,operation_id)
);
