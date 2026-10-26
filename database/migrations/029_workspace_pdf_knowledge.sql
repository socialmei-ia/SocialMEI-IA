-- Private per-workspace PDF knowledge (no external embedding provider).
-- 2 MiB per PDF, text indexed for deterministic Portuguese retrieval.
CREATE TABLE IF NOT EXISTS socialmei.kb_pdf_documents (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    id UUID NOT NULL,
    filename VARCHAR(160) NOT NULL,
    sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    pdf_bytes BYTEA NOT NULL CHECK (octet_length(pdf_bytes) BETWEEN 8 AND 2097152),
    page_count INTEGER NOT NULL CHECK (page_count BETWEEN 1 AND 100),
    status TEXT NOT NULL CHECK (status IN ('indexed', 'no_text')),
    uploaded_by BIGINT,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, sha256),
    FOREIGN KEY (workspace_id, uploaded_by)
       REFERENCES socialmei.workspace_members(workspace_id, user_id)
       ON DELETE SET NULL (uploaded_by)
);
CREATE INDEX IF NOT EXISTS ix_kb_pdf_documents_workspace
    ON socialmei.kb_pdf_documents(workspace_id, uploaded_at DESC);
CREATE TABLE IF NOT EXISTS socialmei.kb_pdf_chunks (
    workspace_id BIGINT NOT NULL,
    document_id UUID NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 0 AND 10000),
    page_number INTEGER NOT NULL CHECK (page_number BETWEEN 1 AND 100),
    content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 1200),
    search_vector TSVECTOR GENERATED ALWAYS AS
        (to_tsvector('portuguese'::regconfig, content)) STORED,
    PRIMARY KEY (workspace_id, document_id, ordinal),
    FOREIGN KEY (workspace_id, document_id)
        REFERENCES socialmei.kb_pdf_documents(workspace_id, id)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_kb_pdf_chunks_search
    ON socialmei.kb_pdf_chunks USING GIN(search_vector);
