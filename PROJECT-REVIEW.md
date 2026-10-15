# Revisão do projeto

Este documento registra a revisão histórica de 10/10/2026. O mapa atual está na [revisão de preparação](FUTURE-READINESS-REVIEW.md); a [revisão de 12/10](docs/REVISAO-PROJETO-2026-10-12.md) também preserva sua coleta datada. Não use as limitações históricas abaixo para concluir que a API de gestão ou as migrations ainda não existem.

Revisão em **10/10/2026**, sobre `socialmei-ia/SocialMEI-IA`, base `aeaad28207d65537071e63f73dbf83143fcff22e`. O GitHub confirmou que o endereço antigo `socialmei-ia/socialmei` resolve para este mesmo repositório. Foram inventariados os 41 arquivos rastreados antes das alterações, incluindo código, configurações, exports, docs e assets.

## Estado atual

CRM experimental com gestão local, experiência pública, atendimento demonstrativo e leitor de mensagens n8n. O backend Python é auxiliar; não oferece CRUD/autenticação do CRM. Schema e workflow PostgreSQL tratam histórico de atendimento. Compose descreve uma VPS, mas não comprova disponibilidade dos serviços.

O repositório publicava duas cópias idênticas da **V3.14**. Nesta sessão o arquivo aprovado era `socialmei-app.html`, posterior à V3.27 com as correções de Inbox e Automações. Foi adotado como fonte oficial, preservando comportamento e identidade aprovados.

SHA-256 do arquivo aprovado antes da extração: `b3496d23d51239f037610840d7d86be46b151ba81e37db11557d954357dbf495`. As duas cópias antigas tinham SHA-256 `1a2ec2f8bf51d06acae3ff67fd5719b03cc5b4f74d1fa989b81e3079138808a9`. Seu histórico permanece no Git; não foi criada uma pasta de versões numeradas.

## O que está bom

- HTML/CSS/JavaScript puro, sem build obrigatório ou dependência de framework.
- Fluxos locais de gestão, exportação/importação, temas e movimento reduzido na versão aprovada.
- Validação de backup e aviso de falha de armazenamento.
- SQL parametrizado no workflow de persistência; schema funcional separado das tabelas n8n.
- Roles distintas e PostgreSQL sem porta pública no Compose.
- Guias de acesso individual e fluxo branch/PR já presentes.

## Divergências encontradas e tratamento

| Evidência                | Problema                                                                          | Mudança                                                                                                          |
| ------------------------ | --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Frontend V3.14 duplicado | Fonte aprovada mais recente estava fora do Git                                    | Fonte oficial única em `frontend/socialmei-app.html`; entradas antigas preservadas como redirecionamentos.       |
| `compose.yaml`           | Bloco WAHA com indentação inválida                                                | YAML corrigido e validado com Compose.                                                                           |
| WAHA no base e override  | Base desativava API key/senhas e publicava 3000, enquanto docs afirmavam proteção | Uma definição autenticada com bind localhost; configurações completas no base.                                   |
| README                   | Não cobria Assistente/Automações atuais e descrevia API apenas interna            | Atualizados módulos/limites e exposição Caddy; nenhuma promessa de IA conectada.                                 |
| Leitura remota           | Docs falavam de consulta fixa a cada 4 s                                          | Documentado recuo 4/8/15/30 s, pausas e `since` desligado.                                                       |
| JSONs Instagram          | Authorization literal, dados fixados e referências da instância                   | Sanitizados; credencial HTTP Header Auth deve ser vinculada no n8n. Validade dos valores antigos não verificada. |
| `backup.sh`              | Diretório e volume `socialmei_n8n_data` fixos; override ausente do backup         | Diretório configurável, descoberta de montagem, arquivo privado completo de configuração e tratamento de falhas. |
| Mike DevHub              | Fontes minificadas e comandos para copiar HTML entre duas versões                 | CSS/JS legíveis, comandos atualizados e exportação standalone preservada.                                        |
| GitHub Actions           | Só JSON/assets/cópias, sem regressão do app                                       | Testes de contratos, backend, backup, formatação e job de navegador; não foi inventado deploy automático.        |
| SEO do aprovado          | Canonical/OG ainda apontavam para domínio placeholder                             | Endereço adotado no repositório e banner existente. Revalidar se houver mudança de host.                         |

## Mapa de arquivos antes da alteração

As categorias se aplicam ao estado observado, antes da reorganização.

