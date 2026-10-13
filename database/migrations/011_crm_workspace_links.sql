-- Impede vínculos de CRM/importação entre negócios diferentes.
-- Não corrige nem exclui registros: inconsistências existentes bloqueiam a transação.
-- Aplicar pelo migrador, com backup prévio e janela de manutenção.

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

CREATE UNIQUE INDEX IF NOT EXISTS ux_crm_products_workspace_id
    ON socialmei.crm_produtos (workspace_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_crm_sales_workspace_id
    ON socialmei.crm_vendas (workspace_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_crm_finance_workspace_id
    ON socialmei.crm_financeiro (workspace_id, id);

DO $migration$
DECLARE
    relationship RECORD;
BEGIN
    FOR relationship IN
        SELECT * FROM (VALUES
            ('crm_vendas', 'cliente_id', 'crm_clientes', 'fk_crm_sales_workspace_customer', 'SET NULL (cliente_id)'),
            ('crm_vendas', 'produto_id', 'crm_produtos', 'fk_crm_sales_workspace_product', 'SET NULL (produto_id)'),
            ('crm_financeiro', 'cliente_id', 'crm_clientes', 'fk_crm_finance_workspace_customer', 'SET NULL (cliente_id)'),
            ('crm_cliente_importacoes', 'cliente_id', 'crm_clientes', 'fk_crm_customer_import_workspace', 'SET NULL (cliente_id)'),
            ('crm_produto_importacoes', 'produto_id', 'crm_produtos', 'fk_crm_product_import_workspace', 'SET NULL (produto_id)'),
            ('crm_venda_importacoes', 'venda_id', 'crm_vendas', 'fk_crm_sale_import_workspace', 'NO ACTION'),
            ('crm_financeiro_importacoes', 'lancamento_id', 'crm_financeiro', 'fk_crm_finance_import_workspace', 'NO ACTION')
        ) AS links(table_name, column_name, target_table, constraint_name, delete_action)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = format('socialmei.%I', relationship.table_name)::regclass
              AND conname = relationship.constraint_name
        ) THEN
            EXECUTE format(
                'ALTER TABLE socialmei.%I ADD CONSTRAINT %I FOREIGN KEY (workspace_id, %I) REFERENCES socialmei.%I (workspace_id, id) ON DELETE %s NOT VALID',
                relationship.table_name, relationship.constraint_name,
                relationship.column_name, relationship.target_table, relationship.delete_action
            );
        END IF;
        EXECUTE format(
            'ALTER TABLE socialmei.%I VALIDATE CONSTRAINT %I',
            relationship.table_name, relationship.constraint_name
        );
    END LOOP;
END;
$migration$;
