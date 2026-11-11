-- Human reply drafts and durable attempts. No transport or channel is enabled.
CREATE TABLE IF NOT EXISTS socialmei.wa_human_replies (
 workspace_id BIGINT NOT NULL,
 id UUID NOT NULL,
 channel_id BIGINT NOT NULL,
 conversation_id BIGINT NOT NULL,
 source_message_id BIGINT NOT NULL,
 binding_hash CHAR(64) NOT NULL CHECK(binding_hash ~ '^[0-9a-f]{64}$'),
 fingerprint CHAR(64) NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$'),
 text TEXT NOT NULL CHECK(octet_length(text) BETWEEN 1 AND 4096),
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','dispatching','confirmed','uncertain')),
 created_by BIGINT,
 provider_message_id VARCHAR(1024),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 claimed_at TIMESTAMPTZ,
 finished_at TIMESTAMPTZ,
 PRIMARY KEY(workspace_id,id),
 FOREIGN KEY(workspace_id,channel_id) REFERENCES socialmei.crm_canais(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,conversation_id) REFERENCES socialmei.me_conversations(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,source_message_id) REFERENCES socialmei.me_messages(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,created_by) REFERENCES socialmei.workspace_members(workspace_id,user_id) ON DELETE SET NULL(created_by),
 CHECK((status='confirmed')=(provider_message_id IS NOT NULL)),
 CHECK(provider_message_id IS NULL OR provider_message_id ~ '^[!-~]+$'),
 CHECK((status<>'draft')=(claimed_at IS NOT NULL)),
 CHECK((status IN ('confirmed','uncertain'))=(finished_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_wa_human_provider_receipt
 ON socialmei.wa_human_replies(workspace_id,channel_id,provider_message_id)
 WHERE provider_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_wa_human_reply_history
 ON socialmei.wa_human_replies(workspace_id,conversation_id,created_at DESC,id);
