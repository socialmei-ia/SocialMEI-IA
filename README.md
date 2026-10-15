# SocialMEI.IA

CRM experimental para MEIs: atendimento, clientes, produtos e serviços, vendas e financeiro em uma interface de HTML, CSS e JavaScript puro.

![SocialMEI.IA](docs/assets/socialmei-banner.svg)

[Desenvolvimento](DEVELOPMENT.md) · [Arquitetura](ARCHITECTURE.md) · [Contas](docs/CONTAS-MEIS.md) · [Operação](docs/OPERACAO-EQUIPE.md) · [Revisão da base](PROJECT-BASELINE-REVIEW.md) · [Manutenção do código](CODE-MAINTAINABILITY-REVIEW.md)

[Design system](docs/DESIGN-SYSTEM.md) · [Redesign e validação](VISUAL-REDESIGN-REPORT.md) · [Configurações](docs/SETTINGS-REDESIGN.md)

Para começar uma alteração: [ambientes e dados](docs/ENVIRONMENTS.md) → [onde editar e como adicionar uma feature](docs/PROJECT-STRUCTURE.md). A [revisão de preparação](FUTURE-READINESS-REVIEW.md) registra a limpeza incorporada, configuração centralizada, testes e pendências; não representa deploy.

A próxima fase segue o [V2 Foundation Plan](docs/V2-FOUNDATION-PLAN.md): Python versionado por HTTP, entrega por SHA e protótipo antes de integrar uma feature visual grande. A [exploração de Oportunidades](prototypes/README.md) é isolada e usa apenas dados fictícios; não está no aplicativo.

## Estado do projeto

A versão da equipe possui API FastAPI, persistência PostgreSQL e contas com isolamento de negócio. O cadastro do piloto team está temporariamente aberto, sem convite; login e proteção Basic continuam ativos. É possível voltar ao cadastro por convite pela configuração descrita em [Contas](docs/CONTAS-MEIS.md). O Pages continua sendo uma demonstração local. WhatsApp real, IA remota, recuperação por e-mail e execução automática das regras ainda não estão homologados.

| Área                    | Implementação atual                                                                                                                       |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Contas                  | Login, sessão revogável, convite e administração quando a autenticação remota está habilitada; Basic do gateway é uma proteção adicional. |
| Clientes e catálogo     | CRUD por API/PostgreSQL ou local, conforme a configuração; versões, importação e validação monetária.                                     |
| Vendas e financeiro     | Operações com identidade, recuperação de resposta perdida, estoque transacional, histórico e exclusão lógica no modo remoto.              |
| Relatórios              | Indicadores e CSV sobre os dados carregados; não são prova de uma integração de atendimento.                                              |
| Caixa Unificada         | Demonstração local ou leitura legada configurada; notas/rascunhos locais. O composer não envia ao WhatsApp.                               |
| Assistente e automações | Sugestões/regras locais e execução simulada; não ativam IA remota ou workflows n8n.                                                       |
| Canais                  | Fundação de banco preparada; conexão, adaptador, autorização e idempotência do atendimento permanecem etapas próprias.                    |

**Git, CI e runtime são evidências diferentes.** Um merge não atualiza automaticamente a API da AWS. O [inventário vivo](docs/LIVE-ENVIRONMENT-INVENTORY.md) registra coletas anteriores e lacunas; a [revisão da estabilização](PROJECT-BASELINE-REVIEW.md) identifica o que foi testado nesta rodada.

## Rodar a demonstração

Com Git e Python 3:

```bash
git clone https://github.com/socialmei-ia/SocialMEI-IA.git
cd SocialMEI-IA
python -m http.server 5500
```

Abra http://localhost:5500. O `index.html` redireciona para **`frontend/socialmei-app.html`**, a fonte principal. Não há build para servir o frontend; mantenha CSS, scripts e assets juntos. A configuração pública fica em `frontend/config.js` e nunca deve conter segredos.

## Desenvolver com banco local

Com Node 22+, Python e Docker/Compose:

```bash
npm ci
npm run doctor
npm run setup
npm run dev
```

A preparação cria arquivos locais; não execute esses comandos sobre a pasta de produção. O ambiente local usa `compose.dev.yaml`, separado da equipe e do legado. Veja [onboarding de desenvolvimento](docs/ONBOARDING.md) e [DEVELOPMENT.md](DEVELOPMENT.md).

