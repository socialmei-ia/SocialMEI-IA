-- Manual commercial lifecycle; never changes sales, stock or payment state.
CREATE TABLE IF NOT EXISTS socialmei.crm_opportunities (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 id UUID NOT NULL,
 client_id BIGINT NOT NULL,
 title VARCHAR(160) NOT NULL CHECK(length(btrim(title))>0),
 interest_level VARCHAR(10) NOT NULL CHECK(interest_level IN ('unknown','cold','warm','hot')),
 outcome VARCHAR(10) NOT NULL DEFAULT 'open' CHECK(outcome IN ('open','won','lost')),
 outcome_reason VARCHAR(30) NOT NULL DEFAULT '',
 outcome_note VARCHAR(1000) NOT NULL DEFAULT '',
 sale_id BIGINT,
 revision BIGINT NOT NULL DEFAULT 1 CHECK(revision>0),
 created_by BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 closed_at TIMESTAMPTZ,
 PRIMARY KEY(workspace_id,id),
 FOREIGN KEY(workspace_id,client_id) REFERENCES socialmei.crm_clientes(workspace_id,id),
 FOREIGN KEY(workspace_id,sale_id) REFERENCES socialmei.crm_vendas(workspace_id,id),
 CHECK((outcome='open' AND outcome_reason='' AND closed_at IS NULL) OR
       (outcome='won' AND outcome_reason='sale_completed' AND closed_at IS NOT NULL) OR
       (outcome='lost' AND outcome_reason IN ('gave_up','other_supplier','price','timing','other') AND closed_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_opportunity_sale ON socialmei.crm_opportunities(workspace_id,sale_id) WHERE sale_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_opportunity_list ON socialmei.crm_opportunities(workspace_id,outcome,updated_at DESC,id);
CREATE TABLE IF NOT EXISTS socialmei.crm_opportunity_events (
 id BIGSERIAL PRIMARY KEY,
 workspace_id BIGINT NOT NULL,
 opportunity_id UUID NOT NULL,
 actor_id BIGINT REFERENCES socialmei.users(id) ON DELETE SET NULL,
 action VARCHAR(10) NOT NULL CHECK(action IN ('create','edit','close','reopen','sale')),
 reason VARCHAR(300) NOT NULL DEFAULT '',
 previous JSONB,
 current JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 FOREIGN KEY(workspace_id,opportunity_id) REFERENCES socialmei.crm_opportunities(workspace_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_opportunity_history ON socialmei.crm_opportunity_events(workspace_id,opportunity_id,id);
CREATE TABLE IF NOT EXISTS socialmei.crm_opportunity_operations (
 workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
 operation_id UUID NOT NULL,
 fingerprint CHAR(64) NOT NULL,
 response JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,operation_id)
);
