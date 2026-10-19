# Estrutura do SocialMEI.IA

Mapa de manutenção, não proposta de migração de framework. Comece pelo [mapa dos ambientes](ENVIRONMENTS.md), escolha o contexto e só então altere o módulo.

## Fontes oficiais e classificação

| Caminho                                                   | Classificação                 | Responsabilidade / decisão                                                                 |
| --------------------------------------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------ |
| `frontend/socialmei-app.html`                             | Atual                         | Única implementação principal de markup e ordem dos scripts                                |
| `index.html`, `frontend/socialmei-dashboard.html`         | Compatibilidade               | Redirecionamentos; não apagar nem manter uma segunda cópia do app                          |
| `frontend/admin.html`, `transferencia.html`               | Atual                         | Administração autorizada e transferência; têm scripts/contratos próprios                   |
| `frontend/scripts/`                                       | Atual                         | Scripts clássicos; stores de API, eventos, renderização e helpers por área                 |
| `frontend/styles/`                                        | Atual                         | CSS principal, conta e componentes interativos; cascata e tokens existentes                |
| `frontend/assets/`, `docs/assets/`                        | Asset                         | Marca, fonte licenciada e documentação; referência indireta não é prova de inutilidade     |
| `python-service/`                                         | Atual                         | FastAPI, modelos, validação, operações transacionais e testes Python                       |
| `database/migrations/001`–`011`                           | Atual / histórico imutável    | Estrutura incremental e integridade de CRM, contas e canais                                |
| `database/bootstrap.sql`, `schema.sql`, `permissions.sql` | Legado necessário             | Bootstrap de atendimento no banco n8n; não substitui migrations team                       |
| `database/team-readonly-access.sql`                       | Infra / preparação            | Acesso interno de consulta; não significa role provisionada na AWS                         |
| `n8n-workflows/equipe/`                                   | Infra / integração de leitura | Export operacional sem credenciais; não escreve no CRM                                     |
| `n8n-workflows/producao/`                                 | Legado                        | Atendimento com limitações P0; pasta não comprova homologação                              |
| `n8n-workflows/examples/`, `experimental/`                | Teste / protótipo             | Exercícios e grafos incompletos; manter inativos                                           |
| `compose*.yaml`, Dockerfiles, Caddyfiles                  | Infra                         | Alvos distintos; [não combinar ambientes](ENVIRONMENTS.md)                                 |
| `tools/`                                                  | Ferramenta / infra            | DevHub, desenvolvimento local, migrations, contas, diagnóstico e backup                    |
| `tests/`, `python-service/test_*.py`                      | Teste                         | Contratos, SQL isolado, navegador e operação; não dados reais                              |
| `.github/`                                                | Configuração                  | CI, templates, responsáveis e workflows manuais genéricos                                  |
| `docs/`, guias técnicos na raiz                           | Documentação                  | Guias atuais e revisões históricas datadas; evitar repetir a mesma regra em vários lugares |
| `.env*` privados, `deploy/team/private/`, dumps e backups | Privado / backup              | Fora do Git; não são arquivos obsoletos a apagar                                           |

Não foi identificado um arquivo versionado seguramente descartável nesta rodada. Não houve remoção ou movimentação. HTMLs numerados anexados em conversas não são entradas oficiais do repositório. `docs/ARQUITETURA.md` é um link de compatibilidade para `ARCHITECTURE.md`.

## Onde alterar cada funcionalidade

