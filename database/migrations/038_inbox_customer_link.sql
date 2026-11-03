-- Manual CRM association only. No matching, provider configuration or sending.
ALTER TABLE socialmei.me_conversations ADD COLUMN IF NOT EXISTS cliente_id BIGINT;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.me_conversations'::regclass AND conname='fk_me_conversation_workspace_customer') THEN
        ALTER TABLE socialmei.me_conversations
            ADD CONSTRAINT fk_me_conversation_workspace_customer
            FOREIGN KEY(workspace_id,cliente_id)
            REFERENCES socialmei.crm_clientes(workspace_id,id)
            ON DELETE SET NULL(cliente_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_me_conversation_customer
    ON socialmei.me_conversations(workspace_id,cliente_id) WHERE cliente_id IS NOT NULL;

-- FK-driven unlink on customer deletion must invalidate an open association form.
CREATE OR REPLACE FUNCTION socialmei.me_customer_link_revision() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.cliente_id IS DISTINCT FROM OLD.cliente_id AND NEW.revision=OLD.revision THEN
        NEW.revision := OLD.revision+1;
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_me_customer_link_revision ON socialmei.me_conversations;
CREATE TRIGGER trg_me_customer_link_revision BEFORE UPDATE OF cliente_id
    ON socialmei.me_conversations FOR EACH ROW
    EXECUTE FUNCTION socialmei.me_customer_link_revision();
