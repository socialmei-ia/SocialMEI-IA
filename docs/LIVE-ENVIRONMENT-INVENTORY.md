# Live Environment Inventory

Atualização de evidências em 13/10/2026: ver seção de acompanhamento ao final. O inventário permanece **PARTIAL**; os bloqueios descritos na coleta inicial são históricos e foram parcialmente fechados.

Rodada de estabilização A01/A02, 12/10/2026 (America/Fortaleza). Coleta inicial: **PARTIAL**; inventário interno da VPS: **BLOCKED**. Nenhuma ação de infraestrutura, banco, n8n, WAHA ou deploy foi executada.

## Baseline e fonte

- Auditoria e `main` conferido na API do GitHub: `65be4880a41bec5903b7c3c896ff14da74c4f1d7`.
- Checkout inicial: `feat/visual-contas`, `b19c447a04d5de32d11c426b7251b3d20f6f2391`; árvore idêntica ao SHA auditado e nenhum arquivo não commitado.
- Branch desta rodada: `fix/audit-ui-regressions`, criada a partir do `main` auditado.
- Fontes: PROJECT-AUDIT.md, TEST-REPORT.md e NEXT-STEPS.md entregues na auditoria. As cópias atuais PROJECT-AUDIT(1).md, TEST-REPORT(1).md e NEXT-STEPS(1).md foram lidas; conteúdo consistente com a base original.
- Os testes locais e o CI anterior são evidência de código/teste, não evidência atual do runtime AWS.

Não foi disponibilizada uma sessão SSH, chave privada local ou conexão autenticada com a instância n8n/WAHA. Nenhum segredo foi solicitado, impresso ou registrado. Sem esse acesso, esta rodada segue somente com as correções locais de baixo risco autorizadas.

Consulta externa sanitizada em 12/10/2026 às 21:03 (America/Fortaleza): HEAD em `/api/v1/clientes` respondeu HTTP 401 com esquema Basic. A tentativa HEAD da raiz expirou; não comprova indisponibilidade do site. Essas requisições não leram corpos ou registros e não fecham o inventário interno.

## Runtime Docker e serviços

| Superfície               | Git / contexto conhecido                                                                        | Runtime atual                                                         |
| ------------------------ | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| VPS                      | IP informado 54.94.213.7; paths históricos /home/ubuntu/socialmei e /home/ubuntu/socialmei-team | BLOCKED: SHA dos checkouts e arquivos locais não consultados          |
| Docker / Compose         | compose.yaml (pilha antiga), compose.team.yaml (equipe), compose.dev.yaml (local)               | BLOCKED: versões, containers, projetos, status, imagens e digests     |
| Healthchecks             | Banco/API definidos no Git; gateway sem healthcheck próprio no Compose team versionado          | BLOCKED: configuração e estado efetivos, inclusive overlays           |
| Mounts / volumes / redes | DB team separado; sessões/mídia WAHA previstos; rede socialmei_team_web                         | BLOCKED: mounts, volumes órfãos e redes efetivamente instalados       |
| n8n                      | Imagem latest no Git                                                                            | BLOCKED: versão, workflows vivos, ativações, execuções e erros        |
| WAHA                     | Imagem latest; engine/config de estrutura previstos no Compose                                  | BLOCKED: versão, engine/mounts efetivos e estado sanitizado da sessão |
| Caddy / API              | Gateway e proxy distintos; proteção Basic e auth opt-in versionadas                             | BLOCKED: versões, logs, arquivos privados e flags efetivos            |

Tags do Git não foram registradas como versões instaladas. A confirmação anterior de criação da sessão WAHA default não comprova o estado atual; o chip dedicado continua uma dependência humana. Nenhuma sessão foi pareada, reiniciada ou usada para envio.

## PostgreSQL

