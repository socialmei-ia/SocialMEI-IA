-- Inbox preferences belong to the workspace member, independently of hidden history.
CREATE TABLE IF NOT EXISTS socialmei.me_inbox_preferences (
    workspace_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    conversation_id BIGINT NOT NULL,
    read_through_id BIGINT NOT NULL DEFAULT 0 CHECK (read_through_id >= 0),
    marked_unread BOOLEAN NOT NULL DEFAULT FALSE,
    archived_at TIMESTAMPTZ,
    PRIMARY KEY (workspace_id, user_id, conversation_id),
    FOREIGN KEY (workspace_id, user_id) REFERENCES socialmei.workspace_members(workspace_id, user_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, conversation_id) REFERENCES socialmei.me_conversations(workspace_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS me_messages_provider_inbox_watermark_idx
    ON socialmei.me_messages (workspace_id, conversation_id, id)
    WHERE origin IN ('waha', 'instagram');

DO $grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='socialmei_candidate040') THEN
        GRANT SELECT, INSERT, UPDATE ON TABLE socialmei.me_inbox_preferences TO socialmei_candidate040;
    END IF;
END
$grants$;
