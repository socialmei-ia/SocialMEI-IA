# Live Environment Inventory

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