| Item                  | Referência versionada                                                      | Coleta atual                                           |
| --------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------ |
| Banco team            | socialmei_team; migrations 001–010                                         | BLOCKED: versões realmente instaladas                  |
| Banco legado/n8n      | Nome depende do ambiente antigo; .env.example exemplifica n8n              | BLOCKED: banco efetivo da instância                    |
| Schema                | Migrations declaram 26 tabelas funcionais; executor cria schema_migrations | BLOCKED: tabelas, colunas, constraints e índices vivos |
| Acessos SQL           | Roles/grants reais não inferidos dos nomes ou dos exemplos                 | BLOCKED: roles e grants                                |
| Dados agregados / A03 | Consultar somente contagens de preços/custos incompatíveis em READ ONLY    | BLOCKED: nenhuma consulta ao banco vivo                |

Não foram exibidos nomes de clientes, e-mails, conteúdo de mensagens, hashes ou credenciais. Nenhuma migration ou consulta de escrita foi executada. O CI anterior com PostgreSQL real permanece evidência separada.

## Workflows n8n

Nenhum workflow vivo foi enumerado nesta coleta. IDs, atividade, triggers efetivos, última execução, agregados de sucesso/erro e correspondência com o Git continuam **BLOCKED**. A tabela abaixo classifica somente os sete exports versionados, sem atribuir estado da instância.

| Arquivo Git                                     | Classificação do export                     | Trigger previsto             | Correspondência / estado vivo |
| ----------------------------------------------- | ------------------------------------------- | ---------------------------- | ----------------------------- |
| equipe/01-conferir-conexao.json                 | ATUAL, conferência técnica                  | Manual → GET de leitura      | BLOCKED                       |
| producao/01-caixa-unificada-api-postgresql.json | LEGADO; P0 condicional antes de dados reais | POST/GET webhook             | BLOCKED                       |
| examples/hello-world.json                       | TESTE                                       | Webhook GET                  | BLOCKED                       |
| examples/process-text.json                      | TESTE                                       | Manual → API Python          | BLOCKED                       |
| experimental/instagram-agent.json               | EXPERIMENTAL / INCOMPLETO                   | Webhook POST                 | BLOCKED                       |
| experimental/instagram-webhook-challenge.json   | EXPERIMENTAL / INCOMPLETO                   | Webhook GET; cadeia separada | BLOCKED                       |
| experimental/scheduled-request-draft.json       | INCOMPLETO / possível LEGADO                | Agendamento → HTTP sem URL   | BLOCKED                       |

Todos os exports são inativos no Git; isso não prova inatividade na VPS. Nenhum workflow foi renomeado, importado, ativado ou excluído. A12/A13 continuam bloqueadores antes de atendimento real, não descrição de um incidente confirmado.

## Backups

| Verificação                           | Evidência disponível                                                    | Estado atual                                          |
| ------------------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------- |
| Existência, datas, tamanho e destinos | Usuário confirmou backups/cópia inicial em etapa anterior               | BLOCKED: não reinspecionados                          |
| Cron diário                           | Implementação versionada e instalação relatada anteriormente            | BLOCKED: crontab e últimas execuções não consultados  |
| Cobertura team                        | Código cobre dump completo do banco team e configuração privada         | VALIDADO em código; conteúdo das cópias vivas BLOCKED |
| Cobertura antiga / WAHA               | Script antigo não cobre todos os volumes de sessões/mídia/Caddy/pgAdmin | VALIDADO em código; cobertura efetiva BLOCKED         |
| Cópia externa recorrente / retenção   | Não comprovada nesta rodada                                             | BLOCKED / NEEDS INFRA DECISION                        |

Nenhum backup foi criado ou restaurado apenas para teste. Não houve leitura de dumps ou conteúdo de arquivos privados.

## Git × AWS e próxima coleta

Não há diferença de código entre o `main` atual e o SHA auditado. **Não é possível concluir igualdade ou divergência Git × AWS sem runtime autenticado.** Versão de imagem, migrations instaladas e flags de contas não são presumidas a partir do Compose.

Para completar a Etapa 0, executar a coleta sanitizada somente leitura do TEST-REPORT pelo acesso privado do responsável e complementar com inventário de workflows/execuções compatível com a versão n8n encontrada. Somente metadados necessários; transação READ ONLY; sem exportar credenciais, nodes completos ou payloads. Qualquer item não obtido permanece BLOCKED.

