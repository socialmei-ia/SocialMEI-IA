-- Isolated synthetic message analysis. No legacy channel table is changed.
CREATE TABLE IF NOT EXISTS socialmei.me_conversations (
 id BIGSERIAL PRIMARY KEY CHECK (id <= 9007199254740991),
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 channel TEXT NOT NULL CHECK (channel IN ('whatsapp','instagram')),
 account_ref VARCHAR(110) NOT NULL CHECK (account_ref LIKE 'synthetic:%'),
 contact_ref VARCHAR(110) NOT NULL CHECK (contact_ref LIKE 'synthetic:%'),
 contact_name VARCHAR(120) NOT NULL,
 revision BIGINT NOT NULL DEFAULT 0 CHECK (revision BETWEEN 0 AND 9007199254740991),
 UNIQUE(workspace_id,channel,account_ref,contact_ref), UNIQUE(workspace_id,id)
);
CREATE TABLE IF NOT EXISTS socialmei.me_messages (
 id BIGSERIAL PRIMARY KEY CHECK (id <= 9007199254740991),
 workspace_id BIGINT NOT NULL,
 conversation_id BIGINT NOT NULL,
 external_message_id VARCHAR(120) NOT NULL,
 fingerprint CHAR(64) NOT NULL,
 conversation_revision BIGINT NOT NULL CHECK (conversation_revision BETWEEN 1 AND 9007199254740991),
 text TEXT NOT NULL CHECK (octet_length(text) <= 8192),
 occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 revision BIGINT NOT NULL DEFAULT 1 CHECK (revision BETWEEN 1 AND 9007199254740991),
 FOREIGN KEY(workspace_id,conversation_id) REFERENCES socialmei.me_conversations(workspace_id,id) ON DELETE CASCADE,
 UNIQUE(workspace_id,conversation_id,external_message_id), UNIQUE(workspace_id,id)
);
CREATE TABLE IF NOT EXISTS socialmei.me_external_messages (
 workspace_id BIGINT NOT NULL,
 channel TEXT NOT NULL CHECK (channel IN ('whatsapp','instagram')),
 account_ref VARCHAR(110) NOT NULL CHECK (account_ref LIKE 'synthetic:%'),
 external_message_id VARCHAR(120) NOT NULL,
 message_id BIGINT NOT NULL,
 PRIMARY KEY(workspace_id,channel,account_ref,external_message_id),
 UNIQUE(workspace_id,message_id),
 FOREIGN KEY(workspace_id,message_id) REFERENCES socialmei.me_messages(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS socialmei.me_documents (
 id BIGSERIAL PRIMARY KEY CHECK (id <= 9007199254740991),
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 title VARCHAR(120) NOT NULL,
 content TEXT NOT NULL CHECK (octet_length(content) <= 32768),
 revision BIGINT NOT NULL DEFAULT 1 CHECK (revision BETWEEN 1 AND 9007199254740991),
 expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '30 days',
 deleted_at TIMESTAMPTZ,
 UNIQUE(workspace_id,id)
);
CREATE INDEX IF NOT EXISTS ix_me_documents_scope ON socialmei.me_documents(workspace_id,expires_at) WHERE deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS socialmei.me_jobs (
 id UUID PRIMARY KEY,
 workspace_id BIGINT NOT NULL,
 message_id BIGINT NOT NULL,
 message_revision BIGINT NOT NULL,
 revision BIGINT NOT NULL DEFAULT 1 CHECK (revision BETWEEN 1 AND 9007199254740991),
 status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','pending_review','approved','rejected','invalidated','expired','superseded')),
 attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt BETWEEN 1 AND 3),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '5 minutes',
 result JSONB CHECK (result IS NULL OR jsonb_typeof(result)='object'),
 FOREIGN KEY(workspace_id,message_id) REFERENCES socialmei.me_messages(workspace_id,id) ON DELETE CASCADE,
 UNIQUE(workspace_id,id)
);
CREATE INDEX IF NOT EXISTS ix_me_jobs_message ON socialmei.me_jobs(workspace_id,message_id,message_revision DESC);
CREATE TABLE IF NOT EXISTS socialmei.me_citations (
 workspace_id BIGINT NOT NULL,
 job_id UUID NOT NULL,
 document_id BIGINT NOT NULL,
 document_revision BIGINT NOT NULL,
 PRIMARY KEY(job_id,document_id),
 FOREIGN KEY(workspace_id,job_id) REFERENCES socialmei.me_jobs(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,document_id) REFERENCES socialmei.me_documents(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS socialmei.me_operations (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK (kind IN ('message','enrich','document')),
 operation_id UUID NOT NULL,
 fingerprint CHAR(64) NOT NULL,
 response JSONB NOT NULL CHECK (jsonb_typeof(response)='object'),
 PRIMARY KEY(workspace_id,kind,operation_id)
);
CREATE TABLE IF NOT EXISTS socialmei.me_events (
 event_id UUID PRIMARY KEY,
 job_id UUID NOT NULL REFERENCES socialmei.me_jobs(id) ON DELETE CASCADE,
 attempt INTEGER NOT NULL CHECK (attempt BETWEEN 1 AND 3),
 fingerprint CHAR(64) NOT NULL,
 received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS socialmei.me_limits (
 workspace_id BIGINT PRIMARY KEY REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 bucket TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 count INTEGER NOT NULL CHECK (count BETWEEN 1 AND 60)
);