| Arquivo/grupo                                                          | Classificação                                   | Decisão                                                                                                        |
| ---------------------------------------------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `index.html`                                                           | DUPLICADO / LEGADO / CONFIGURAÇÃO de publicação | Retirar conteúdo V3.14, manter entrada para Pages com query/hash.                                              |
| `frontend/socialmei-dashboard.html`                                    | DUPLICADO / LEGADO                              | Manter URL de compatibilidade; não manter segunda aplicação.                                                   |
| `tools/mike-devhub.html`                                               | ATUAL MAS PRECISA DE REVISÃO                    | Preservar toolbox, extrair CSS/JS e atualizar comandos.                                                        |
| `python-service/app.py`                                                | ATUAL MAS PRECISA DE REVISÃO                    | Nomes internos em inglês, contrato `/processar` e JSON preservados.                                            |
| `python-service/Dockerfile`, `requirements.txt`                        | ATUAL E NECESSÁRIO / CONFIGURAÇÃO               | Mantidos; versões não fixadas registradas como dívida.                                                         |
| `compose.yaml`, `compose.override.yaml`, `Caddyfile`                   | ATUAL MAS PRECISA DE REVISÃO / CONFIGURAÇÃO     | Consolidar serviços, corrigir WAHA e permitir configuração dos hosts.                                          |
| `.env.example`                                                         | CONFIGURAÇÃO                                    | Placeholders mantidos, novas variáveis públicas documentadas.                                                  |
| `.gitignore`                                                           | CONFIGURAÇÃO                                    | Acrescentar dependências, caches, evidências e credenciais locais.                                             |
| `.nojekyll`                                                            | CONFIGURAÇÃO                                    | Mantido para publicação estática.                                                                              |
| `backup.sh`                                                            | ATUAL MAS PRECISA DE REVISÃO                    | Corrigir alvos reais e falhas; testar com Docker falso.                                                        |
| `database/bootstrap.sql`, `schema.sql`, `permissions.sql`              | ATUAL E NECESSÁRIO / CONFIGURAÇÃO               | Mantidos sem alteração de schema; documentar ordem/owner/banco fixo.                                           |
| `n8n-workflows/producao/01-caixa-unificada-api-postgresql.json`        | ATUAL MAS PRECISA DE REVISÃO                    | Preservar SQL/grafo/contrato; normalização com variáveis em inglês.                                            |
| `n8n-workflows/hello-world.json`, `teste-python.json`                  | ARQUIVO DE TESTE                                | Mover para `examples/`, exports inativos.                                                                      |
| `n8n-workflows/integracao-n8n-insta.json`                              | PROTÓTIPO / EXPERIMENTAL                        | Mover para `experimental/instagram-agent.json`, sanitizar.                                                     |
| `n8n-workflows/error.json`                                             | PROTÓTIPO / possível LEGADO                     | Grafo de challenge distinto; preservar em `experimental/instagram-webhook-challenge.json` para revisão manual. |
| `n8n-workflows/my-workflow.json`                                       | PROTÓTIPO / possível LEGADO                     | HTTP agendado sem URL: preservar como `scheduled-request-draft.json`; não apagar às cegas.                     |
| `README.md`, `CONTRIBUTING.md`, `SECURITY.md`                          | DOCUMENTAÇÃO                                    | Atualizar conforme código e novos testes.                                                                      |
| `docs/ARQUITETURA.md`, `ONBOARDING.md`, `DOCKER.md`                    | DOCUMENTAÇÃO desatualizada                      | Guias menores com links para documentação canônica.                                                            |
| `docs/ACESSOS.md`, `BANCO-DE-DADOS.md`, `MIKE-DEVHUB.md`               | DOCUMENTAÇÃO                                    | Preservar procedimentos úteis e explicitar limites/verificação.                                                |
| `docs/assets/socialmei-banner.png`, `.svg`, `socialmei-logo.png`       | ASSET                                           | Mantidos: representações distintas e informação visual única.                                                  |
| `docs/assets/socialmei-dashboard.png`, `socialmei-caixa-unificada.png` | ASSET / captura LEGADA                          | Preservar para referência histórica; não apresentar como screenshot da fonte atual.                            |
| `.github/workflows/repository-checks.yml`                              | CONFIGURAÇÃO / ATUAL MAS PRECISA DE REVISÃO     | Ampliar validação, retirar exigência de duplicar HTML.                                                         |
| `.github/ISSUE_TEMPLATE/bug.yml`, `feature.yml`, `config.yml`          | CONFIGURAÇÃO / ATUAL E NECESSÁRIO               | Mantidos; não há ganho em reescrever formulários funcionais.                                                   |
| `.github/PULL_REQUEST_TEMPLATE.md`                                     | DOCUMENTAÇÃO / CONFIGURAÇÃO                     | Atualizar checklist da fonte e testes.                                                                         |