As futuras etapas de banco/n8n/infra/deploy aguardam esse inventário e autorização própria. O bloqueio não impede A01/A02 locais, conforme a regra explícita desta rodada.

## Acompanhamento — 13/10/2026, America/Fortaleza

### Fonte e limites da coleta

Evidências fornecidas pelo responsável após execução no servidor via SSH: Texto colado(8).txt (coleta às 00:46:42, -03:00), Texto colado(9).txt (inventário n8n posterior) e saída sanitizada de WAHA/cron recebida às 00:51. O auditor não possui sessão SSH própria. As consultas de banco foram executadas em transações `READ ONLY`, com metadados selecionados; não houve leitura de payloads, credenciais ou dados pessoais.

**PARTIAL** significa que esta coleta fecha os itens explicitados abaixo. Não comprova todos os requisitos operacionais nem substitui os itens pendentes. Não houve nova auditoria geral.

O PR #30 foi aprovado explicitamente e integrado em `main`: `9e943a92624f1cdefc50bfc2322b0f7bfc2a0af3`. O responsável executou a atualização somente do gateway, precedida de backup, e confirmou visualmente o site. Banco/API não foram reconstruídos; nenhuma migration foi aplicada nessa atualização. O texto de encerramento da rodada inicial acima descreve o estado anterior a essa autorização.

### Git × AWS e Docker efetivo

- Checkout team: SHA `9e943a92624f1cdefc50bfc2322b0f7bfc2a0af3`; `git status --short` sem saída. Igual ao merge autorizado do PR #30, não ao snapshot inicial da auditoria.
- Docker 29.8.2 (build 7fc2dff); Docker Compose v5.5.1; nove containers em execução na coleta. O container de migrations estava encerrado com código 0, criado antes desta atualização.
- Gateway/API/PostgreSQL team usam somente `/home/ubuntu/socialmei-team/compose.team.yaml` nos labels efetivos.
- Caddy público usa o Compose legado, `compose.override.yaml` e `deploy/team/private/proxy.override.yaml`; compartilha `socialmei_default` e `socialmei_team_web`. Os arquivos privados completos não foram lidos.
- WAHA, pgAdmin e Python legado registram Compose + override; n8n e PostgreSQL legado registram somente `compose.yaml`. Portanto os overlays não devem ser presumidos idênticos entre containers.
- API team, PostgreSQL team/legado e Python legado: `healthy`. Gateway, Caddy, WAHA, pgAdmin e n8n: sem healthcheck configurado. Container em execução não significa saúde funcional certificada.

| Container          | Imagem declarada no runtime    | Campo Image retornado pelo Docker                                       |
| ------------------ | ------------------------------ | ----------------------------------------------------------------------- |
| team-gateway       | socialmei-team-team-gateway    | sha256:aba95012eb1d2b2d8c1edccf75f2840610c8cc7a193504496c24ec8ac99e7b9d |
| team-api           | socialmei-team-team-api        | sha256:905ed8ac12b43595ebad7b16ab2d14c4e021b9a58db73f0a2166645ec9c064a5 |
| team-postgres      | postgres:16-alpine             | sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea |
| socialmei-caddy    | caddy:2-alpine                 | sha256:de23def33b17fb5d1290b0f6c2add1d70780e52341896c00a4c8a2a2fe9d355e |
| socialmei-waha     | devlikeapro/waha:latest        | sha256:280bdc8f860267a2488a45d00ec88529646f7468c0bf0283c595d6efdd1b5e3b |
| socialmei-pgadmin  | dpage/pgadmin4:latest          | sha256:c332c5f6dfba995d9ebc4af261d93506d6876085d712eaaa3defc8dd1a3f26de |
| socialmei-python   | socialmei-python-api           | sha256:ed33f3d59715ec02e0cb195c76b0053aef1ce9567a93a6a69ac3cdce87d16797 |
| socialmei-n8n      | docker.n8n.io/n8nio/n8n:latest | sha256:9f693fd5565539efd5e75ad168526c8041a6af516d9e50bc4d9cb1c9c5031523 |
| socialmei-postgres | postgres:16-alpine             | sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea |

