-- Amplia o contrato sem alterar a migration 002 ou o histórico de atendimento.
ALTER TABLE socialmei.crm_clientes
    ADD COLUMN IF NOT EXISTS cidade VARCHAR(160),
    ADD COLUMN IF NOT EXISTS desde VARCHAR(160),
    ADD COLUMN IF NOT EXISTS categoria VARCHAR(160),
    ADD COLUMN IF NOT EXISTS cadastro_original_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS observacao_atualizada_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(2048),
    ADD COLUMN IF NOT EXISTS foto VARCHAR(2048),
    ADD COLUMN IF NOT EXISTS ultima VARCHAR(80),
    ADD COLUMN IF NOT EXISTS total NUMERIC CHECK (total >= 0),
    ADD COLUMN IF NOT EXISTS pendente NUMERIC CHECK (pendente >= 0),
    ADD COLUMN IF NOT EXISTS versao BIGINT NOT NULL DEFAULT 1 CHECK (versao > 0);

COMMENT ON COLUMN socialmei.crm_clientes.total IS
    'Snapshot legado do navegador; não é saldo calculado de vendas remotas.';
COMMENT ON COLUMN socialmei.crm_clientes.pendente IS
    'Snapshot legado do navegador; não é saldo calculado do financeiro remoto.';
COMMENT ON COLUMN socialmei.crm_clientes.ultima IS
    'Texto legado de última atividade; não deve ser interpretado como timestamp.';
COMMENT ON COLUMN socialmei.crm_clientes.cadastro_original_em IS
    'Data original do cadastro local, independente de criado_em no servidor.';
