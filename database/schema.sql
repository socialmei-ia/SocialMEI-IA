-- SocialMEI.IA - Sprint 3
-- Estrutura inicial para histórico de atendimento.
-- Este arquivo NÃO contém senhas nem credenciais.
-- Aplicar no PostgreSQL pelo pgAdmin ou por um processo de migração controlado.

CREATE SCHEMA IF NOT EXISTS socialmei;

CREATE TABLE IF NOT EXISTS socialmei.clientes (
    id BIGSERIAL PRIMARY KEY,
    nome VARCHAR(160) NOT NULL,
    telefone VARCHAR(40),
    email VARCHAR(255),
    identificador_externo VARCHAR(255),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_clientes_identificador_externo
    ON socialmei.clientes (identificador_externo)
    WHERE identificador_externo IS NOT NULL;

CREATE TABLE IF NOT EXISTS socialmei.conversas (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT NOT NULL REFERENCES socialmei.clientes(id) ON DELETE CASCADE,
    canal VARCHAR(20) NOT NULL CHECK (canal IN ('whatsapp', 'instagram')),
    identificador_externo VARCHAR(255),
    status VARCHAR(30) NOT NULL DEFAULT 'aberto'
        CHECK (status IN ('aberto', 'em_andamento', 'aguardando_cliente', 'concluido')),
    nao_lidas INTEGER NOT NULL DEFAULT 0 CHECK (nao_lidas >= 0),
    ultima_mensagem_em TIMESTAMPTZ,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_conversas_identificador_externo
    ON socialmei.conversas (canal, identificador_externo)
    WHERE identificador_externo IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_conversas_cliente
    ON socialmei.conversas (cliente_id);

CREATE INDEX IF NOT EXISTS ix_conversas_ultima_mensagem
    ON socialmei.conversas (ultima_mensagem_em DESC);

CREATE TABLE IF NOT EXISTS socialmei.mensagens (
    id BIGSERIAL PRIMARY KEY,
    conversa_id BIGINT NOT NULL REFERENCES socialmei.conversas(id) ON DELETE CASCADE,
    identificador_externo VARCHAR(255),
    direcao VARCHAR(10) NOT NULL DEFAULT 'entrada'
        CHECK (direcao IN ('entrada', 'saida')),
    conteudo TEXT NOT NULL,
    enviada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadados JSONB NOT NULL DEFAULT '{}'::jsonb,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mensagens_identificador_externo
    ON socialmei.mensagens (identificador_externo)
    WHERE identificador_externo IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_mensagens_conversa_enviada
    ON socialmei.mensagens (conversa_id, enviada_em);

COMMENT ON SCHEMA socialmei IS 'Dados funcionais do SocialMEI.IA separados das tabelas internas do n8n.';
COMMENT ON TABLE socialmei.clientes IS 'Cadastro mínimo dos clientes usados no atendimento.';
COMMENT ON TABLE socialmei.conversas IS 'Conversas agrupadas por cliente e canal.';
COMMENT ON TABLE socialmei.mensagens IS 'Histórico persistente das mensagens por conversa.';
