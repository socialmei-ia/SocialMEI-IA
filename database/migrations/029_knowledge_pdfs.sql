-- 029: Workspace-isolated PDF knowledge, stored privately in PostgreSQL.
-- Future OCR/embeddings can extend this ledger without changing uploaded originals.
CREATE TABLE IF NOT EXISTS socialmei.knowledge_pdfs (
 id UUID NOT NULL,
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 uploaded_by BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
 filename TEXT NOT NULL CHECK (char_length(filename) BETWEEN 1 AND 180),
 file_sha256 CHAR(64) NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
 media_type TEXT NOT NULL DEFAULT 'application/pdf' CHECK(media_type='application/pdf'),
 original_bytes BYTEA NOT NULL CHECK (octet_length(original_bytes) BETWEEN 1 AND 5242880),
 pages INTEGER NOT NULL CHECK (pages BETWEEN 1 AND 80),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(workspace_id,id),
 UNIQUE (workspace_id, file_sha256)
);
CREATE INDEX IF NOT EXISTS knowledge_pdfs_workspace_recent ON socialmei.knowledge_pdfs(workspace_id,created_at DESC);
CREATE TABLE IF NOT EXISTS socialmei.knowledge_pdf_pages (
 workspace_id BIGINT NOT NULL,
 document_id UUID NOT NULL,
 page_number INTEGER NOT NULL CHECK (page_number BETWEEN 1 AND 80),
 page_text TEXT NOT NULL CHECK (octet_length(page_text) BETWEEN 1 AND 32768),
 indexed_text TSVECTOR GENERATED ALWAYS AS (to_tsvector('portuguese',page_text)) STORED,
 PRIMARY KEY (workspace_id,document_id,page_number),
 FOREIGN KEY (workspace_id,document_id) REFERENCES socialmei.knowledge_pdfs(workspace_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS knowledge_pdf_pages_search ON socialmei.knowledge_pdf_pages USING GIN (indexed_text);
