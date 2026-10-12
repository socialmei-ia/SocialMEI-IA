-- Base de atendimento da equipe. Nao ativa canais, webhooks ou envios.
-- As tabelas legadas clientes/conversas/mensagens permanecem intactas.

-- Necessario para o vinculo composto que impede associar outro workspace.
CREATE UNIQUE INDEX IF NOT EXISTS ux_crm_clientes_workspace_id
    ON socialmei.crm_clientes (workspace_id, id);

CREATE TABLE IF NOT EXISTS socialmei.crm_canais (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES socialmei.workspaces(id) ON DELETE RESTRICT,
    canal VARCHAR(20) NOT NULL DEFAULT 'whatsapp' CHECK (canal = 'whatsapp'),
    provedor VARCHAR(40) NOT NULL DEFAULT 'waha' CHECK (provedor = 'waha'),
    instancia VARCHAR(80) NOT NULL CHECK (instancia ~ '^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$'),
    sessao VARCHAR(160) NOT NULL CHECK (length(btrim(sessao)) > 0 AND sessao = btrim(sessao)),
    nome VARCHAR(160) NOT NULL DEFAULT '',
    identificador_conta VARCHAR(255) CHECK (identificador_conta IS NULL OR length(btrim(identificador_conta)) > 0),
    ativo BOOLEAN NOT NULL DEFAULT false,
    envio_habilitado BOOLEAN NOT NULL DEFAULT false,
    estado_provedor VARCHAR(80),
    verificado_em TIMESTAMPTZ,
    versao BIGINT NOT NULL DEFAULT 1 CHECK (versao > 0),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (NOT envio_habilitado OR ativo),
    UNIQUE (workspace_id, id),
    -- Uma sessao de uma instancia pertence a um unico workspace.
    UNIQUE (provedor, instancia, sessao)
);

CREATE TABLE IF NOT EXISTS socialmei.crm_conversas_canal (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL,
    canal_id BIGINT NOT NULL,
    identificador_externo VARCHAR(255) NOT NULL CHECK (length(btrim(identificador_externo)) > 0),
    tipo VARCHAR(20) NOT NULL DEFAULT 'direta' CHECK (tipo IN ('direta', 'grupo', 'canal', 'outro')),
    cliente_id BIGINT,
    nome VARCHAR(160) NOT NULL DEFAULT '',
    status VARCHAR(30) NOT NULL DEFAULT 'aberto' CHECK (status IN ('aberto', 'em_andamento', 'aguardando_cliente', 'concluido')),
    nao_lidas INTEGER NOT NULL DEFAULT 0 CHECK (nao_lidas >= 0),
    ultima_mensagem_em TIMESTAMPTZ,
    versao BIGINT NOT NULL DEFAULT 1 CHECK (versao > 0),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (workspace_id, canal_id) REFERENCES socialmei.crm_canais(workspace_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, cliente_id) REFERENCES socialmei.crm_clientes(workspace_id, id) ON DELETE SET NULL (cliente_id),
    CHECK (cliente_id IS NULL OR tipo = 'direta'),
    UNIQUE (workspace_id, canal_id, identificador_externo),
    UNIQUE (workspace_id, canal_id, id)
);

CREATE INDEX IF NOT EXISTS ix_crm_conversas_canal_ultima
    ON socialmei.crm_conversas_canal (workspace_id, ultima_mensagem_em DESC, id);