Os valores acima são o campo `Image` de `docker inspect` dos containers; não foram substituídos por tags do Git. `RepoDigests`, versões de pacote de PostgreSQL/Caddy/pgAdmin/API e comparação completa das imagens construídas com os SHAs de origem ainda não foram coletados. O backend team permaneceu na imagem anterior ao PR #30; o PR contém somente UI/testes/docs.

Mounts/rede confirmados: volume team `socialmei-team_team_postgres_data` no banco e rede interna `socialmei-team_database`; API em `socialmei-team_api`/database; gateway em api/web com binds privados de Caddy/config. Volumes legados `socialmei_postgres_data`, `socialmei_n8n_data`, `socialmei_pgadmin_data`, `socialmei_caddy_data` e `socialmei_caddy_config`. Caddy público monta `deploy/team/private/public.Caddyfile`. WAHA monta somente `socialmei_waha_sessions` em `/app/.sessions`, na rede `socialmei_default`, com porta host `127.0.0.1:3000`. Enumeração de volumes/redes órfãos não realizada.

### Bancos, migrations e saúde

- Bancos identificados: `socialmei_team` e `n8n` (este último confirmado por `current_database()` no PostgreSQL legado).
- Todas as dez migrations 001–010 instaladas no banco team. 001–007 em 12/10 às 03:09 UTC; 008 às 04:12 UTC; 009 às 18:45 UTC; 010 às 22:42 UTC.
- 27 tabelas no schema `socialmei`, incluindo `schema_migrations`: 26 funcionais. Confirmadas tabelas de contas/sessões/credenciais/convites/auditoria, CRM e canais/conversas/mensagens/eventos.
- `doctor` reportou `healthy`, `shared_data: true`, workspace `team`. Conferência técnica de leitura: clientes 1, produtos 1, vendas visíveis 0, financeiro 1. Isso não comprova separadamente login e todos os recursos de canais.
- Não consultados: colunas/constraints/índices/grants/roles do schema team, validação de preços/custos atuais (A03), saúde específica das tabelas de auth/canais (A06). Sem leitura de e-mails, hashes ou registros individuais.

### n8n vivo

Versão efetiva: **2.40.5**. Banco `n8n`; 24 workflows, oito com `active=true`, três arquivados. As contagens de execução abaixo consideram últimos sete dias, excluindo execuções com `deletedAt` preenchido; são histórico retido, não todas as chamadas possíveis. Horários de última execução em UTC. Sem leitura de erros brutos, outputs ou payloads.

Classificação é triagem baseada em nome, tipos de nós e histórico. Correspondência por nome/tipos não prova igualdade integral com o export. `nodes` lido nesta consulta representa o documento salvo; sua equivalência com a versão publicada não foi verificada. O gerador de relatórios declara Chat Trigger no documento salvo, mas ainda possui webhooks registrados; isso exige comparar a versão publicada antes de concluir os triggers efetivos.

