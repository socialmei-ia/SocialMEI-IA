-- Optional catalog details. No channel, automation or external action is enabled.
ALTER TABLE socialmei.crm_produtos
 ADD COLUMN IF NOT EXISTS categoria VARCHAR(80) NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS descricao VARCHAR(2000) NOT NULL DEFAULT '';