## Onde alterar

| Diretório/arquivo                   | Responsabilidade                                                                         |
| ----------------------------------- | ---------------------------------------------------------------------------------------- |
| `frontend/socialmei-app.html`       | Estrutura da aplicação e experiência pública.                                            |
| `frontend/scripts/`                 | Stores, autenticação, telas, diálogos e navegação; scripts clássicos na ordem do HTML.   |
| `frontend/styles/`                  | Design atual, temas e estilos de contas; sem framework.                                  |
| `frontend/admin.html`               | Administração autenticada.                                                               |
| `python-service/`                   | API, autorização e testes de contrato/integração.                                        |
| `database/migrations/`              | Evolução incremental do schema; nunca reescrever migrations instaladas.                  |
| `database/team-readonly-access.sql` | Perfil administrativo de consulta preparado para concessão individual; aplicação manual. |
| `n8n-workflows/`                    | Sete exports classificados e inativos; não representam integralmente o runtime n8n.      |
| `tools/`                            | Preparação, operação, backup e migrador.                                                 |
| `tests/`                            | Regressões de frontend, stores e operação.                                               |
| `docs/`                             | Guias, contratos e evidências datadas.                                                   |

## Testar

```bash
npm ci
npm test
npm run format:check
python -m pip install -r python-service/requirements.txt
python -m unittest discover -s python-service -p 'test_*.py'
python -m unittest discover -s tests -p 'test_*.py'
npx playwright install chromium
npm run test:browser
node tests/stability-browser.cjs
```

Integrações Python exigem `TEST_DATABASE_URL` apontando **somente para um PostgreSQL descartável**: algumas suites alteram/truncam suas fixtures. Sem essa variável, os casos de banco são ignorados. Gateway/HTTPS exigem Docker. Não use credenciais ou banco de produção nos testes.

O CI usa PostgreSQL 16, verifica a stack team isolada, exercita backup/restore no destino de teste e executa os browsers. A matriz adicional cobre 11 resoluções e Light/Dark/Auto/Custom. Evidências ficam no artifact `frontend-regression`. Veja [contratos da API](docs/API-ENDPOINTS.md).

## Publicação e acesso

- **Pages:** demonstração pública, com dados locais; o ramo configurado pode publicar após merge.
- **Equipe AWS:** gateway serve `frontend/socialmei-app.html` na raiz, com Basic e autenticação do app. O `index.html` da raiz do Git não é essa entrada. Atualização usa SHA aprovado e somente o serviço necessário.
- **Legado:** n8n, WAHA, Caddy e seu banco têm Compose/configuração próprios. Não misture as pilhas.
- **Workflows manuais do GitHub:** staging/produção genéricos existem, mas não devem ser usados para atualizar a implantação team sem conferir seus contratos.

Backup verificado precede migrations/configuração/deploy. Em 13/10/2026, o responsável confirmou checkout team `ae73f6e…` (PR #35), migration **011** instalada com sete constraints validadas e frontend publicado; somente o gateway foi recriado. Login, abertura dos cinco módulos de gestão, saída e reentrada confirmados após publicação. O perfil de consulta permanece preparado, sem aplicação/provisionamento na AWS; a role atual da API foi observada como superuser e exige revisão própria. Evidências em [REMEDIATION-STATUS.md](docs/REMEDIATION-STATUS.md); acesso colaborativo em [TEAM-DATABASE-ACCESS.md](docs/TEAM-DATABASE-ACCESS.md). PostgreSQL continua sem porta pública.

## Próxima etapa

A rodada de manutenção separa responsabilidades de navegação, sugestões locais e saúde da API, preservando os contratos e a interface. Veja o [relatório de manutenção](CODE-MAINTAINABILITY-REVIEW.md) para alterações, testes e dívida restante.

A próxima etapa operacional continua sendo conferir permissões do banco, cobertura dos backups e identidade/autorização do atendimento antes de conectar canais reais. Recuperação por e-mail, WhatsApp real, onboarding acompanhado e novas funcionalidades dependem das decisões do responsável. Esta revisão não publica serviços na AWS.

[Roadmap](ROADMAP.md) · [Changelog](CHANGELOG.md) · [Deploy](DEPLOYMENT.md) · [Contribuição](CONTRIBUTING.md) · [Segurança](SECURITY.md)
