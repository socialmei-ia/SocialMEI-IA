# Análise de sentimento — workflow já existente do n8n

**Estado:** aperfeiçoado em código, **não instalado/ativado nesta etapa**. Para evitar duplicidade, o projeto mantém **somente** o template pré-existente `n8n-workflows/experimental/provider-sentiment-worker.json`. O segundo export proposto em `equipe/` foi descartado. O fluxo antigo real que pode existir na instância n8n não é alterado por esta PR.

## Contrato preservado e reforçado

O workflow original tem oito nós: agenda → **Piloto protegido** → claims HTTP → validação de itens → agente de classificação → validação do JSON → results HTTP, com o modelo Groq conectado por uma aresta separada de linguagem.

1. **Piloto protegido** permanece com `const ENABLED = false`: nem ativação acidental do export deve iniciar consumo. Só mudar essa trava após verificar todos os pré-requisitos.
2. POST `/internal/message-enrichment/provider/claims`: credencial Bearer específica de análise (não a API key administrativa do n8n). A API seleciona no máximo 10 mensagens previamente verificadas, apenas dos workspaces da allowlist.
3. O nó `Individualizar classificacoes` valida `schema_version=1`, `send_enabled=false`, UUID, origem `waha|instagram`, texto limitado, tentativa 1–3 e lote limitado. Sem itens, a execução termina antes de chamar a IA.
4. O **agente n8n/Groq existente** permanece com o modelo `llama-3.3-70b-versatile`. O prompt trata a mensagem como dado não confiável e restringe a saída a `sentiment`, `confidence` e `explanation`, sem gerar resposta nem copiar dados pessoais.
5. O nó `Validar classificacao` rejeita campos adicionais e enumerações inválidas, exige explicação preenchida e a limita a 120 caracteres Unicode. Não admite campo `suggested_reply`.
6. POST `/internal/message-enrichment/provider/results` grava exclusivamente a classificação. No backend, resultados de claims cujo lease expirou são recusados; resultados já concluídos iguais permanecem idempotentes, divergentes são rejeitados.

**Não há nós WAHA sendText, Direct, publicação, novos webhooks, SQL direto ou novo remetente.** O template não inclui credenciais ou tokens literais e continua com `active:false` e dados de execução desligados.

## Pré-requisitos para qualquer ativação

- Confirmar os workflows salvos **e publicados** do n8n, inclusive a análise histórica `K8Z9SVLEsR0yKVPc`. Identificar com a equipe quem consome a fila. **Não importar ou ativar um segundo consumidor** sem desativação/backup do anterior e sem autorização operacional.
- Confirmar migration 033, imagens API/gateway, backup restaurável, rollback, isolamento do workspace 1 e a disponibilidade da Caixa; a API deve estar recebendo mensagens reais.
- Confirmar conectividade privada do n8n ao serviço `team-api:8000` (URL indicada no template). O repositório **já contém** o override opcional `compose.team-n8n-bridge.yaml`, que anexa somente o n8n à rede `socialmei_team_automation` da API sem expor o PostgreSQL. **Não reaplicar Compose inteiro**: comparar em leitura o override, serviços, redes e mounts efetivos na AWS e realizar alteração controlada com backup e recuperação. A existência do arquivo não comprova que a rede já está ligada na VPS. Não abrir a rota interna na internet.
- Cadastrar no cofre privado do n8n as credenciais HTTP Header Auth de serviço para os dois nós de API e a credencial Groq já prevista no nó LangChain. Não adicionar segredos ao repositório, log ou interface.
- No backend, configurar privadamente `SOCIALMEI_PROVIDER_SENTIMENT_ENABLED=true`, `SOCIALMEI_PROVIDER_SENTIMENT_KEY` de 32+ caracteres, `SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS=1`, autenticação e dados compartilhados ativos. Não ativar o endpoint para todos os MEIs.
- A mensagem do cliente será compartilhada com o serviço Groq. Revisar consentimento, política de tratamento/privacidade e armazenamento do provedor antes de tratar conversas reais. Verificar que a configuração do n8n realmente não salva o conteúdo das execuções.
- Importar apenas em ambiente de teste com credenciais fictícias, testar entrada, lista vazia, expiração, erro Groq, resposta JSON inválida, idempotência, ausência de envios e visualização da análise na Caixa. Em produção, usar somente conta e destinatário de teste autorizados.
- Depois de aprovar e configurar tudo, o responsável pode liberar o **mesmo** fluxo, observando erros, limites e custos. `active:false` e `ENABLED=false` são travas distintas, ambas mantidas nesta PR.

## Falhas e recuperação

O lease da API dura cinco minutos. Uma classificação inválida não é registrada, e a mensagem pode voltar ao lote após expirar, até três tentativas. Um resultado tardio é recusado quando o claim está expirado e não foi concluído. Nunca usar fallback que crie classificação fictícia, envie respostas ou retorne dados de outro workspace. Falha 401/503 significa configuração indisponível; não tentar outra credencial ou rota pública.

Rollback: desativar apenas o workflow, restaurar sua versão anterior exportada/validada, revogar a credencial específica se necessário. Não apagar tabelas, conversas nem os demais workflows.

## Testes

`tests/provider-sentiment-n8n.test.cjs` testa o template **original** de oito nós, preservação da trava, contratos e parser com entradas sintéticas. `python-service/test_provider_sentiment.py` cobre isolamento, autenticação, replay e a cláusula SQL de lease válido. O CI não confirma conectividade Groq/n8n real, autorização de tratamento de dados ou funcionamento na AWS; esses itens exigem homologação operacional.
