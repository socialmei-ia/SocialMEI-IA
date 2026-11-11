-- Additive, opt-in automation state. Existing OAuth, messages and human jobs are unchanged.
CREATE TABLE IF NOT EXISTS socialmei.ig_menu_conversations (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 conversation_id BIGINT NOT NULL,
 origin TEXT NOT NULL DEFAULT 'instagram' CHECK(origin='instagram'),
 state TEXT NOT NULL DEFAULT 'menu' CHECK(state IN ('menu','ask_product','human')),
 revision BIGINT NOT NULL DEFAULT 0 CHECK(revision>=0),
 last_message_id BIGINT,
 last_occurred_at TIMESTAMPTZ,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(workspace_id,conversation_id),
 FOREIGN KEY(workspace_id,conversation_id,origin) REFERENCES socialmei.me_conversations(workspace_id,id,origin),
 FOREIGN KEY(workspace_id,last_message_id,origin) REFERENCES socialmei.me_messages(workspace_id,id,origin)
);
CREATE TABLE IF NOT EXISTS socialmei.ig_menu_replies (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 id UUID NOT NULL,
 conversation_id BIGINT NOT NULL,
 source_message_id BIGINT NOT NULL,
 origin TEXT NOT NULL DEFAULT 'instagram' CHECK(origin='instagram'),
 connection_id UUID NOT NULL,
 external_account_id VARCHAR(40) NOT NULL,
 recipient_id VARCHAR(40) NOT NULL CHECK(recipient_id ~ '^[0-9]{1,40}$'),
 text TEXT NOT NULL CHECK(octet_length(text)<=1000),
 status TEXT NOT NULL CHECK(status IN ('dispatching','confirmed','uncertain','failed','skipped')),
 provider_message_id VARCHAR(1024),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 finished_at TIMESTAMPTZ,
 PRIMARY KEY(workspace_id,id),
 UNIQUE(workspace_id,source_message_id),
 FOREIGN KEY(workspace_id,conversation_id) REFERENCES socialmei.ig_menu_conversations(workspace_id,conversation_id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,source_message_id,origin) REFERENCES socialmei.me_messages(workspace_id,id,origin),
 FOREIGN KEY(workspace_id,connection_id,external_account_id) REFERENCES socialmei.ig_meta_connections(workspace_id,id,external_account_id),
 CHECK((status='confirmed')=(provider_message_id IS NOT NULL)),
 CHECK((status='dispatching')=(finished_at IS NULL)),
 CHECK(provider_message_id IS NULL OR provider_message_id ~ '^[!-~]+$')
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ig_menu_provider_receipt
 ON socialmei.ig_menu_replies(workspace_id,provider_message_id) WHERE provider_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_ig_menu_conversation_history
 ON socialmei.ig_menu_replies(workspace_id,conversation_id,created_at DESC);
