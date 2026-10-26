-- Prepared Instagram ingress. Synthetic API contracts and existing rows are preserved.
ALTER TABLE socialmei.me_conversations ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'synthetic';
ALTER TABLE socialmei.me_messages ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'synthetic';
ALTER TABLE socialmei.me_external_messages ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'synthetic';
ALTER TABLE socialmei.me_messages ALTER COLUMN external_message_id TYPE VARCHAR(1024);
ALTER TABLE socialmei.me_external_messages ALTER COLUMN external_message_id TYPE VARCHAR(1024);

ALTER TABLE socialmei.me_conversations DROP CONSTRAINT IF EXISTS me_conversations_account_ref_check;
ALTER TABLE socialmei.me_conversations DROP CONSTRAINT IF EXISTS me_conversations_contact_ref_check;
ALTER TABLE socialmei.me_external_messages DROP CONSTRAINT IF EXISTS me_external_messages_account_ref_check;

DO $migration$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_conversations'::regclass AND conname='ck_me_conversation_origin') THEN
  ALTER TABLE socialmei.me_conversations ADD CONSTRAINT ck_me_conversation_origin CHECK (
   (origin='synthetic' AND account_ref LIKE 'synthetic:%' AND contact_ref LIKE 'synthetic:%') OR
   (origin='instagram' AND channel='instagram' AND account_ref ~ '^instagram:[0-9]{1,40}$' AND contact_ref ~ '^instagram:[0-9]{1,40}$')
  );
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_messages'::regclass AND conname='ck_me_message_origin') THEN
  ALTER TABLE socialmei.me_messages ADD CONSTRAINT ck_me_message_origin CHECK (
   (origin='synthetic' AND length(external_message_id)<=120) OR
   (origin='instagram' AND octet_length(external_message_id) BETWEEN 1 AND 1024 AND external_message_id ~ '^[!-~]+$')
  );
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_external_messages'::regclass AND conname='ck_me_external_origin') THEN
  ALTER TABLE socialmei.me_external_messages ADD CONSTRAINT ck_me_external_origin CHECK (
   (origin='synthetic' AND account_ref LIKE 'synthetic:%' AND length(external_message_id)<=120) OR
   (origin='instagram' AND channel='instagram' AND account_ref ~ '^instagram:[0-9]{1,40}$' AND octet_length(external_message_id) BETWEEN 1 AND 1024 AND external_message_id ~ '^[!-~]+$')
  );
 END IF;
END;
$migration$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_me_conversation_origin ON socialmei.me_conversations(workspace_id,id,origin);
CREATE UNIQUE INDEX IF NOT EXISTS ux_me_message_origin ON socialmei.me_messages(workspace_id,id,origin);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ig_meta_connection_account ON socialmei.ig_meta_connections(workspace_id,id,external_account_id);
DO $migration$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_messages'::regclass AND conname='fk_me_message_origin') THEN
  ALTER TABLE socialmei.me_messages ADD CONSTRAINT fk_me_message_origin FOREIGN KEY(workspace_id,conversation_id,origin)
   REFERENCES socialmei.me_conversations(workspace_id,id,origin) ON DELETE CASCADE;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_external_messages'::regclass AND conname='fk_me_external_origin') THEN
  ALTER TABLE socialmei.me_external_messages ADD CONSTRAINT fk_me_external_origin FOREIGN KEY(workspace_id,message_id,origin)
   REFERENCES socialmei.me_messages(workspace_id,id,origin) ON DELETE CASCADE;
 END IF;
END;
$migration$;

CREATE TABLE IF NOT EXISTS socialmei.ig_meta_ingress_events (
 external_account_id VARCHAR(40) NOT NULL CHECK (external_account_id ~ '^[0-9]{1,40}$'),
 event_key CHAR(64) NOT NULL CHECK (event_key ~ '^[0-9a-f]{64}$'),
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 connection_id UUID NOT NULL,
 kind TEXT NOT NULL CHECK (kind IN ('message','echo','receipt','unsupported')),
 fingerprint CHAR(64) NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
 status TEXT NOT NULL CHECK (status IN ('processed','ignored')),
 message_id BIGINT,
 message_origin TEXT NOT NULL DEFAULT 'instagram' CHECK (message_origin='instagram'),
 received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(external_account_id,event_key),
 FOREIGN KEY(workspace_id,connection_id,external_account_id)
  REFERENCES socialmei.ig_meta_connections(workspace_id,id,external_account_id),
 FOREIGN KEY(workspace_id,message_id,message_origin)
  REFERENCES socialmei.me_messages(workspace_id,id,origin),
 CHECK ((status='processed')=(message_id IS NOT NULL)),
 CHECK ((kind='message')=(status='processed'))
);
CREATE INDEX IF NOT EXISTS ix_ig_meta_ingress_workspace ON socialmei.ig_meta_ingress_events(workspace_id,received_at DESC);
