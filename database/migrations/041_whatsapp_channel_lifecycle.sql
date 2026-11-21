-- Prepared only. Preserve channel identities and every historical tenant FK.
ALTER TABLE socialmei.crm_canais ADD COLUMN IF NOT EXISTS retired_at TIMESTAMPTZ;
DO $migration$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='socialmei.crm_canais'::regclass AND conname='ck_channel_retirement') THEN
  ALTER TABLE socialmei.crm_canais ADD CONSTRAINT ck_channel_retirement
   CHECK(retired_at IS NULL OR (NOT ativo AND NOT ingress_provisioned AND NOT envio_habilitado));
 END IF;
END;$migration$;
-- Disabled reservations remain exclusive. Only an explicitly retired generation
-- releases the genuine instance/session; no alias or historical row is changed.
CREATE UNIQUE INDEX IF NOT EXISTS ux_channel_current_session
 ON socialmei.crm_canais(provedor,instancia,sessao) WHERE retired_at IS NULL;
ALTER TABLE socialmei.crm_canais DROP CONSTRAINT IF EXISTS crm_canais_provedor_instancia_sessao_key;

CREATE TABLE IF NOT EXISTS socialmei.wa_channel_handovers (
 id UUID PRIMARY KEY,
 actor_id BIGINT NOT NULL REFERENCES socialmei.users(id) ON DELETE RESTRICT,
 target_owner_id BIGINT NOT NULL REFERENCES socialmei.users(id) ON DELETE RESTRICT,
 source_workspace_id BIGINT NOT NULL,
 source_channel_id BIGINT NOT NULL,
 target_workspace_id BIGINT NOT NULL,
 target_channel_id BIGINT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('reserved','active','rolled_back')),
 fingerprint CHAR(64) NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$'),
 previous_channel JSONB NOT NULL CHECK(jsonb_typeof(previous_channel)='object'),
 reviewed_draft_ids JSONB NOT NULL CHECK(jsonb_typeof(reviewed_draft_ids)='array'),
 ingress_after TIMESTAMPTZ NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 activated_at TIMESTAMPTZ,
 rolled_back_at TIMESTAMPTZ,
 FOREIGN KEY(source_workspace_id,source_channel_id) REFERENCES socialmei.crm_canais(workspace_id,id) ON DELETE RESTRICT,
 FOREIGN KEY(target_workspace_id,target_channel_id) REFERENCES socialmei.crm_canais(workspace_id,id) ON DELETE RESTRICT,
 CHECK(source_workspace_id<>target_workspace_id),
 CHECK((status='rolled_back')=(rolled_back_at IS NOT NULL)),
 UNIQUE(target_workspace_id,target_channel_id)
);
