# Arquitetura

## Gestão local ou compartilhada

O modo de cada módulo é explícito em `config.js`. No GitHub Pages, Clientes, Produtos, Vendas e Financeiro usam armazenamento local. No servidor da equipe, os quatro módulos usam FastAPI e PostgreSQL, protegidos pelo gateway. Dados de demonstração de atendimento não são dados compartilhados do CRM.

```mermaid
flowchart TD
    F[Frontend] -->|modo local| L[Dados do navegador]
    F -->|modo remoto| G[Gateway protegido]
    G --> A[API de gestão]
    A --> D[(Banco da equipe)]
    N[n8n] -->|Bearer de leitura| G
```

Os stores remotos preservam snapshots locais e recusam escrita quando a API está indisponível; não fazem fallback para gravação no navegador. Vendas e Financeiro usam IDs de operação duráveis, versões e recuperação de respostas perdidas. Vendas e lançamentos excluídos permanecem no banco como exclusões lógicas. Importações e transferência são transacionais; não renomeie contratos persistidos.

## Atendimento e infraestrutura legada

```mermaid
flowchart LR
    U[Usuário] --> F[Frontend estático]
    F -->|gestão, preferências e rascunhos| L[localStorage]
    F -->|GET de mensagens| C[Caddy HTTPS]
    O[Origem de teste ou adaptador de canal] -->|POST normalizado| C
    C --> N[n8n]
    N --> D[(PostgreSQL)]
    N -. workflow de exemplo .-> P[FastAPI]
    N -. integração a configurar .-> W[WAHA]
    C --> P
    C --> W
    C --> A[pgAdmin]
    A --> D
```

Este segundo diagrama descreve o Compose legado de atendimento, separado de `compose.team.yaml`. Linhas pontilhadas indicam integração experimental/a configurar. A FastAPI da equipe também oferece gestão; a API auxiliar antiga e o banco n8n são serviços distintos. WAHA não está conectado ao composer por código versionado. O Caddy interno da equipe serve o frontend; o Caddy público encaminha seu hostname para esse gateway.

## Frontend

`frontend/socialmei-app.html` é a fonte de markup. Os scripts clássicos são carregados em ordem, nas mesmas posições da versão aprovada. Algumas funções e variáveis são compartilhadas globalmente; trocar para `defer`, `async` ou módulos ES sem revisar a inicialização pode quebrar esse contrato.

- `storage-and-themes.js` e `motion.js` inicializam tema e movimento antes da interface.
- `inbox.js`, `inbox-sync.js`, `dialogs.js` e `navigation.js` cuidam do atendimento e do shell.
- `business-views.js` renderiza os módulos de gestão; helpers menores ficam em `sales.js`, `finance.js`, `customers.js` e `products.js`.
- `app.js` reúne dados demonstrativos, estado, utilitários, eventos e inicialização.
- `experience.js` ainda concentra landing/auth/onboarding, Home, Assistente e automações locais.
- `record-editor.js` integra edição/confirmação e persistência de rascunhos.

A extração separou responsabilidades em arquivos; não eliminou todos os acoplamentos internos. `frontend/styles/socialmei.css` preserva a cascata, com seções e media queries próximas dos componentes.

### Persistência e compatibilidade

`socialmei-app-data-v2` guarda dados locais e preferências; os módulos configurados como remotos preservam seus snapshots originais nessa chave. `socialmei-inbox-local-v3` guarda estado local do atendimento. Perfil, temas, regras e vínculos locais de conversas têm chaves próprias. O backup JSON reúne chaves `socialmei-`/`socialmei_`, com validação antes da importação; não substitui o dump do PostgreSQL compartilhado.

Campos como `clientes`, `nome` e `mensagem`, IDs existentes e classes antigas são contratos preservados. Novos nomes internos usam inglês; renomear dados persistidos exige migração. `sessionData` contém conversas/atividade de demonstração e não é uma fonte compartilhada entre usuários.

## Caixa Unificada e n8n

O app consulta `frontend/config.js`, faz GET e espera `{ "mensagens": [...] }`. O intervalo progride de 4 para 8, 15 e 30 segundos quando não há novidades/ocorrem falhas; pausa com aba oculta, offline, fora da experiência do app ou sem URL configurada. `n8nMessagesUrl: null` desativa a leitura. A opção `since` permanece desligada porque o SQL versionado não implementa esse filtro.

O export `n8n-workflows/producao/01-caixa-unificada-api-postgresql.json` possui dois caminhos:

1. POST → normalização → SQL parametrizado → confirmação.
2. GET → leitura das últimas 50 mensagens de entrada → JSON com CORS `*` e `Cache-Control: no-store`.

A gravação faz upsert de cliente/conversa e insere mensagem. O frontend identifica conversas pelo nome/canal; o payload de leitura não inclui IDs estáveis de cliente/conversa. Reenvio de webhook não é deduplicado por ID externo na query de inserção. São limites para resolver antes de receber tráfego real.

Export inativo não significa workflow inativo na VPS: Git e ambiente remoto são estados separados. Credenciais precisam ser selecionadas após importar. Workflows experimentais de Instagram têm dependências Gemini/Meta e autenticação por credencial n8n; não são a IA do Assistente local.

## Banco

PostgreSQL 16 atende o banco interno do n8n e o schema funcional `socialmei` com `clientes`, `conversas`, `mensagens`. `bootstrap.sql` exige a role `socialmei_admin` previamente criada. `permissions.sql` prepara `socialmei_app`, sem senha versionada, e cita explicitamente o banco `n8n`.

Esses scripts de atendimento são distintos das migrations incrementais de gestão em `database/migrations/`. O ambiente local usa `npm run db:migrate`; a equipe usa `team-migrate` antes da API. O workspace é escolhido pelo servidor, não pelo usuário do navegador; não há autorização por negócio ou isolamento por usuário da aplicação. Os grants do bootstrap legado pressupõem tabelas criadas por `socialmei_admin`. Veja [docs/BANCO-DE-DADOS.md](docs/BANCO-DE-DADOS.md).

## Infraestrutura

`compose.yaml` é a definição completa: PostgreSQL, n8n, pgAdmin, Caddy, FastAPI e WAHA. `compose.override.yaml` mantém compatibilidade sem redefinir serviços. Caddy publica 80/443; WAHA tem bind `127.0.0.1:3000`; PostgreSQL e FastAPI não publicam portas próprias.

Os hosts WAHA/FastAPI podem ser configurados por ambiente, com fallback para os endereços históricos. O hook histórico do WAHA aponta à raiz do n8n e precisa ser validado/mapeado ao adaptador de recebimento. Não há workflow versionado que prove o envio pelo composer.

O script `backup.sh` descobre o volume real do n8n, gera dump/configuração e arquiva dados do n8n com parada temporária. Não faz backup dos volumes WAHA/pgAdmin/Caddy, nem fornece snapshot atômico entre banco e arquivos.

`compose.team.yaml` cria banco, API, migrador e gateway separados, sem portas publicadas. A API da equipe só é exposta pelo proxy/gateway; seu CRUD não possui login próprio. O gateway exige Basic auth nas rotas humanas. Somente cinco rotas GET técnicas de leitura aceitam Bearer na API; o token não abre o site nem autoriza escrita.

`tools/team-maintenance.py` faz backup do banco/configuração da equipe sem interrupção, confere o índice e hashes e pode agendar uma execução diária. A restauração é exercitada em banco isolado no CI. Cópias na própria instância exigem armazenamento externo para proteger contra perda do host. Veja [docs/OPERACAO-EQUIPE.md](docs/OPERACAO-EQUIPE.md).
