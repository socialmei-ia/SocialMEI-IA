# Desenvolvimento

## Preparação

O caminho recomendado para a equipe é usar o ambiente Docker local:

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/nome-da-tarefa
npm ci
npm run setup
npm run dev
```

Abra:

- Frontend: http://localhost:5500
- n8n: http://localhost:5678
- FastAPI: http://localhost:8000/health

O ambiente padrão também cria um PostgreSQL local isolado. pgAdmin e WAHA são opcionais:

```bash
npm run dev:tools
npm run dev:waha
```

Veja [docs/ONBOARDING.md](docs/ONBOARDING.md) para o passo a passo completo.

Se quiser trabalhar apenas no frontend sem Docker, ainda é possível usar:

```bash
python -m http.server 5500
```

## Onde editar

| Necessidade                                        | Arquivo                                                               |
| -------------------------------------------------- | --------------------------------------------------------------------- |
| Markup e telas                                     | `frontend/socialmei-app.html`                                         |
| URL pública do n8n                                 | `frontend/config.js`                                                  |
| Tokens, layout, componentes e responsividade       | `frontend/styles/socialmei.css`                                       |
| THEME                                              | `frontend/scripts/storage-and-themes.js`, `appearance.js`             |
| MOTION                                             | `frontend/scripts/motion.js` e seção motion do CSS                    |
| SIDEBAR / NAVIGATION                               | `frontend/scripts/navigation.js`, renderização em `business-views.js` |
| INBOX                                              | `frontend/scripts/inbox.js`, `inbox-sync.js`                          |
| CRUD / MODALS                                      | `frontend/scripts/dialogs.js`, `record-editor.js`                     |
| DATA / BACKUP                                      | `frontend/scripts/data-and-backup.js`                                 |
| HOME / AUTH / ONBOARDING / ASSISTANT / AUTOMATIONS | `frontend/scripts/experience.js`                                      |
| BUSINESS MODULES                                   | `frontend/scripts/business-views.js` e helpers de cada módulo         |
| REPORTS / SETTINGS                                 | `frontend/scripts/app.js`; exportação em `reports.js`                 |
| API Python                                         | `python-service/app.py`                                               |
| Toolbox                                            | `tools/devhub.js`, `tools/devhub.css`, `tools/mike-devhub.html`       |

Os arquivos preservam a ordem dos scripts clássicos do HTML. Não reorganize a sequência somente pelo nome. A inicialização acontece em `app.js` e depois `experience.js`; algumas funções anteriores dependem desse estado quando chamadas.

## Convenções

- JavaScript: `camelCase`, constantes em `UPPER_SNAKE_CASE`; Python: `snake_case`.
- Novas classes/IDs/data attributes e nomes técnicos em inglês. Textos da interface em português.
- Comentários curtos que explicam intenção/limite; não descrevam o óbvio.
- Use tokens existentes para cor, duração e spacing. Não acrescente correções indiscriminadas ao fim do CSS.
- Preserve IDs/classes compartilhados, rotas `/processar`, chaves localStorage e campos JSON/SQL em português até haver migração e teste de compatibilidade.
- Use Prettier (`npm run format` / `format:check`). Template strings têm formatação embutida desligada para preservar seu conteúdo.
- Não crie HTMLs `final2`, `backup` ou numerados. Histórico fica no Git.

## Testes

```bash
npm test
npm run format:check
python -m unittest discover -s tests -p 'test_*.py'
```

Os testes Node validam sintaxe e contratos globais, recursos relativos, IDs, stores remotos, backups, temas, exports e normalização n8n. Alguns testes de operação usam Docker falso; o CI também verifica gateway, pilha da equipe e restauração de backup em banco isolado, usando containers reais.

Para navegador:

```bash
npx playwright install chromium
npm run test:browser
```

Opcionalmente defina `CHROMIUM_EXECUTABLE` para uma instalação local. A suíte inicia seu próprio servidor em localhost, bloqueia serviços externos e grava evidências em `test-results/`, ignorado pelo Git. Os fluxos são locais; valide integração remota separadamente em ambiente de teste.

Checklist manual complementar: filtros do Inbox, modais por Escape/Tab, formulários inválidos, anexos, preferências, login/onboarding nas quatro larguras, tema custom, reduced motion e recarga com dados existentes. Não use **limpar dados** sobre o navegador de trabalho sem exportar um backup.

## API Python

```bash
python -m venv .venv
# Ative o ambiente virtual conforme seu sistema.
python -m pip install -r python-service/requirements.txt
python -m uvicorn app:app --app-dir python-service --reload
python -m unittest discover -s python-service -p 'test_*.py'
```

Abra http://127.0.0.1:8000/health ou `/docs`. `/processar` recebe `{ "texto": "Olá" }`; a resposta mantém `original`, `maiusculo`, `quantidade_caracteres`. Os testes verificam funções/modelo/rotas, não substituem um teste HTTP completo do servidor.

## Workflows e SQL

Leia [n8n-workflows/README.md](n8n-workflows/README.md). Importe em um projeto de teste, selecione credenciais locais e deixe o fluxo inativo até validar. Exporte sem credenciais, cabeçalhos secretos, dados fixados ou metadados de pessoas. Execute `npm test` depois de alterar JSON ou o código de normalização.

SQL deve ser revisado e aplicado por responsável pelo banco. `database/migrations/` contém as migrations incrementais de gestão: use `npm run db:migrate` no desenvolvimento. A pilha da equipe executa `team-migrate` antes da API; o Compose legado não aplica o bootstrap de atendimento automaticamente. Novas alterações precisam de migrations com plano de compatibilidade.

## Docker e revisão

Validação de configuração não inicia serviços:

```bash
docker compose --env-file .env.example config --quiet
bash -n backup.sh
```

`.env.example` tem placeholders; não o use para publicar serviços. Em operação use o `.env` privado e [DEPLOYMENT.md](DEPLOYMENT.md). Faça commits por responsabilidade e abra PR; não publique dumps, credenciais, artefatos de teste ou dependências.

## Regressão da base estabilizada

`node tests/stability-browser.cjs` cobre 11 resoluções, Light/Dark/Auto-Light/Auto-Dark/Custom, telas públicas e módulos, labels de botões e recursos locais. A suite normal mantém CRUD/conflitos/replay/contas/teclado. O alias “Meu negócio” leva intencionalmente à Visão Geral.

Use `TEST_DATABASE_URL` apenas em PostgreSQL descartável. `test_workspace_integrity.py` verifica FKs, upgrade interrompido sem reparação, histórico e o perfil interno de leitura; alterações de estrutura/grants são exercitadas em transações de teste. A migration 011 não foi aplicada ao servidor nesta revisão. Resultados em [PROJECT-BASELINE-REVIEW.md](PROJECT-BASELINE-REVIEW.md).

## Manutenção sem mudança de comportamento

Antes de refatorar, registre SHA/status e execute as suites da área. Use uma branch `refactor/`, mudanças pequenas e commits por responsabilidade. Preserve nomes de payloads, chaves do armazenamento, classes/IDs usados pelos scripts e ordem de carregamento.

A seleção de período fica em `navigation.js`; a hora comercial, em `home.js`. O listener de `app.js` encaminha essas ações. `inbox.js` monta mensagens iniciais locais. Dentro de `experience.js`, a composição do texto do Assistente fica separada da gravação do histórico. Os stores continuam próprios de cada módulo: versões, importações e estoque têm regras diferentes.

Compare desktop/mobile, temas e movimento reduzido antes/depois de mexer na cascata. Não retire seletores ou `!important` apenas por repetição: estados dinâmicos e media queries podem depender deles. Consultas de saúde estão agrupadas em `python-service/database.py`; permanecem somente leitura e não comprovam conexão real dos canais.

Veja [CODE-MAINTAINABILITY-REVIEW.md](CODE-MAINTAINABILITY-REVIEW.md). Testes usam dados fictícios e banco isolado; nunca a configuração privada da AWS.
