CREATE TABLE IF NOT EXISTS socialmei.editorial_draft_assets (
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    id UUID NOT NULL,
    fingerprint CHAR(64) NOT NULL CHECK (fingerprint ~ '^[a-f0-9]{64}$'),
    image_bytes BYTEA NOT NULL CHECK (octet_length(image_bytes) BETWEEN 1 AND 2097152),
    actor_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(workspace_id,id),
    UNIQUE(workspace_id,fingerprint)
);
ALTER TABLE socialmei.editorial_draft_revisions
    ADD COLUMN IF NOT EXISTS asset_id UUID;
DO $migration$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
        WHERE conrelid='socialmei.editorial_draft_revisions'::regclass AND conname='fk_editorial_draft_asset') THEN
        ALTER TABLE socialmei.editorial_draft_revisions ADD CONSTRAINT fk_editorial_draft_asset
            FOREIGN KEY(workspace_id,asset_id) REFERENCES socialmei.editorial_draft_assets(workspace_id,id);
    END IF;
END
$migration$;