CREATE INDEX IF NOT EXISTS ix_crm_conversas_canal_cliente
    ON socialmei.crm_conversas_canal (workspace_id, cliente_id) WHERE cliente_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS socialmei.crm_mensagens_canal (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL,
    canal_id BIGINT NOT NULL,
    conversa_id BIGINT NOT NULL,
    identificador_externo VARCHAR(255) CHECK (identificador_externo IS NULL OR length(btrim(identificador_externo)) > 0),
    operation_id UUID,
    operation_fingerprint CHAR(64) CHECK (operation_fingerprint IS NULL OR operation_fingerprint ~ '^[0-9a-f]{64}$'),
    direcao VARCHAR(10) NOT NULL CHECK (direcao IN ('entrada', 'saida')),
    tipo VARCHAR(20) NOT NULL DEFAULT 'texto' CHECK (tipo IN ('texto', 'imagem', 'audio', 'video', 'documento', 'outro')),
    conteudo TEXT NOT NULL DEFAULT '',
    remetente_externo VARCHAR(255),
    destinatario_externo VARCHAR(255),
    participante_externo VARCHAR(255),
    midia_ref VARCHAR(512),
    midia_mime VARCHAR(160),
    status VARCHAR(20) NOT NULL CHECK (status IN ('recebida', 'rascunho', 'pendente', 'enviada', 'entregue', 'lida', 'falha', 'incerta', 'cancelada')),
    ocorrida_em TIMESTAMPTZ,
    enviada_em TIMESTAMPTZ,
    entregue_em TIMESTAMPTZ,
    lida_em TIMESTAMPTZ,
    versao BIGINT NOT NULL DEFAULT 1 CHECK (versao > 0),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (workspace_id, canal_id, conversa_id) REFERENCES socialmei.crm_conversas_canal(workspace_id, canal_id, id) ON DELETE RESTRICT,
    CHECK ((operation_id IS NULL) = (operation_fingerprint IS NULL)),
    CHECK (
        (direcao = 'entrada' AND identificador_externo IS NOT NULL AND operation_id IS NULL AND status = 'recebida')
        OR (direcao = 'saida' AND operation_id IS NOT NULL AND status <> 'recebida')
        -- message.any tambem informa saidas feitas pelo proprio telefone.
        OR (direcao = 'saida' AND operation_id IS NULL AND identificador_externo IS NOT NULL AND status IN ('enviada', 'entregue', 'lida'))
    ),
    CHECK (status NOT IN ('enviada', 'entregue', 'lida') OR (identificador_externo IS NOT NULL AND enviada_em IS NOT NULL)),
    CHECK (status <> 'entregue' OR entregue_em IS NOT NULL),
    CHECK (status <> 'lida' OR lida_em IS NOT NULL),
    CHECK (entregue_em IS NULL OR enviada_em IS NOT NULL),
    CHECK (direcao = 'saida' OR (enviada_em IS NULL AND entregue_em IS NULL AND lida_em IS NULL)),
    UNIQUE (workspace_id, canal_id, identificador_externo),
    UNIQUE (workspace_id, operation_id),
    UNIQUE (workspace_id, canal_id, id)
);

CREATE INDEX IF NOT EXISTS ix_crm_mensagens_canal_conversa
    ON socialmei.crm_mensagens_canal (workspace_id, conversa_id, ocorrida_em, id);
CREATE INDEX IF NOT EXISTS ix_crm_mensagens_canal_pendentes
    ON socialmei.crm_mensagens_canal (workspace_id, status, criado_em, id)
    WHERE direcao = 'saida' AND status IN ('pendente', 'incerta');

CREATE TABLE IF NOT EXISTS socialmei.crm_eventos_canal (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL,
    canal_id BIGINT NOT NULL,
    chave_evento VARCHAR(255) NOT NULL CHECK (length(btrim(chave_evento)) > 0),
    tipo VARCHAR(80) NOT NULL CHECK (length(btrim(tipo)) > 0),
    fingerprint CHAR(64) NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    mensagem_externa_id VARCHAR(255),
    mensagem_id BIGINT,
    dados_normalizados JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(dados_normalizados) = 'object' AND octet_length(dados_normalizados::text) <= 2000000),
    status VARCHAR(20) NOT NULL DEFAULT 'recebido' CHECK (status IN ('recebido', 'processado', 'falha', 'ignorado')),
    tentativas INTEGER NOT NULL DEFAULT 0 CHECK (tentativas >= 0),
    codigo_erro VARCHAR(80),
    ocorrida_em TIMESTAMPTZ,
    recebido_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processado_em TIMESTAMPTZ,
    FOREIGN KEY (workspace_id, canal_id) REFERENCES socialmei.crm_canais(workspace_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, canal_id, mensagem_id) REFERENCES socialmei.crm_mensagens_canal(workspace_id, canal_id, id) ON DELETE SET NULL (mensagem_id),
    CHECK ((status IN ('processado', 'ignorado')) = (processado_em IS NOT NULL)),
    UNIQUE (workspace_id, canal_id, chave_evento)
);

CREATE INDEX IF NOT EXISTS ix_crm_eventos_canal_pendentes
    ON socialmei.crm_eventos_canal (workspace_id, canal_id, recebido_em, id)
    WHERE status IN ('recebido', 'falha');

COMMENT ON TABLE socialmei.crm_canais IS 'Sessoes de atendimento por instancia/workspace. Ativacao e envio desabilitados por padrao; nenhuma credencial.';
COMMENT ON TABLE socialmei.crm_conversas_canal IS 'Identidade externa por canal, com vinculo explicito a cliente do mesmo workspace; nunca por nome.';
COMMENT ON TABLE socialmei.crm_mensagens_canal IS 'Historico com deduplicacao por canal/ID externo e identidade de operacao para saidas do app. Estado incerta exige conciliacao antes de retry.';
COMMENT ON TABLE socialmei.crm_eventos_canal IS 'Recebimento normalizado e deduplicado de eventos; processamento futuro deve ser transacional e comparar fingerprints.';
COMMENT ON COLUMN socialmei.crm_mensagens_canal.midia_ref IS 'Referencia opaca a armazenamento privado; nunca URL temporaria com credencial, blob ou QR.';
