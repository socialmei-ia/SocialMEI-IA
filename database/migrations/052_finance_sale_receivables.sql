ALTER TABLE socialmei.crm_financeiro ADD COLUMN IF NOT EXISTS venda_id BIGINT;
DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'socialmei.crm_financeiro'::regclass
          AND conname = 'fk_crm_finance_workspace_sale'
    ) THEN
        ALTER TABLE socialmei.crm_financeiro
            ADD CONSTRAINT fk_crm_finance_workspace_sale FOREIGN KEY (workspace_id,venda_id)
            REFERENCES socialmei.crm_vendas(workspace_id,id);
    END IF;
END
$migration$;
CREATE UNIQUE INDEX IF NOT EXISTS ux_financeiro_venda_ativa
    ON socialmei.crm_financeiro(workspace_id,venda_id)
    WHERE venda_id IS NOT NULL AND NOT excluida;