| Área                         | UI e comportamento                                                            | Estado / API / testes                                                                             |
| ---------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Home                         | `home.js`, `experience.js`, `personalization.js`; shell em `app.js`           | Estado atual dos stores; `visual-browser.cjs` e `visual-refinement-browser.cjs`                   |
| Caixa Unificada              | `inbox.js`, `record-editor.js`, `dialogs.js`                                  | `inbox-sync.js`, estado local; `inbox-sync.test.cjs`, navegador                                   |
| Clientes                     | `customers.js`, `business-views.js`, `record-editor.js`                       | `client-store.js`, `shared_data.py`, `client_import.py`; suites client/remote/transfer            |
| Produtos                     | `products.js`, `business-views.js`, `personalization.js`                      | `product-store.js`, `catalog_data.py`, `product_import.py`; suites catalog                        |
| Vendas                       | `sales.js`, `business-views.js`                                               | `sale-store.js`, `sales_data.py`, `sale_import.py`; suites sales/replay/estoque                   |
| Financeiro                   | `finance.js`, `business-views.js`                                             | `finance-store.js`, `finance_data.py`, `finance_import.py`; suites finance                        |
| Relatórios                   | `reports.js`, `report-ui.js`, `report-motion.js`, `report-data.js` e `app.js` | Estado de gestão e período; `reports-browser.cjs`                                                 |
| Assistente / Automações      | Seções nomeadas em `experience.js`                                            | Rascunhos/regras locais; sem executor externo confirmado; browser                                 |
| Configurações / tema         | `appearance.js`, `app.js`, `storage-and-themes.js`                            | Preferências e perfil; `settings-browser.cjs`, `themes.test.cjs`                                  |
| Onboarding adaptativo        | `business-profile.js`, `experience.js`; perfil em Configurações de `app.js`   | Preferências locais explícitas por usuário/workspace; suites business-profile/adaptive-onboarding |
| Login / convite              | `experience.js`, `auth-store.js`, `admin-accounts.js`                         | `account_auth.py`, `account_admin.py`; suites account/team                                        |
| Navegação / período          | `navigation.js`, renderers do shell                                           | `app.js`; `navigation.test.cjs` e browser                                                         |
| Transferência / backup local | `data-and-backup.js`, `workspace-transfer.js`, `transferencia.html`           | `workspace_transfer.py`; suites export/transfer                                                   |

Os caminhos JS da tabela são relativos a `frontend/scripts/`; os Python são relativos a `python-service/`. Buscar pelos nomes das seções antes de extrair um novo arquivo. `business-views.js`, `app.js` e `experience.js` ainda são grandes; não são componentes independentes.

## Fronteiras e inicialização do frontend

1. `storage-and-themes.js` e `motion.js` executam no head para inicializar apresentação.
2. Helpers de UI são declarados no corpo, na ordem do HTML. `config.js` precede auth/stores.
3. Os stores escolhem modo local/remoto, validam respostas e tratam transporte. `app.js` cria estado, liga eventos e inicializa; `experience.js` complementa telas/ciclo de vida.
4. Renderers e handlers consomem o estado. `record-editor.js` reúne edição/confirmação; os scripts da landing são complementos posteriores.

Não adicionar `async`, `defer` ou `type="module"` em lote: existem dependências globais e chamadas tardias. A limpeza extraiu seleção de período para `navigation.js` e composição de rascunhos do Assistente para funções nomeadas. Não mudou a ordem dos scripts.

As URLs dos stores vêm de `SOCIALMEI_CONFIG`; não colocar um `fetch` para AWS dentro de um renderer. Os quatro stores preservam seus contratos e recusam escrita remota quando a API falha; não gravam silenciosamente no navegador como substituto do banco. A repetição parcial de transporte permanece dívida conhecida, sem um client genérico que apague diferenças de replay/importação.

## Estado e persistência

| Categoria / chave ou família                                                                     | Fonte e finalidade                                                                                              |
| ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| Estado de UI em memória                                                                          | View, busca, seleção, filtros abertos e renderização; não é persistência do negócio                             |
| `socialmei-app-data-v2`                                                                          | Snapshot/gestão local e preferências; modo remoto preserva os snapshots antigos, não os torna fonte do servidor |
| `socialmei-inbox-local-v3`, `socialmei-inbox-drafts-v1`                                          | Conversas locais, anotações e composer; não comprovam sincronização de canal                                    |
| `socialmei-inbox-quick-v3`, `-sort-v3`, `-tag-v3`, `-details-v3`                                 | Filtros, ordenação e painel da Caixa                                                                            |
| `socialmei-client-origin-v1`, `-links-v1`, `-create-pending-v1`                                  | Identidade/vínculos/importação e recuperação de criação de clientes                                             |
| `socialmei-product-origin-v1`, `-links-v1`, `-create-pending-v1`                                 | Mesmo papel para catálogo                                                                                       |
| `socialmei-sale-origin-v1`, `-links-v1`, `-operation-pending-v1`                                 | Importação e replay de operações de vendas                                                                      |
| `socialmei-finance-origin-v1`, `-links-v1`, `-operation-pending-v1`                              | Importação e replay de operações financeiras                                                                    |
| `socialmei-auth-browser-scope`, `socialmei-account-state-*`                                      | Separação do estado local por identidade/negócio; não contêm o cookie HttpOnly de sessão                        |
| `socialmei-experience-profile-v1`                                                                | Perfil/preferências locais da experiência                                                                       |
| `socialmei-automation-drafts-v1`, `socialmei-automation-tests-v1`, `socialmei-ai-drafts-v1`      | Regras, testes simulados e rascunhos locais                                                                     |
| `socialmei-theme`, `socialmei-active-theme`, `socialmei-custom-themes`, `socialmei_public_theme` | Compatibilidade de tema, editor e tema público                                                                  |
| `socialmei-sidebar-compact-v2`, `socialmei-hide-money`                                           | Preferências de apresentação                                                                                    |
| sessionStorage: `socialmei-experience-screen`, `socialmei-current-view`                          | Retomada da tela na sessão do navegador                                                                         |
| PostgreSQL                                                                                       | Fonte dos módulos remotos; workspace é resolvido pela conta autenticada                                         |

