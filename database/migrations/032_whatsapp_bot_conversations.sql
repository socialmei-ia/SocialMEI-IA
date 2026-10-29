-- Planning only: no channel, sender, credential or automatic reply is activated.
CREATE TABLE IF NOT EXISTS socialmei.wa_bot_access (
 workspace_id BIGINT NOT NULL,
 channel_id BIGINT NOT NULL,
 token_hash CHAR(64) NOT NULL UNIQUE CHECK(token_hash ~ '^[0-9a-f]{64}$'),
 binding_hash CHAR(64) NOT NULL CHECK(binding_hash ~ '^[0-9a-f]{64}$'),
 issued_by BIGINT,
 issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(workspace_id,channel_id),
 FOREIGN KEY(workspace_id,channel_id) REFERENCES socialmei.crm_canais(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,issued_by) REFERENCES socialmei.workspace_members(workspace_id,user_id) ON DELETE SET NULL(issued_by)
);
CREATE TABLE IF NOT EXISTS socialmei.wa_bot_conversations (
 workspace_id BIGINT NOT NULL,
 channel_id BIGINT NOT NULL,
 conversation_id BIGINT NOT NULL,
 state TEXT NOT NULL DEFAULT 'menu' CHECK(state IN ('menu','ask_product','human')),
 revision BIGINT NOT NULL DEFAULT 0 CHECK(revision>=0),
 last_message_id BIGINT,
 last_occurred_at TIMESTAMPTZ,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(workspace_id,channel_id,conversation_id),
 FOREIGN KEY(workspace_id,channel_id) REFERENCES socialmei.crm_canais(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,conversation_id) REFERENCES socialmei.me_conversations(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,last_message_id) REFERENCES socialmei.me_messages(workspace_id,id)
);
CREATE TABLE IF NOT EXISTS socialmei.wa_bot_decisions (
 id UUID PRIMARY KEY,
 workspace_id BIGINT NOT NULL,
 channel_id BIGINT NOT NULL,
 conversation_id BIGINT NOT NULL,
 source_message_id BIGINT NOT NULL,
 binding_hash CHAR(64) NOT NULL CHECK(binding_hash ~ '^[0-9a-f]{64}$'),
 state_revision BIGINT NOT NULL CHECK(state_revision>0),
 result JSONB NOT NULL CHECK(jsonb_typeof(result)='object' AND octet_length(result::text)<=32768),
 status TEXT NOT NULL CHECK(status IN ('planned','claimed','confirmed','uncertain','skipped')),
 provider_message_id VARCHAR(1024),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 claimed_at TIMESTAMPTZ,
 finished_at TIMESTAMPTZ,
 UNIQUE(workspace_id,channel_id,source_message_id),
 FOREIGN KEY(workspace_id,channel_id,conversation_id) REFERENCES socialmei.wa_bot_conversations(workspace_id,channel_id,conversation_id),
 FOREIGN KEY(workspace_id,source_message_id) REFERENCES socialmei.me_messages(workspace_id,id),
 CHECK((status='confirmed')=(provider_message_id IS NOT NULL)),
 CHECK(provider_message_id IS NULL OR provider_message_id ~ '^[!-~]+$'),
 CHECK((status IN ('claimed','confirmed','uncertain'))=(claimed_at IS NOT NULL)),
 CHECK((status IN ('confirmed','uncertain'))=(finished_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_wa_bot_provider_receipt
 ON socialmei.wa_bot_decisions(workspace_id,channel_id,provider_message_id)
 WHERE provider_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_wa_bot_history
 ON socialmei.wa_bot_decisions(workspace_id,channel_id,conversation_id,created_at DESC);