Não havia arquivos rastreados de backup, `.env`, `.pem`, dumps ou HTMLs `final-final2`. Não foram identificados assets idênticos pelos hashes do inventário. Candidatos incertos foram mantidos; não há descarte de informação única para reduzir contagem de arquivos.

## Arquivos atuais e reorganização

- Fonte oficial: `frontend/socialmei-app.html`, `config.js`, `scripts/`, `styles/`, `assets/`.
- Entradas compatíveis: `index.html`, `frontend/socialmei-dashboard.html`.
- Infraestrutura: Compose/Caddy/API/SQL e backup, com nomes de containers/volumes preservados.
- Automação: candidato PostgreSQL no caminho original, exemplos separados de experimentos.
- Docs canônicas: README, ARCHITECTURE, DEVELOPMENT, DEPLOYMENT, ROADMAP, PROJECT-REVIEW e CHANGELOG. Guias de acesso/banco/toolbox permanecem em `docs/`.
- Testes de manutenção em `tests/` e `python-service/test_app.py`.

## Refatoração e limites

Separados 22 blocos executáveis em scripts com nomes por responsabilidade, mais configuração pública. Os scripts continuam clássicos e na ordem original. A comparação AST confirmou código executável idêntico para os 22 módulos, desconsiderando comentários/formatação e a configuração literal movida para arquivo próprio.

O CSS continua em um arquivo legível para manter a cascata. Foi consolidado somente um par de media queries adjacentes idênticas; 13.010 declarações mantiveram ordem, contexto e valores (com URLs dos assets extraídos). Ícone/fonte preservaram seus bytes. Remoção ampla de overrides depende de regressão visual executável.

As novas separações reduzem o custo de localizar código, mas não transformam os globais em módulos isolados. Não foram renomeados contratos persistidos nem eliminadas funcionalidades. Após a liberação do ambiente, a regressão no Chromium passou em 88 estados e oito fluxos; os contratos HTTP da API auxiliar também passaram. A branch foi publicada no [PR #6](https://github.com/socialmei-ia/SocialMEI-IA/pull/6). Veja [docs/QA.md](docs/QA.md).

## Dívida técnica e riscos

- `app.js`, `experience.js`, `business-views.js` e CSS ainda grandes; handlers/globais acoplados.
- CSS original: 4.437 regras, 118 media queries, 834 seletores que aparecem mais de uma vez e 203 `!important`. Repetição em tema/responsividade pode ser legítima; não classificada automaticamente como regra morta.
- CRUD/autenticação/multiempresa ainda sem backend; login demonstrativo não garante segurança.
- Leitura n8n com CORS amplo, sem identidade estável de conversa/cliente e sem idempotência de reenvio na inserção.
- Regras e Assistente locais; não prometem execução/IA remota.
- Requisitos Python/imagens flutuantes; export não prova compatibilidade de versão n8n instalada.
- SQL inicial sem migrations incrementais. `permissions.sql` exige owner/banco corretos.
- Backup não cobre todas as sessões/volumes nem oferece snapshot conjunto atômico.
- Capturas antigas foram preservadas e rotuladas; falta documentação visual nova validada.
- Cabeçalhos antigos, caso fossem válidos, exigem revogação: não reescrever histórico sem plano da equipe.

## Próxima etapa e decisões recomendadas

1. Exigir aprovação do CI e revisão visual da fonte extraída antes do merge.
2. Reproduzir entrada/leitura n8n/PostgreSQL com credenciais de teste e dados fictícios.
3. Definir identidade, autorização e dados compartilhados antes de conectar o composer/IA.
4. Revisar/adaptar WAHA na VPS preservando project name/volumes; testar restore separado.
5. Dividir grandes controladores por ciclo de vida e consolidar CSS gradualmente, com regressão.

O planejamento detalhado está em [ROADMAP.md](ROADMAP.md). Esta revisão prepara a base para a próxima fase, sem ativar workflows, executar SQL ou aplicar mudanças na VPS.
