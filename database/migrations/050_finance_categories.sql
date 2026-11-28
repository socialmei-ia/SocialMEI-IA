ALTER TABLE socialmei.crm_financeiro
    ADD COLUMN IF NOT EXISTS categoria VARCHAR(80) NOT NULL DEFAULT '';
