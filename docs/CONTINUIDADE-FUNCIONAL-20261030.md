# SocialMEI.IA — continuidade funcional verificada (30/10/2026)

Este documento rastreia **código publicado no GitHub**, **execução confirmada na AWS em relatórios anteriores** e **pendências não homologadas**. Não substitui `C:\Users\richa\socialmei-ops-20261029\CONTINUIDADE-SOCIALMEI-20261030.md`, que pode conter alterações locais ainda não enviadas ao remoto.

## Regra de entrega

Uma tela ou endpoint existente não é prova de funcionamento. Classificar separadamente: código preparado; testes aprovados; versão instalada; recebimento real observado; envio/publicação reais homologados. Não inserir produtos, preços, métricas, números, resultados de sentimento ou confirmações sintéticos como se fossem dados reais.

## Sequência GitHub a preservar

1. **#159** (`feat/whatsapp-contact-refresh-20261030`) — base de recebimento e identificação periódica do contato; 552 backend, 358 frontend, 261 operacionais reportados no CI anterior. Melhoria da análise da Caixa implementada e ainda não publicada. Não fazer merge sem verificar a cadeia de PRs #156–#159.
2. **#160** (`feat/integrations-honest-readiness-20261030` → #159) — status de recebimento WhatsApp verificado pelo vínculo privado + banco do workspace 1, front-end com estado honesto, testes unitários e V22. Não comprova sessão WAHA viva nem habilita envio.
3. **#161** (`feat/recovery-link-and-worker-readiness-20261030` → #160) — link HTTPS no fragmento, token removido do histórico, código manual mantido, testes de TLS e browser; configuração SMTP/worker permanece pendente.
4. **#162** (`feat/whatsapp-catalog-honest-empty-20261030` → #161) — mensagens de catálogo sem produtos reais não inventam estoque, preços ou serviços; testes sintéticos.

5. **#163** (`feat/instagram-owner-token-renewal-20261030` → #162) — conexão Instagram passa a informar disponibilidade de renovação do token somente com runtime OAuth e flag explícita; responsáveis podem renovar pelo diálogo sem enviar Direct ou publicar conteúdo. Inclui testes sintéticos de permissão, método POST e falha do provedor.

6. **#165** (`feat/n8n-provider-sentiment-20261030` → #163) — reforço do template n8n **existente** de oito nós (`experimental/provider-sentiment-worker.json`) com validação estrita de claims e classificação, preservando a trava `ENABLED=false` e o agente Groq; nenhum segundo workflow foi criado. API recusa resultado de lease expirado. Documentação de ativação privada em `docs/N8N-PROVIDER-SENTIMENT.md`; integração real **ainda não homologada**.

As branches estão empilhadas, portanto o mesmo arquivo deve ser alterado preferencialmente no topo da cadeia e os merges devem respeitar a ordem. **Não confundir commits em branches Draft com deploy em produção.** Conferir testes CI de cada HEAD; a PR de integração #164 passou no CI para o HEAD eba0ff5859850ea27f17912dc1ca33bebdb2cc1b; o acréscimo #165 ainda requer CI próprio. Os novos testes unitários não foram executados por falta de runner local/CI nesta sessão. A sintaxe dos scripts JavaScript de entrada, integração WAHA/Meta e testes novos foi verificada em um parser JavaScript sem execução.

## Verificações isoladas desta continuação

- Os scripts `frontend/scripts/v22-instagram.js`, `frontend/scripts/v22-whatsapp-readiness.js`, `frontend/scripts/entrada.js` e os três testes JavaScript novos foram analisados pelo parser V8: sintaxe válida.
- O método real de renovação do Instagram, extraído da branch via GitHub, passou **5 cenários sintéticos em V8**: responsável autorizado; flag desligada; viewer; conta desconectada; erro do provedor. Somente o cenário permitido acionou o POST.
- O trecho real do link de recuperação passou **3 cenários sintéticos em V8**: token válido, token inválido e demonstração local. O fragmento foi limpo e apenas o modo remoto preencheu o código.
- O controlador real de readiness WAHA passou **3 cenários sintéticos em V8**: canal registrado; não configurado; resposta de API inválida com envio habilitado. Não acionou envios.
- **Limite:** estas verificações executaram funções/trechos com mocks sem servidor/browser completo. Testes Python, Node/Playwright completos e CI ainda **não** foram executados/confirmados neste ambiente; não são evidência de funcionamento AWS.

## Estado operacional conhecido e ações prioritárias

