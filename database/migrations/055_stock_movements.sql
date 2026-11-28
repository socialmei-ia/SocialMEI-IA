CREATE TABLE IF NOT EXISTS socialmei.stock_movements (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL,
    product_version BIGINT NOT NULL,
    sale_id BIGINT,
    actor_id BIGINT,
    operation_id UUID,
    previous_stock BIGINT NOT NULL CHECK (previous_stock >= 0),
    current_stock BIGINT NOT NULL CHECK (current_stock >= 0),
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 1 AND 240),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (previous_stock <> current_stock)
);
CREATE INDEX IF NOT EXISTS ix_stock_movements_product
    ON socialmei.stock_movements(workspace_id,product_id,id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ux_stock_movements_operation
    ON socialmei.stock_movements(workspace_id,product_id,operation_id)
    WHERE operation_id IS NOT NULL AND sale_id IS NULL;

CREATE OR REPLACE FUNCTION socialmei.capture_stock_movement() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    context JSONB := COALESCE(NULLIF(current_setting('socialmei.stock_context', true), ''), '{}')::jsonb;
    before_stock BIGINT := 0;
    after_stock BIGINT := COALESCE(NEW.estoque, 0);
    reason TEXT;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        before_stock := COALESCE(OLD.estoque, 0);
    END IF;
    -- Consume metadata even when this statement does not move stock.
    PERFORM set_config('socialmei.stock_context', '', true);
    IF before_stock = after_stock THEN
        RETURN NEW;
    END IF;
    IF (context->>'workspace_id') IS DISTINCT FROM NEW.workspace_id::text
        OR (TG_OP = 'UPDATE' AND (context->>'product_id') IS DISTINCT FROM NEW.id::text) THEN
        context := '{}'::jsonb;
    END IF;
    reason := COALESCE(context->>'reason',
        CASE WHEN TG_OP = 'INSERT' THEN 'Saldo inicial do produto' ELSE 'Alteração de estoque sem origem informada' END);
    INSERT INTO socialmei.stock_movements
        (workspace_id,product_id,product_version,sale_id,actor_id,operation_id,previous_stock,current_stock,reason)
    VALUES (NEW.workspace_id,NEW.id,NEW.versao,(context->>'sale_id')::bigint,
        (context->>'actor_id')::bigint,(context->>'operation_id')::uuid,before_stock,after_stock,reason);
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS capture_stock_movement ON socialmei.crm_produtos;
CREATE TRIGGER capture_stock_movement
    AFTER INSERT OR UPDATE OF estoque ON socialmei.crm_produtos
    FOR EACH ROW EXECUTE FUNCTION socialmei.capture_stock_movement();