Não renomear, apagar ou migrar essas chaves sem plano de compatibilidade. Backup JSON do navegador não substitui dump do banco. Os arrays de exemplos ficam fora da conta remota; não inserir fixtures como fallback de erro da API. As famílias acima mantêm o prefixo completo da primeira chave, por exemplo `socialmei-sale-links-v1`.

## Backend: configuração e contratos

`app.py` monta routers/middleware e preserva `/`, `/health` e `/processar`. `settings.py` concentra a leitura de ambiente para PostgreSQL, auth, CORS, workspace legado e token técnico. Não guarda cache nem imprime valores privados. `database.py` continua expondo `database_url` e `shared_data_enabled` por compatibilidade.

| Configuração                                            | Consumidor / comportamento                                                                       |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `DATABASE_URL` ou `POSTGRES_HOST/PORT/USER/PASSWORD/DB` | Conexão; URL explícita tem precedência; erro de ausência é sanitizado                            |
| `SOCIALMEI_SHARED_DATA_ENABLED`                         | Habilita gestão compartilhada; interpretação histórica preservada                                |
| `SOCIALMEI_WORKSPACE_SLUG/NAME`                         | Fallback sem auth; nunca substitui a identidade da sessão                                        |
| `SOCIALMEI_AUTH_ENABLED/ORIGIN`                         | Modo e origem HTTPS; flag inválida bloqueia acesso; validação permanece no módulo auth           |
| `SOCIALMEI_CORS_ORIGINS`                                | Lista explícita lida ao iniciar a aplicação; wildcard recusado; vazio no gateway de mesma origem |
| `SOCIALMEI_N8N_READ_TOKEN`                              | Somente leitura técnica do workspace team; não autentica um usuário                              |

Os modelos Pydantic e operações ficam perto do router de cada área. O middleware resolve a sessão; `auth_context.principal` leva a identidade ao trabalho executado na thread. `ensure_workspace` e consultas por workspace mantêm a fronteira de negócio. Não aceitar um workspace livre do corpo de uma requisição autenticada.

Os [55 endpoints](API-ENDPOINTS.md) e seus modelos são os contratos oficiais desta base. Erros usam `detail`, podendo ser uma string ou lista de validação FastAPI. Stores já tratam essas diferenças; padronizar todo o formato exige mudança de contrato própria. Endpoints de contas/admin não devolvem valores submetidos em erros de validação. 409 representa conflito/replay incompatível; não repetir escrita cegamente.

## Como adicionar uma feature

A próxima funcionalidade ainda não foi especificada. Não criar tela, rota, botão, tabela ou chave de armazenamento antes de definir entrada/saída, fonte, permissões, estados de erro e aceite com o responsável.

