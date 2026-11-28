CREATE UNIQUE INDEX IF NOT EXISTS ig_inbound_media_ai_source_key
    ON socialmei.ig_inbound_media(workspace_id,message_id,id,sha256);

CREATE TABLE IF NOT EXISTS socialmei.ig_inbound_media_ai (
    attachment_id BIGINT PRIMARY KEY REFERENCES socialmei.ig_inbound_media(id) ON DELETE CASCADE,
    workspace_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    status TEXT NOT NULL CHECK (status IN ('processing','completed','unavailable','uncertain')),
    interpretation TEXT CHECK (length(interpretation) BETWEEN 1 AND 480),
    intent TEXT CHECK (intent IN ('products','services','booking','quote','clarify','context_only')),
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    UNIQUE (workspace_id,message_id),
    FOREIGN KEY (workspace_id,message_id,attachment_id,sha256)
        REFERENCES socialmei.ig_inbound_media(workspace_id,message_id,id,sha256) ON DELETE CASCADE,
    CHECK ((status='processing') = (finished_at IS NULL)),
    CHECK ((status='completed') = (interpretation IS NOT NULL AND intent IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ig_inbound_media_ai_budget_idx
    ON socialmei.ig_inbound_media_ai(workspace_id,claimed_at);

DO $grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='socialmei_candidate040') THEN
        GRANT SELECT,INSERT,UPDATE ON socialmei.ig_inbound_media_ai TO socialmei_candidate040;
    END IF;
END
$grants$;