| ID               | Nome                                       | Ativo / arquivado | Trigger no documento salvo | Última execução UTC | Sucessos / erros / canceladas (7d) | Classificação / correspondência                                                      |
| ---------------- | ------------------------------------------ | ----------------- | -------------------------- | ------------------- | ---------------------------------- | ------------------------------------------------------------------------------------ |
| WWzhvmdPh9LrpuYy | 01 · Caixa Unificada API                   | sim / não         | Webhook                    | 2026-10-07 22:10:26 | 701 / 0 / 0                        | LEGADO; variante sem PostgreSQL, sem export exato identificado                       |
| BtvlHv4mt90tn70z | 01 · Caixa Unificada API — PostgreSQL      | sim / não         | Webhook                    | 2026-10-12 02:20:06 | 1343 / 1 / 0                       | LEGADO; candidato ao export producao/01-caixa-unificada-api-postgresql.json          |
| DDrphANXE8QdxoWy | 02 · Gerador de Relatórios                 | sim / não         | Chat Trigger               | 2026-10-13 02:12:34 | 2018 / 2 / 0                       | DESCONHECIDO; nenhum dos sete exports representa o documento salvo                   |
| NDNF5doo9pLtj6sb | 03 · Integração Instagram                  | sim / não         | Webhook                    | sem execução retida | 0 / 0 / 0                          | EXPERIMENTAL; candidato a experimental/instagram-agent.json                          |
| K8Z9SVLEsR0yKVPc | Analise de Semtimentos                     | não / não         | Chat Trigger               | 2026-10-09 00:25:53 | 13 / 24 / 0                        | EXPERIMENTAL; não versionado nos sete exports                                        |
| SAlmjUPuAjyMdLAn | Integração Whatsapp                        | não / não         | Webhook                    | sem execução retida | 0 / 0 / 0                          | EXPERIMENTAL; não versionado nos sete exports                                        |
| uPbpfBbSB3q1efO7 | My workflow                                | não / não         | Manual                     | sem execução retida | 0 / 0 / 0                          | DESCONHECIDO; difere do export agendado com nome original My workflow                |
| RnXngR3SvhSxaC32 | Resposta Orçamento                         | não / não         | Chat Trigger               | 2026-10-11 22:56:35 | 10 / 9 / 0                         | EXPERIMENTAL; versão a escolher com responsável                                      |
| e324ZPdcKLcHQAPF | Resposta Orçamento                         | não / não         | não identificado           | 2026-10-11 21:42:07 | 2 / 1 / 0                          | EXPERIMENTAL; nome duplicado, identidade deve usar ID                                |
| UJFfcnE7PC6oOBd7 | Resposta Orçamento copy                    | não / sim         | Chat Trigger               | 2026-10-11 22:55:22 | 2 / 5 / 0                          | EXPERIMENTAL; arquivado, não excluir                                                 |
| 8hSF0mABWNYJqWQB | Resposta Orçamento copy 2                  | não / não         | Chat Trigger               | 2026-10-12 17:03:33 | 8 / 15 / 0                         | EXPERIMENTAL; sem nó Google Sheets ou toolWorkflow no documento salvo                |
| vF3jcCJrElfoQTH6 | Revisar · Workflow Antigo                  | não / não         | Schedule Trigger           | 2026-10-06 16:46:55 | 0 / 1 / 0                          | LEGADO / INCOMPLETO; candidato a experimental/scheduled-request-draft.json           |
| es8Q46avtvZzK1EX | SocialMEI - Pedidos e relatório de estoque | não / não         | Manual                     | 2026-10-12 14:13:06 | 1 / 3 / 0                          | DESCONHECIDO; sem export correspondente                                              |
| EGXHkPjqt0Wiaxl4 | SocialMEI equipe — conferir conexão        | não / não         | Manual                     | 2026-10-12 16:00:50 | 1 / 0 / 0                          | ATUAL; candidato a equipe/01-conferir-conexao.json                                   |
| Sasq0PBhdzlHV7Ds | Teste · Caixa Unificada                    | não / não         | Manual                     | 2026-10-06 17:12:59 | 1 / 0 / 0                          | EXPERIMENTAL; sem export correspondente                                              |
| 6BczTaFNOl24jr4X | Teste · Hello World                        | sim / não         | Webhook                    | sem execução retida | 0 / 0 / 0                          | EXPERIMENTAL; candidato a examples/hello-world.json                                  |
| QDlfkKxesQEWfyLp | Teste · Python                             | não / não         | Manual                     | 2026-10-08 21:03:06 | 2 / 0 / 0                          | EXPERIMENTAL; candidato a examples/process-text.json                                 |
| KevuuJgU5iXC9SfV | Validar CPF e CNPJ com Python              | não / sim         | sem nós                    | sem execução retida | 0 / 0 / 0                          | INCOMPLETO; arquivado                                                                |
| M9BN1KgXN0cqxmXi | Validação de CPF e CNPJ com Python         | não / não         | Webhook                    | 2026-10-12 16:46:56 | 4 / 0 / 0                          | EXPERIMENTAL; sem export correspondente                                              |
| QAcfeKiXA6ZQQ4Mz | confirmar_pedido                           | sim / não         | Execute Workflow Trigger   | 2026-10-13 02:12:35 | 8 / 0 / 0                          | DESCONHECIDO; Google Sheets, função comercial não validada                           |
| AUpqr0ko77jQJ6DW | consultar_produtos                         | sim / não         | Execute Workflow Trigger   | 2026-10-13 02:09:00 | 14 / 2 / 0                         | DESCONHECIDO; Google Sheets, função comercial não validada                           |
| JVPPxXa0cQbE62C2 | error                                      | não / sim         | Webhook                    | sem execução retida | 0 / 0 / 0                          | EXPERIMENTAL / INCOMPLETO; candidato a experimental/instagram-webhook-challenge.json |
| LV2rsbXIb3eE0Pb3 | registrar_pedido                           | sim / não         | Execute Workflow Trigger   | 2026-10-13 02:09:10 | 10 / 0 / 0                         | DESCONHECIDO; Google Sheets, função comercial não validada                           |
| kUVSGWkh2m7wpj2x | whatsapp                                   | não / não         | Webhook                    | 2026-10-12 23:19:09 | 7 / 46 / 1                         | EXPERIMENTAL; nó WAHA presente, não comprova integração pronta                       |

