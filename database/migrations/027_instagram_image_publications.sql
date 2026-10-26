-- Instagram single-image publication outbox. Separate from Direct/n8n.
CREATE TABLE IF NOT EXISTS socialmei.ig_meta_publications (
  id UUID PRIMARY KEY,
  workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id),
  request_id UUID NOT NULL,
  created_by BIGINT NOT NULL,
  connection_id UUID NOT NULL REFERENCES socialmei.ig_meta_connections(id),
  external_account_id TEXT NOT NULL,
  image_url TEXT NOT NULL,
  caption TEXT NOT NULL,
  content_fingerprint TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('creating','created','publishing','published','uncertain')),
  container_id TEXT,
  media_id TEXT,
  error_code TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_id, request_id)
);
CREATE INDEX IF NOT EXISTS ig_meta_publications_workspace_recent
  ON socialmei.ig_meta_publications(workspace_id, created_at DESC);
