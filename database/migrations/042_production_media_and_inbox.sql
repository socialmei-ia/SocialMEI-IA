-- Version the media and inbox objects installed directly in production.
-- Preserve existing data and reject partial installations.
DO $media$
DECLARE
    present integer;
BEGIN
    SELECT count(*) INTO present FROM unnest(ARRAY['socialmei.me_attachment_ai', 'socialmei.me_inbound_attachments', 'socialmei.me_inbound_attachments_id_seq', 'socialmei.me_inbox_hidden', 'socialmei.me_inbound_attachments_conversation_idx']) AS names(name)
    WHERE to_regclass(name) IS NOT NULL;
    IF present = 0 THEN
        --

        CREATE TABLE socialmei.me_attachment_ai (
            attachment_id bigint NOT NULL,
            sha256 text NOT NULL,
            request_id uuid NOT NULL,
            model text NOT NULL,
            status text NOT NULL,
            interpretation text,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            finished_at timestamp with time zone,
            CONSTRAINT me_attachment_ai_check CHECK (((status = 'completed'::text) = (interpretation IS NOT NULL))),
            CONSTRAINT me_attachment_ai_check1 CHECK (((status = 'processing'::text) = (finished_at IS NULL))),
            CONSTRAINT me_attachment_ai_interpretation_check CHECK (((char_length(interpretation) >= 1) AND (char_length(interpretation) <= 3000))),
            CONSTRAINT me_attachment_ai_sha256_check CHECK ((sha256 ~ '^[a-f0-9]{64}$'::text)),
            CONSTRAINT me_attachment_ai_status_check CHECK ((status = ANY (ARRAY['processing'::text, 'completed'::text, 'uncertain'::text])))
        );

        --

        CREATE TABLE socialmei.me_inbound_attachments (
            id bigint NOT NULL,
            workspace_id bigint NOT NULL,
            channel_id bigint NOT NULL,
            conversation_id bigint NOT NULL,
            origin text NOT NULL,
            account_ref text NOT NULL,
            contact_ref text NOT NULL,
            external_message_id text NOT NULL,
            source_event_key text NOT NULL,
            source_fingerprint text NOT NULL,
            media_kind text NOT NULL,
            sha256 text NOT NULL,
            size_bytes bigint NOT NULL,
            storage_key text NOT NULL,
            occurred_at timestamp with time zone NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT me_inbound_attachments_media_kind_check CHECK ((media_kind = ANY (ARRAY['audio'::text, 'imagem'::text, 'documento'::text]))),
            CONSTRAINT me_inbound_attachments_origin_check CHECK ((origin = 'waha'::text)),
            CONSTRAINT me_inbound_attachments_sha256_check CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text)),
            CONSTRAINT me_inbound_attachments_size_bytes_check CHECK (((size_bytes >= 1) AND (size_bytes <= 10485760)))
        );

        --

        ALTER TABLE socialmei.me_inbound_attachments ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
            SEQUENCE NAME socialmei.me_inbound_attachments_id_seq
            START WITH 1
            INCREMENT BY 1
            NO MINVALUE
            NO MAXVALUE
            CACHE 1
        );

        --

        CREATE TABLE socialmei.me_inbox_hidden (
            workspace_id bigint NOT NULL,
            user_id bigint NOT NULL,
            conversation_id bigint NOT NULL,
            last_message_id bigint NOT NULL,
            hidden_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT me_inbox_hidden_last_message_id_check CHECK ((last_message_id >= 0))
        );

        --

        ALTER TABLE ONLY socialmei.me_attachment_ai
            ADD CONSTRAINT me_attachment_ai_pkey PRIMARY KEY (attachment_id);

        --

        ALTER TABLE ONLY socialmei.me_attachment_ai
            ADD CONSTRAINT me_attachment_ai_request_id_key UNIQUE (request_id);

        --

        ALTER TABLE ONLY socialmei.me_inbound_attachments
            ADD CONSTRAINT me_inbound_attachments_pkey PRIMARY KEY (id);

        --

        ALTER TABLE ONLY socialmei.me_inbound_attachments
            ADD CONSTRAINT me_inbound_attachments_workspace_id_channel_id_account_ref__key UNIQUE (workspace_id, channel_id, account_ref, external_message_id);

        --

        ALTER TABLE ONLY socialmei.me_inbox_hidden
            ADD CONSTRAINT me_inbox_hidden_pkey PRIMARY KEY (workspace_id, user_id, conversation_id);

        --

        CREATE INDEX me_inbound_attachments_conversation_idx ON socialmei.me_inbound_attachments USING btree (workspace_id, conversation_id, occurred_at);

        --

        ALTER TABLE ONLY socialmei.me_attachment_ai
            ADD CONSTRAINT me_attachment_ai_attachment_id_fkey FOREIGN KEY (attachment_id) REFERENCES socialmei.me_inbound_attachments(id) ON DELETE CASCADE;

        --

        ALTER TABLE ONLY socialmei.me_inbound_attachments
            ADD CONSTRAINT me_inbound_attachments_workspace_id_conversation_id_fkey FOREIGN KEY (workspace_id, conversation_id) REFERENCES socialmei.me_conversations(workspace_id, id) ON DELETE CASCADE;

        --

        ALTER TABLE ONLY socialmei.me_inbox_hidden
            ADD CONSTRAINT me_inbox_hidden_workspace_id_conversation_id_fkey FOREIGN KEY (workspace_id, conversation_id) REFERENCES socialmei.me_conversations(workspace_id, id) ON DELETE CASCADE;

        --

        ALTER TABLE ONLY socialmei.me_inbox_hidden
            ADD CONSTRAINT me_inbox_hidden_workspace_id_user_id_fkey FOREIGN KEY (workspace_id, user_id) REFERENCES socialmei.workspace_members(workspace_id, user_id) ON DELETE CASCADE;
    ELSIF present <> 5 THEN
        RAISE EXCEPTION 'Partial media/inbox schema; reconcile before migration';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_attachment_ai'::regclass AND conname='me_attachment_ai_pkey')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_attachment_ai'::regclass AND conname='me_attachment_ai_request_id_key')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_inbound_attachments'::regclass AND conname='me_inbound_attachments_pkey')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_inbound_attachments'::regclass AND conname='me_inbound_attachments_workspace_id_channel_id_account_ref__key')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_inbox_hidden'::regclass AND conname='me_inbox_hidden_pkey')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_attachment_ai'::regclass AND conname='me_attachment_ai_attachment_id_fkey')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_inbound_attachments'::regclass AND conname='me_inbound_attachments_workspace_id_conversation_id_fkey')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_inbox_hidden'::regclass AND conname='me_inbox_hidden_workspace_id_conversation_id_fkey')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_inbox_hidden'::regclass AND conname='me_inbox_hidden_workspace_id_user_id_fkey') THEN
        RAISE EXCEPTION 'Existing media/inbox constraints require reconciliation';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='socialmei_candidate040') THEN
        GRANT SELECT,INSERT,UPDATE ON TABLE socialmei.me_attachment_ai TO socialmei_candidate040;
        GRANT SELECT,INSERT ON TABLE socialmei.me_inbound_attachments TO socialmei_candidate040;
        GRANT USAGE ON SEQUENCE socialmei.me_inbound_attachments_id_seq TO socialmei_candidate040;
        GRANT SELECT,INSERT,UPDATE ON TABLE socialmei.me_inbox_hidden TO socialmei_candidate040;
    END IF;
END
$media$;
