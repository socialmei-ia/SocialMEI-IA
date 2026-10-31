# Análise de sentimento — fluxo n8n para mensagens reais verificadas

**Estado:** export implementado, **inativo e não importado na instância viva**. Não substitui os workflows do colega nem publica/enfila respostas WhatsApp ou Instagram. Existe para concluir a ponte com o backend `provider_sentiment.py` após validação operacional.

## Fluxo implementado

Arquivo: `n8n-workflows/equipe/02-sentimento-mensagens-verificadas.json` (6 nós).

1. Gatilho agendado, a cada minuto **somente se o workflow for ativado**.
2. POST `/internal/message-enrichment/provider/claims` na API privada: requer Bearer específico de análise. API retorna no máximo 10 mensagens já persistidas e verificadas, restritas à allowlist configurada no servidor. Não coleta dados diretamente do WAHA ou Meta.
3. Código valida `schema_version=1`, `send_enabled=false`, o UUID do claim, tipo de origem, tamanho do texto e limite de lote. Lote vazio interrompe a execução sem chamar IA.
4. POST `https://api.groq.com/openai/v1/chat/completions` usando `llama-3.1-8b-instant`, `response_format=json_object`, temperatura zero e um prompt de classificação **sem geração de respostas**. A mensagem é tratada como dado não confiável.
5. Código valida estritamente `sentiment` (`positive|negative|neutral|uncertain`), `confidence` (`low|medium|high`) e explicação curta em português, sem campos adicionais. Incompatibilidades interrompem o lote; a API retentará um claim expirado até 3 vezes.
6. POST `/internal/message-enrichment/provider/results` com o mesmo claim e classificação. O backend agora recusa resultados de claims expirados; aceita replay idempotente de resultado igual e rejeita replay divergente.

O fluxo **não possui webhooks, acesso direto ao PostgreSQL, envio WAHA/Meta, HTTP para destinatários, publicação de mídia, manipulação de contas nem criação de clientes**.

## Pré-requisitos para ativar, nesta ordem

- Conferir se migrations 033 e versões dos serviços correspondem à release aprovada. Obter backup com restauração validada, configuração privada e plano de rollback. Não mudar a stack inteira.
- Validar com o operador do n8n os workflows **salvos e publicados**, inclusive o de análise de sentimento antigo (`K8Z9SVLEsR0yKVPc` no inventário histórico). Garantir que exista **um único classificador** consumindo a nova fila, e que não fique um respondedor de mensagens duplicado. A identificação histórica não comprova seu estado atual.
- Garantir rota de rede privada do container n8n até API FastAPI sem publicar endpoints internos abertos na internet. Substituir os dois URLs `https://CONFIGURAR_API_PRIVADA` por uma origem efetivamente acessível e autorizada, com TLS verificado. Não definir URL pública sem gate de autenticação/limitação.
- Criar no cofre de credenciais n8n **duas** credenciais do tipo HTTP Header Auth, separadas: `Authorization: Bearer <chave-serviço-provider-sentiment>` para ambos os nós da API; `Authorization: Bearer <token-Groq>` somente no nó Groq. Não copiar os valores para export, GitHub, logs nem navegador. Evitar reutilizar n8n API key, segredo HMAC WAHA, token Meta, SMTP ou segredo do bot.
- Backend: `SOCIALMEI_PROVIDER_SENTIMENT_ENABLED=true`, `SOCIALMEI_PROVIDER_SENTIMENT_KEY` com 32+ caracteres gerados privadamente, `SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS=1`, autenticação ativa e shared-data ativo. Sem esses gates o endpoint retorna 503/401 e não deve ser forçado.
- **Privacidade:** a mensagem do cliente é compartilhada com o serviço Groq. Obter aprovação de tratamento/consentimento/aviso conforme política do produto antes de ativar dados reais. Configuração deste export desliga persistência de execuções de sucesso/erro/manuais no n8n; verificar políticas e registros reais do serviço antes de usar.
- Testar **primeiro num ambiente isolado com dados fictícios**, depois com uma mensagem recebida de uma conta de teste autorizada. Comparar a classificação persistida, expiração, repetição, conta/workspace, revisão da Caixa e ausência de mensagem enviada. Não iniciar automaticamente com backlog real.
- Após ativação controlada, acompanhar logs redigidos, tempos de resposta, limite de chamadas e falhas do Groq; confirmar que a análise aparece na Caixa após a atualização da PR #159. A execução bem-sucedida do nó não substitui confirmação na interface.

## Comportamento em falhas

A solicitação de lote tem lease de 5 minutos. Se o Groq falhar ou retornar JSON incorreto, o fluxo falha fechado, sem armazenar resultado falso; o backend pode reivindicar novamente quando expirar, até três tentativas. Resultado tardio de claim expirado retorna 404 até reivindicar outro. Se a API retornar 401/503, **não** ativar fallback genérico nem usar outro workspace. Se nenhuma mensagem estiver disponível, o fluxo para sem gastar crédito de IA.

Os campos de confiança são fornecidos pelo modelo, não representam calibração estatística. Mensagens ambíguas devem ser `uncertain` e não podem gerar respostas comerciais ou inferências sobre características pessoais.

## Reversão

Desativar só o workflow novo e revogar a credencial técnica específica. Manter dados classificados e tabelas aditivas; não apagar banco ou outros workflows, e não reativar um antigo classificador sem revisar o responsável/consumidor da fila. O código existente da Caixa continua operando sem essa integração quando o backend está desativado.

## Escopo dos testes

`tests/provider-sentiment-n8n.test.cjs` valida a topologia do export, ausência de nós de envio, schema das tarefas, limite de lote, segurança do parser e idempotência da correlação de claims com simulações locais. `python-service/test_provider_sentiment.py` cobre autenticação, autorização, replays e proteção de lease por SQL. **CI não testa credenciais Groq, conectividade do n8n, classificação real ou execução em produção.**
