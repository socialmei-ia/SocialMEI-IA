-- Server-provisioned reception only. No session, pairing or sender is activated.
ALTER TABLE socialmei.crm_canais ADD COLUMN IF NOT EXISTS ingress_provisioned BOOLEAN NOT NULL DEFAULT FALSE;
DO $migration$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.crm_canais'::regclass AND conname='ck_waha_provisioned_account') THEN
  ALTER TABLE socialmei.crm_canais ADD CONSTRAINT ck_waha_provisioned_account CHECK(NOT ingress_provisioned OR (identificador_conta IS NOT NULL AND identificador_conta ~ '^[0-9]{1,40}@c[.]us$'));
 END IF;
END;$migration$;
CREATE UNIQUE INDEX IF NOT EXISTS ux_waha_channel_account ON socialmei.crm_canais(workspace_id,id,identificador_conta);
CREATE UNIQUE INDEX IF NOT EXISTS ux_waha_active_account ON socialmei.crm_canais(identificador_conta) WHERE ingress_provisioned AND ativo;
ALTER TABLE socialmei.crm_eventos_canal ADD COLUMN IF NOT EXISTS waha_account_snapshot VARCHAR(255);
ALTER TABLE socialmei.crm_eventos_canal ADD COLUMN IF NOT EXISTS waha_event_key CHAR(64);
ALTER TABLE socialmei.crm_eventos_canal ADD COLUMN IF NOT EXISTS inbox_message_id BIGINT;
ALTER TABLE socialmei.crm_eventos_canal ADD COLUMN IF NOT EXISTS inbox_origin TEXT;
ALTER TABLE socialmei.crm_eventos_canal ALTER COLUMN mensagem_externa_id TYPE VARCHAR(1024);
DO $migration$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.crm_eventos_canal'::regclass AND conname='ck_waha_ingress_event') THEN
  ALTER TABLE socialmei.crm_eventos_canal ADD CONSTRAINT ck_waha_ingress_event CHECK(
   (waha_event_key IS NULL AND waha_account_snapshot IS NULL AND inbox_message_id IS NULL AND inbox_origin IS NULL) OR
   (waha_event_key IS NOT NULL AND waha_event_key ~ '^[0-9a-f]{64}$' AND waha_account_snapshot IS NOT NULL AND inbox_origin IS NOT NULL AND inbox_origin='waha' AND status IN ('processado','ignorado') AND ((status='processado')=(inbox_message_id IS NOT NULL)) AND mensagem_id IS NULL));
  ALTER TABLE socialmei.crm_eventos_canal ADD CONSTRAINT fk_waha_ingress_account FOREIGN KEY(workspace_id,canal_id,waha_account_snapshot) REFERENCES socialmei.crm_canais(workspace_id,id,identificador_conta);
  ALTER TABLE socialmei.crm_eventos_canal ADD CONSTRAINT fk_waha_ingress_inbox FOREIGN KEY(workspace_id,inbox_message_id,inbox_origin) REFERENCES socialmei.me_messages(workspace_id,id,origin);
 END IF;
END;$migration$;
CREATE UNIQUE INDEX IF NOT EXISTS ux_waha_ingress_global ON socialmei.crm_eventos_canal(waha_account_snapshot,waha_event_key) WHERE waha_event_key IS NOT NULL;
ALTER TABLE socialmei.me_conversations DROP CONSTRAINT IF EXISTS ck_me_conversation_origin;
ALTER TABLE socialmei.me_conversations ADD CONSTRAINT ck_me_conversation_origin CHECK(
 (origin='synthetic' AND account_ref LIKE 'synthetic:%' AND contact_ref LIKE 'synthetic:%') OR
 (origin='instagram' AND channel='instagram' AND account_ref ~ '^instagram:[0-9]{1,40}$' AND contact_ref ~ '^instagram:[0-9]{1,40}$') OR
 (origin='waha' AND channel='whatsapp' AND account_ref ~ '^waha:[0-9]{1,40}@c[.]us$' AND contact_ref ~ '^waha:([0-9]{1,40}@c[.]us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)$'));
ALTER TABLE socialmei.me_messages DROP CONSTRAINT IF EXISTS ck_me_message_origin;
ALTER TABLE socialmei.me_messages ADD CONSTRAINT ck_me_message_origin CHECK(
 (origin='synthetic' AND length(external_message_id)<=120) OR
 (origin IN ('instagram','waha') AND octet_length(external_message_id) BETWEEN 1 AND 1024 AND external_message_id ~ '^[!-~]+$'));
ALTER TABLE socialmei.me_external_messages DROP CONSTRAINT IF EXISTS ck_me_external_origin;
ALTER TABLE socialmei.me_external_messages ADD CONSTRAINT ck_me_external_origin CHECK(
 (origin='synthetic' AND account_ref LIKE 'synthetic:%' AND length(external_message_id)<=120) OR
 (origin='instagram' AND channel='instagram' AND account_ref ~ '^instagram:[0-9]{1,40}$' AND octet_length(external_message_id) BETWEEN 1 AND 1024 AND external_message_id ~ '^[!-~]+$') OR
 (origin='waha' AND channel='whatsapp' AND account_ref ~ '^waha:[0-9]{1,40}@c[.]us$' AND octet_length(external_message_id) BETWEEN 1 AND 1024 AND external_message_id ~ '^[!-~]+$'));