A presença de workflows legados ativos torna a revisão A12/A13 operacionalmente relevante. **Não confirma incidente, ausência de autenticação no runtime ou uso com clientes reais.** Não chamar seus webhooks, desativar, renomear ou publicar como teste. Conferir primeiro versão ativa, acesso estrutural e identidade/idempotência, respeitando o responsável por cada fluxo.

### WAHA e backups

- WAHA **2026.9.2**, engine **WEBJS**, edição **CORE**. A sessão `default` estava em `SCAN_QR_CODE`: aguardando pareamento. Sem exibir QR, telefone, tokens ou configuração de sessão. Nenhum pareamento/envio/restart foi feito.
- O runtime WEBJS não deve ser confundido com GOWS previsto no Compose atual do Git; há configuração/versão histórica distinta a reconciliar antes de atualizar WAHA. Montagem de sessão preservada.
- Cron de usuário consultado com sucesso; um agendamento `backup_team` às **02:30 diariamente**, `cron.service` ativo. Isso confirma agenda/serviço, não conclusão de cada execução.
- Arquivos atuais encontrados em `/home/ubuntu/socialmei-backups`, incluindo `team-auto-20261013-004302-03aa73`: `equipe.dump` 100905 bytes; `configuracao.tar.gz` 2128 bytes; `conteudo.txt` 18040 bytes; `concluido.json` 403 bytes. A atualização já havia reportado índice conferido; nesta coleta listaram-se somente metadados, sem novo backup/restore.
- Retenção, cópia externa recorrente, integridade de todas as cópias, último sucesso automático e cobertura dos volumes WAHA/Caddy continuam não comprovados. Não confundir lista de arquivos com restauração validada.

### Lacunas restantes

1. Versão publicada dos workflows (`activeVersionId`) e equivalência segura com exports; autenticação estrutural dos webhooks legados e dependências reais entre fluxos. Não exportar credenciais nem payloads.
2. Causas dos erros de orçamento/WhatsApp: agregados comprovam falhas, não a causa. Escolher o workflow pelo ID antes de corrigir.
3. Metadados completos do banco team: colunas, constraints, índices, roles/grants e contagens monetárias incompatíveis somente leitura.
4. `RepoDigests`, configuração completa sanitizada de redes/volumes/healthchecks, checkout legado e diferenças estruturais dos overlays, sem revelar arquivos privados completos.
5. Último backup automático bem-sucedido, cobertura de volumes, retenção e cópia externa recorrente; nenhum restore em produção para fechar inventário.

Acompanhamento fecha parte dos bloqueios iniciais e mantém o restante como **BLOCKED/PARTIAL**. Nenhum workflow n8n, WAHA, conta, preço, dado de CRM ou configuração de infraestrutura foi modificado durante estas consultas.