| Ponto de extensão           | Arquivo / contrato a preservar                                                                                                                                                                                                                                                                                         |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Entrada e carregamento      | `frontend/socialmei-app.html`: seção `.page-view`, ID estável e `data-view`; scripts clássicos na ordem existente, sem `async/defer` em lote. Preferir ampliar uma tela existente quando fizer sentido.                                                                                                                |
| Navegação e retomada        | `navigation.js:setView` seleciona a view, salva rascunho da Caixa, fecha popovers e emite `socialmei-view-change`. Usar o `setView` final, preservando wrappers de `business-views.js`, `app.js` e `experience.js`. Não apenas trocar classes no renderer.                                                             |
| Sidebar e topbar            | `business-views.js:renderNavigation/updateHeaderContext`; se for módulo operacional, conferir `MANAGEMENT_TABS`, `MANAGEMENT_VIEW_CONFIG` e mapeamento de IDs. `app.js:MANAGEMENT_AUXILIARY_VIEWS/syncBusinessIdentity` contextualiza as telas auxiliares.                                                             |
| Inicialização e atualização | `app.js:renderCurrentView` e wrappers existentes; inicializar eventos uma vez, atualizar o renderer com dados atuais. Consumir eventos de view/perfil/demo somente quando necessário; cancelar observers/requests/animações obsoletos.                                                                                 |
| Ajuda e componentes         | `context-help.js:topics` registra o contexto. Reutilizar `dialogs.js:openModal/closeModal` para foco/retorno, componentes de formulário e estados vazios já existentes. Não inventar um segundo shell.                                                                                                                 |
| Identidade visual           | `DESIGN-SYSTEM.md`, tokens semânticos em `socialmei.css`, temas em `storage-and-themes.js`, infraestrutura `motion.js`. Foco/seleção não dependem só de cor; reduced motion preserva a informação.                                                                                                                     |
| Perfil e demonstração       | `business-profile.js` é a fonte do perfil; `personalization.js` aplica capacidades. `businessViewData()` e helpers de apresentação separam a amostra opt-in dos dados originais. Não usar fixtures como fallback de erro.                                                                                              |
| Dados locais/remotos        | Stores da área escolhem modo/configuração por `SOCIALMEI_CONFIG`; renderer recebe dados, não URLs hardcoded. Não gravar localmente como substituto de escrita remota falha. Preservar timeout, validação, versões e replay quando aplicáveis.                                                                          |
| Conta/workspace             | `auth-store.js` e repositórios existentes delimitam estado local por identidade. Se houver API futura, o servidor resolve o workspace pela sessão/associação; não confiar no workspace livre enviado pelo browser. Perfil local não sincroniza entre dispositivos.                                                     |
| Estado e rascunhos          | UI transitória fica em memória; preferências/rascunhos usam os repositórios existentes. Preservar chaves legadas, sessão expirada, troca de conta, cancelamento sem salvar e conteúdo ao navegar. Persistência nova exige requisito e contrato próprios.                                                               |
| API/banco futuros           | Somente se aprovados: contrato da área, modelos/router e store; migration incremental após conferir a numeração, sem editar migrations aplicadas. Não duplicar regras no renderer e no n8n.                                                                                                                            |
| Testes e entrega            | Adicionar cenário a `tests/browser.cjs`; testes unitários da regra e contratos de store quando existirem. Cobrir zero/um/vários, local/remoto/falha, duas identidades, demo on/off, rascunhos, teclado/foco/Escape, 320/390/768/1024/1440 e temas/movimento reduzido. Rodar Node, format, navegador e CI no SHA final. |

Acoplamentos principais: globais/ordem dos scripts, cadeia de wrappers de `setView/renderCurrentView`, nomes de rotas salvos e chaves de persistência. Não introduzir um registro genérico de módulos antes de haver necessidade. A [estabilização de 19/10/2026](FRONTEND-STABILIZATION.md) registra as pendências operacionais separadas dos pontos de extensão.

## Alterações visuais e integrações

Consultar [DESIGN-SYSTEM.md](DESIGN-SYSTEM.md): tokens semânticos de cor, `--space-*`, `--r-*`, tipografia e motion já existem. Paletas e ajustes custom ficam em `storage-and-themes.js`; não transformar tokens antigos em um segundo conjunto concorrente. A cascata ainda tem overrides por componente/breakpoint. Alterar um componente por vez e conferir claro/escuro/auto/custom, foco, teclado, touch e reduced motion.

Classes/IDs existentes podem ser seletores de JavaScript. Novos handlers devem preferir `data-action`, `data-role` ou ID estável quando houver ganho; não reescrever seletores de todos os componentes para uma mudança de spacing.

Workflows usam o guia [n8n-workflows/README.md](../n8n-workflows/README.md): contrato, credenciais fora do export, teste isolado, export inativo, revisão e promoção explícita. API, workflow versionado e versão publicada são três estados distintos. A futura organização do n8n vivo precisa de acesso autorizado e backup conjunto de banco, volume e chave.