| Área                     | Evidência anterior                                                                                         | Estado presente deste registro                                         | Próxima ação verificável                                                                                                                                                                             |
| ------------------------ | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API, gateway, PostgreSQL | AWS relatada saudável no SHA `5a23c74459391fb2d9c83170725826664cc6dc19`; 33 migrations                     | Sem nova confirmação de produção                                       | Conferir digest/SHA real, saúde, rede, backup e segurança antes de qualquer mudança                                                                                                                  |
| WhatsApp WAHA            | Sessão WEBJS WORKING e mensagens reais recebidas no workspace 1; PR #159 cita oito mensagens               | Recebimento observado, envios desabilitados                            | Homologar revisão da Caixa e os estados da #160; preservar vínculo HMAC                                                                                                                              |
| Contatos WhatsApp        | PR #159 relata três conversas identificadas, sem envios                                                    | Helper já aplicado na AWS segundo a PR; nenhuma alteração nesta rodada | Confirmar nomes no dashboard e job único                                                                                                                                                             |
| Bot WAHA/n8n             | Planner/claim/handoff existem no código; bot desligado; workflows legados preservados                      | **Não homologado**                                                     | Obter acesso administrativo privado ao n8n; comparar versão ativa e rascunho; escolher exatamente um respondedor, garantir idempotência/pausa humana; testar apenas com telefone de teste autorizado |
| Catálogo workspace 1     | Zero produtos na última consulta                                                                           | Sem dados para resposta comercial real                                 | Cadastrar produtos/serviços reais com preços e estoque no app; exercitar a consulta do bot antes de habilitar envios                                                                                 |
| Instagram Meta           | Conta de teste teve token aceito em leitura; OAuth preparado                                               | Direct recebido/enviado e publicações **não confirmados**              | Inspecionar inscrições/permissões efetivas do app e workflows; homologar Direct por teste, feed/stories/reels com conteúdo aprovado e um único responsável pelas respostas                           |
| n8n                      | Workflow Direct ativo em versão publicada diferente da versão rascunho; acesso administrativo indisponível | Não reconfigurado                                                      | Obter API administrativa privada ou acesso de operador; exportar versão publicada, revisar conexões e credenciais sem registrá-las no Git                                                            |
| Análises/Sentimento      | Persistência e exibição de sentimento preparadas no código; integração remota desligada                    | Análise real não homologada; melhoria da Caixa na #159                 | Revisar esquema de integração com n8n, ativar somente com chave privada e allowlist workspace 1, verificar resultado no banco e na interface                                                         |
| Recuperação de conta     | Migration 024/026, SMTP e worker explícito existem no código; SMTP desabilitado na AWS                     | Link novo apenas em #161, não publicado                                | Configurar SMTP privado; instalar worker controlado; testar pedido, e-mail real de teste, expiração, uso único, revogação e login                                                                    |
| UX e regressão           | Auditoria visual do computador Windows ficou bloqueada; houve testes sintéticos                            | Sem homologação visual nova                                            | Revisar desktop/celular na AWS após release e conferir estados vazios, formulários, isolamentos e erros                                                                                              |

## Procedimentos de segurança e recuperação

- Não aplicar `docker compose down`, remover volumes, restaurar dump integral por rotina ou ativar simultaneamente webhooks/respondedores legados.
- Antes de release, verificar backup recente e restaurável com hashes e índice pg_restore, configurações efetivas, imagens anteriores, comparação de rede/mount/Compose e rollback direcionado por serviço.
- Preservar o agendador/registro WAHA e não emitir respostas automáticas a clientes ou publicar conteúdo sem conteúdo e destinatário de teste sob controle.
- Credenciais Meta, n8n, SMTP, HMAC e tokens ficam somente no cofre/ambiente privado. Nenhum código deve imprimir segredos.
- Se a homologação visual ou API n8n estiver indisponível, continuar em módulos independentes, sem declarar integração ativa.

## Retomada imediata sugerida

1. Executar CI e `node --test tests/recovery-link.test.cjs tests/v22-whatsapp-readiness.test.cjs` e `python -m unittest test_integration_readiness test_recovery_link test_whatsapp_empty_catalog` em dependências isoladas; em seguida o CI completo.
2. Validar versão ativa n8n e contrato único do WAHA; homologar resposta somente ao telefone de teste e menu consultando produto real do workspace 1.
3. Publicar a melhoria já implementada das análises da Caixa (PR #159), após release isolada, backup e smoke test.
4. Preparar e verificar Meta Direct (inbound, persistência, outbound seguro, handoff) e publicações reais aprovadas (feed/stories/reels).
5. Implantar SMTP e worker de recuperação; confirmar entrega e reset com teste controlado.
6. Registrar SHA, CI, versão publicada, logs redigidos e rollback de cada etapa neste documento.

**Esta atualização só representa commits/preparações nas branches. Não foi executado merge, deploy ou mudança no n8n, WAHA, Meta, PostgreSQL ou SMTP.**
