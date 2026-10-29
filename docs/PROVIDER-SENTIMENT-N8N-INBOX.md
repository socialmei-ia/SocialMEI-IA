# Sentimento real na Caixa — ponte opt-in n8n / FastAPI

**Estado:** candidata de desenvolvimento para revisão, não implantada. Sem chamada real à AWS/n8n/Groq/WAHA/Meta, sem envios e sem alteração de workflows publicados. Derivada do inventário vivo de 56 workflows e dos contratos publicados no n8n de 28/10/2026.

## Por que uma ponte nova

As mensagens externas validadas já entram no banco pelas rotas preparadas de ingresso Meta (HMAC SHA256) e WAHA (HMAC SHA512). O enriquecimento legado de `message_enrichment.py` faz **heurística somente para dados sintéticos**; não deve ser promovido a IA real. A classificação de sentimento não é envio de mensagem e não deve ativar um segundo remetente. O objetivo desta entrega é **apenas classificar e exibir** mensagens verificadas.

## Backend e banco

- `database/migrations/033_provider_sentiment_jobs.sql`: tabela própria por `(workspace_id,message_id)`, FK ao mesmo workspace da mensagem, lease por mensagem, até 3 tentativas, saída imutável quando concluída.
- `POST /internal/message-enrichment/provider/claims`: seleciona até 10 mensagens de texto já persistidas por ingressos oficiais e com `origin in ('instagram','waha')`, dos últimos sete dias. Cada mensagem recebe um `claim_id` aleatório e lease de cinco minutos. Duas consultas simultâneas não reservam a mesma mensagem. Resposta contém somente `claim_id,message_id,origin,text,attempt`; não transfere ID de workspace ao n8n. A repetição após vencimento do lease pode gastar uma nova chamada ao modelo, mas não registra dois resultados.
- `POST /internal/message-enrichment/provider/results`: aceita `claim_id,sentiment,confidence,explanation` com valores fechados. Grava somente para claim atual. Repetição exata retorna `replayed:true`; alteração do resultado concluído retorna 409. Claim antiga após novo lease retorna 404.
- `GET /api/v1/message-enrichment/conversations`: a sessão do negócio correspondente recebe `provider_analysis` somente nas mensagens de origem Instagram ou WAHA, nunca por conta/nome fornecido pelo n8n; no frontend aparece rótulo discreto **sentimento positivo/negativo/neutro/indefinido (automação)**. A mensagem original não é modificada.
- Não há geração de respostas, alteração da outbox, callback externo público ou envio para Meta/WAHA.

## Configuração privada (não criar valores no Git)

Na API, a ponte exige **todas** estas condições:

- `SOCIALMEI_PROVIDER_SENTIMENT_ENABLED=true` (padrão desligado)
- `SOCIALMEI_PROVIDER_SENTIMENT_KEY` exclusivo, com no mínimo 32 caracteres. Não usar chave pública n8n nem token Meta/WAHA.
- `SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS` com os IDs internos dos negócios explicitamente autorizados no piloto, separados por vírgulas, sem espaços. Vazio/inválido bloqueia o serviço (não varre todos os MEIs).
- `SOCIALMEI_SHARED_DATA_ENABLED=true` e `SOCIALMEI_AUTH_ENABLED=true`.
- Migration 033 aplicada **somente após backup + ensaio isolado**. Migrations anteriores não são alteradas.

O arquivo `compose.team.yaml` já encaminha as três flags ao container `team-api`,
mas mantém valores vazios e `false` por padrão. Não é necessário inserir a chave
no código nem alterar a imagem; o operador deverá configurá-las apenas no
`.env.team` privado durante o piloto aprovado.

As rotas `/internal/*` devem ser acessíveis **somente por rede privada**, e nunca encaminhadas pelo Caddy público. n8n usa credencial HTTP Header Auth exclusiva com nome `Authorization` e valor `Bearer <segredo>`. O navegador nunca recebe essa chave. A consulta e os recibos também são limitados aos negócios da allowlist, mesmo com chave de serviço válida.

## Workflow preparado (não ativo)

`n8n-workflows/experimental/provider-sentiment-worker.json` possui oito nós:

1. Schedule Trigger (proposto 1 minuto).
2. Code com `ENABLED=false` até homologação, sem processamento.
3. POST das claims pela rede interna.
4. Desdobramento de até dez itens.
5. AI Agent Groq em português, somente classificação JSON estrita — texto do cliente tratado como dado, sem instruções.
6. Code de validação do formato, com ligação explícita ao claim da mensagem.
7. POST do resultado ao backend, sem retry automático.
8. Nó auxiliar de modelo Groq ligado ao agente.

A versão do modelo do template é sugestão e deve ser conferida contra a instância n8n/Groq e seu plano antes da homologação. Credenciais não são importadas automaticamente. A saída do modelo pode conter texto inválido: nesse caso, a execução falha e o lease expira, permitindo no máximo três tentativas. Não configurar `Continue On Fail` na gravação.

**Não importar/ativar o template em produção enquanto a API candidata, migration, conexão privada e testes com dados fictícios não estiverem homologados.** Este JSON não altera os workflows ativos `LHlqroY2xzvpYAmD` e `NFcJfjvpaUsjh1x1`; tampouco copia segredos deles.

## Aceite de ponta a ponta (após autorização de corte)

1. Mensagem externa de conta/número de teste entra com assinatura real verificada, uma única vez, no workspace correto.
2. n8n faz claim após o commit do ingresso, recebe somente o texto da mensagem correta e classifica; falta/erro de IA não envia nada.
3. Resultado assinado no canal privado é persistido uma vez, mesmo sob duplicidade/replay, e aparece junto da mensagem na Caixa após atualização.
4. Dois negócios recebem resultados separados; transferência de canal, desativação de ingressos, tokens expirados e mensagens sintéticas não autorizam atribuições entre empresas.
5. Falha de rede/timeout permite no máximo 3 tentativas e nunca repete envio (não existe nó de envio nessa ponte).
6. Sanidade do restante do site, CI Node/Python/PostgreSQL descartável, revisão de fluxos, versão de imagem, migrations, backups, rollback, redes, credenciais e observabilidade antes de um deploy.
7. A integração **não** corrige o 403 do Instagram nem vincula automaticamente webhooks Meta à API. Essas etapas seguem P0 próprias.

## Voltar atrás

Desativar o workflow novo, configurar `SOCIALMEI_PROVIDER_SENTIMENT_ENABLED=false`, manter a migration 033 e resultados para rastreabilidade. Não apagar mensagens reais, volumes, banco ou recibos. Se necessário, restaurar apenas a versão anterior da API/frontend, após confirmar mesma keyring, cookies e configuração existente.
