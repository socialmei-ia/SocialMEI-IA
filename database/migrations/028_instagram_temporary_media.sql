-- Bounded, expiring JPEG staging for explicit Instagram publication.
CREATE TABLE IF NOT EXISTS socialmei.ig_meta_media (
  id UUID PRIMARY KEY,
  workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id),
  created_by BIGINT NOT NULL REFERENCES socialmei.users(id),
  request_id UUID NOT NULL,
  public_key TEXT NOT NULL UNIQUE,
  fingerprint TEXT NOT NULL,
  image_bytes BYTEA NOT NULL CHECK (octet_length(image_bytes) BETWEEN 1 AND 2097152),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '1 hour',
  UNIQUE(workspace_id, request_id)
);
CREATE INDEX IF NOT EXISTS ig_meta_media_expiry ON socialmei.ig_meta_media(expires_at);
ALTER TABLE socialmei.ig_meta_publications ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ;
