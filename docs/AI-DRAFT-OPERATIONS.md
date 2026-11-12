# Rascunhos com IA — operação opt-in, sem envio

## O que está pronto
O backend oferece `POST /api/v1/message-enrichment/conversations/{id}/assistant-draft` para o **owner/admin autenticado**, enviando `{"expected_revision": N}` após consultar a revisão da conversa no endpoint `assistant-context`. A resposta inclui `draft`, `send_enabled:false`, `persisted:false` e `requires_human_review:true`.

O código não envia mensagens à Meta/WhatsApp, não aprova rascunhos, não salva o texto no CRM e não aciona n8n. A aplicação verifica a revisão da conversa **antes e depois** da chamada ao modelo; mudanças durante o processamento retornam `409`. O destino HTTP é fixo (Groq HTTPS), sem seguir redirecionamentos, sem executar ferramentas e com timeout.

## Configuração privada requerida
Ativar **somente** após autorizar o tratamento dos dados de mensagens por provedor externo, revisar LGPD/termos/retenção do prestador e limitar as contas permitidas.

- `SOCIALMEI_AI_DRAFT_ENABLED=true` (padrão desativado)
- `SOCIALMEI_AI_DRAFT_WORKSPACES=<IDs numéricos autorizados separados por vírgula>`
- `SOCIALMEI_GROQ_API_KEY=<chave privada do servidor>`, nunca commitar ou compartilhar no chat
- `SOCIALMEI_AI_DRAFT_MODEL=openai/gpt-oss-20b` (ou outro modelo válido e homologado)

A conta ChatGPT Plus não fornece uma chave de API automaticamente. A utilização de Groq tem termos, limites de uso e condições de retenção próprios. Mensagens recentes podem conter dados pessoais inseridos pelos clientes; revisar minimização e base legal **antes** de habilitar. Preços e catálogo são dados reais do workspace autorizado, mas o modelo pode errar: **revisão humana é obrigatória**.

## Critérios de homologação
1. Usar **dois workspaces de teste** e contas autorizadas, sem dados reais, para criar conversas independentes e clientes diferentes. Conferir `404` para conversas estrangeiras e `403` para papéis sem permissão.
2. Sem variável ou chave privada: responder `503` **antes de chamar o provedor**.
3. Editar a conversa entre consulta e resposta do modelo: responder `409` sem expor o rascunho obsoleto.
4. Simular erro, timeout, redirecionamento e saída inválida do provedor: responder `503` sem encaminhar texto parcial.
5. Confirmar ausência de novos registros em `wa_bot_decisions`, `ig_menu_replies` e trabalhos de envio. Depois disso, revisar manualmente rascunhos de preços, horários, dúvidas e casos sensíveis.

## Implantação
A PR #227 é uma candidata, **não um deploy**. Antes da publicação: validar backups e rollback, webhook Meta/OAuth, conexões WAHA, scopes, vinculação do CRM e opção de agendamento por workspace. Fazer um canário real com contas da equipe, respeitando a confirmação humana, e só então expandir gradualmente. Nenhuma configuração privada pode ser inferida apenas pelo CI. Não alterar Prisma ou migrations para este fluxo.
