# SocialMEI.IA — Code Maintainability Review

Coleta de 14/10/2026. Escopo: refatoração da implementação, sem redesign, novas funcionalidades ou deploy.

## Baseline

- Checkout inicial: branch `work`, SHA `92d4c20a106d330a24452f6cca969c79762c15b3`, sem alterações locais.
- `origin/main` conferido no mesmo SHA antes da nova branch `refactor/code-maintainability`.
- Inventário de 217 arquivos versionados: leitura de conteúdo dos textos, metadados dos binários e análise estática de JS/CSS/Python/JSON. Revisão detalhada dos pontos alterados e dos contratos de persistência, autenticação e infraestrutura.
- Baseline: 64 testes Node, 130 testes Python com PostgreSQL 16 isolado, navegador com 88 estados/21 fluxos, Prettier e 19 testes operacionais passaram. Cinco testes de gateway estavam ignorados na execução padrão e foram executados separadamente na validação final.
- Capturas antes/depois usam dados fictícios, relógio fixo, Chromium, movimento reduzido e dois temas em desktop/mobile. Não usam contas ou banco da AWS.
- `PROJECT-AUDIT.md`, `TEST-REPORT.md` e `NEXT-STEPS.md` não foram encontrados no checkout. As revisões históricas versionadas foram preservadas, sem inventar resultados desses anexos ausentes.

## Mapa e decisões

| Grupo                                                  | Classificação                                       | Decisão                                                              |
| ------------------------------------------------------ | --------------------------------------------------- | -------------------------------------------------------------------- |
| `frontend/socialmei-app.html`, scripts e estilos       | Atual, precisa de manutenção gradual                | Refatorações locais; entrada, ordem, IDs e aparência preservados.    |
| `frontend/socialmei-dashboard.html`, raiz `index.html` | Compatibilidade necessária                          | Redirecionamentos mantidos; não são uma segunda implementação.       |
| Páginas de administração/transferência e seus scripts  | Atual                                               | Gates, sessão, permissões e estados mantidos.                        |
| `python-service/`                                      | Atual                                               | Saúde reorganizada; rotas/modelos/CRUD/transações preservados.       |
| `database/migrations/`                                 | Configuração histórica necessária                   | Migrations 001–011 intactas; nenhuma migration nova.                 |
| SQL de bootstrap/permissões/atendimento                | Configuração/legado com contrato próprio            | Não usado como substituto do banco team; mantido.                    |
| Compose team/dev, Dockerfiles e Caddy                  | Configuração atual                                  | Mantidos; nomes, redes, mounts, auth e volumes não mudaram.          |
| Compose/Caddy genéricos e `backup.sh`                  | Pilha legada, ainda necessária                      | Não confundidos com team; nenhuma execução contra a pilha existente. |
| Sete exports `n8n-workflows/`                          | Operacional, exemplo ou experimental conforme pasta | Conteúdo intacto; todos inativos no Git, não importados/ativados.    |
| `tests/`, ferramentas de manutenção                    | Teste/ferramenta atual                              | Mantidos; três casos de navegação adicionados.                       |
| DevHub e catálogo de ferramentas                       | Ferramenta de desenvolvimento                       | Mantidos; catálogo grande não justifica inventar abstrações.         |
| `docs/`, arquivos técnicos de raiz                     | Documentação, parte histórica                       | Corrigidas orientações atuais; evidências datadas preservadas.       |
| Logos, fonte e imagens                                 | Asset necessário                                    | Mantidos; licença da fonte preservada.                               |

Nenhum arquivo foi removido, movido ou renomeado. Não houve prova suficiente para excluir assets ou seletores dinâmicos. Arquivos grandes não foram divididos apenas pelo número de linhas.

## Convenções

Novos helpers em inglês, interface em português, comentários curtos e formatação existente. Campos persistidos em português, classes/IDs históricos, storage keys, endpoints e nomes públicos de modelos continuam por compatibilidade. A revisão não troca uma inconsistência interna por uma quebra de API ou OpenAPI.

## HTML e CSS

Comentários de seção deixaram de usar separadores extensos. A confirmação de telefone passou de um template em uma linha para markup indentado, mantendo textos, foco, botões e diálogo nativo.

A análise encontrou quatro declarações idênticas repetidas no mesmo escopo. Foram removidas somente as anteriores, deixando a ocorrência posterior e sua posição:

- `.sb-collapse`: `min-height`;
- `.nav-group-label`: `color`;
- `#inboxView .inbox-shell`: `transition`;
- `#xpSetup .landing-setup-steps button[aria-selected="true"]`: `border-color`.

Não foram encontrados blocos de regra integralmente idênticos no mesmo escopo. Seletores repetidos com propriedades diferentes não foram tratados como regras mortas. Os 194 `!important` do CSS principal foram preservados; retirar proteções de responsividade/acessibilidade exige análise específica. Tokens, breakpoints e ordem de media queries permanecem.

## JavaScript e frontend

| Área                     | Antes                                                              | Depois                                                                                                              |
| ------------------------ | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| Navegação                | Listener principal calculava datas e gerenciava carregamento.      | `selectPeriod` e `applyCustomPeriod` ficam em `navigation.js`; listener encaminha as ações.                         |
| Home/header              | Dois blocos iguais de `Intl.DateTimeFormat`.                       | `getBusinessHour` mantém o fuso configurado e atende ambos.                                                         |
| Vendas                   | `updateSaleReview` era redefinida por wrapper após sua declaração. | Uma função atualiza total/validação e ajuda específica do modo remoto.                                              |
| Financeiro               | Ternários aninhados para status/labels.                            | Retornos explícitos mantêm as mesmas prioridades, inclusive pago antes de atraso.                                   |
| Inbox                    | Dois blocos iguais para mensagem inicial local.                    | `appendInitialLocalMessage` mantém timestamp no ponto original de cada fluxo; não envia mensagens.                  |
| Automações               | Área da regra recalculada para escolher ícone.                     | `ruleIcon` usa um `switch` com fallback existente.                                                                  |
| Assistente               | Callback misturava composição do texto e metadados/histórico.      | `buildAssistantDraftText` compõe sugestões; controlador preserva fontes, intenção, ordem e limite de dez registros. |
| Auth/admin/configurações | Contratos e proteções já separados em helpers/stores.              | Mantidos; somente markup da confirmação de contato foi formatado.                                                   |

Não foram fundidos os stores: estoque, versões, exclusões e importações têm regras diferentes. Estados locais/remotos, rollback de remoção de conversa, máscaras/limites de telefone, ownership dos diálogos e proteção contra escrita offline permanecem.

## Exemplos curtos

Trechos reais, sem reproduzir os renderers inteiros:

| Tipo       | Antes                                                               | Depois                                                                |
| ---------- | ------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Nome/hora  | `const h = Number(new Intl.DateTimeFormat(...).format(new Date()))` | `const hour = getBusinessHour()` em `renderHeader`.                   |
| Evento     | O bloco `[data-period]` calculava estado/carregamento no listener.  | `await selectPeriod(period.dataset.period)` encaminha para navegação. |
| Função     | `const baseSaleReview = updateSaleReview` seguido da redefinição.   | A condição `if (SocialMEISales.remote)` fica na função original.      |
| CSS        | `min-height: 44px` em dois blocos `.sb-collapse`.                   | Somente a declaração posterior permanece, com a mesma cascata.        |
| Comentário | Separador de três linhas ao redor de `AUTENTICAÇÃO — HTML`.         | `<!-- AUTENTICAÇÃO -->`.                                              |

## Backend

`database.check_database` passa a iterar `CRM_SCHEMA_QUERIES`, `AUTH_SCHEMA_QUERIES` e `CHANNEL_SCHEMA_QUERIES`. As 24 strings SELECT foram comparadas com a baseline e são idênticas. Ordem, timeout, transação somente leitura, requisitos de migrations e savepoint dos canais permanecem. Ausência de canal não torna o CRM indisponível; ausência de contas continua fatal quando auth está habilitada.

Autenticação, ContextVar do principal, CSRF, rate limit, isolamento por workspace, hashing, SQL parametrizado, versões e idempotência foram mantidos. Renomear funções públicas em português poderia mudar identificadores OpenAPI; isso não foi feito por preferência de linguagem.

## SQL, infraestrutura e n8n

SQL, Dockerfiles, Compose, Caddy, workflows Actions e sete exports n8n ficaram byte a byte iguais à baseline. Nenhuma alteração de portas, redes, volume, configuração privada, schema ou autorização. Os JSONs foram analisados e seus contratos cobertos pela suite; isso não homologa a versão viva dos workflows ou o atendimento externo.

A validação de Caddy usa uma rede e containers descartáveis próprios. Na primeira tentativa, três testes receberam 403 por chamadas internas encaminhadas pelo proxy do ambiente. Uma adaptação somente da execução local incluiu `team-api` na exceção de proxy interna; os cinco testes passaram sem editar Caddy nem relaxar proteção do app. Essa adaptação não foi versionada nem aplicada à AWS.

## Documentação

README aponta para esta revisão e deixa de apresentar evolução visual/calculadora como trabalho desta manutenção. README e DEVELOPMENT corrigem nove para 11 resoluções, conforme a suite existente. DEVELOPMENT descreve onde procurar os helpers; CONTRIBUTING inclui `refactor/`; ROADMAP distingue próximos itens atuais do planejamento antigo; DEPLOYMENT diferencia roteiro legado e team. CHANGELOG registra as alterações de código, sem afirmar publicação.

## Validação final

Resultados locais e CI são evidências separadas. O PR fornece o resultado remoto do SHA revisado.

| Verificação                           | Resultado local                                                                                                                            |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Node                                  | 67 testes passaram, incluindo três novos casos de período.                                                                                 |
| Python/API com PostgreSQL 16 isolado  | 130 testes passaram, sem skips.                                                                                                            |
| Operação/backup/admin                 | 19 testes passaram; os cinco de gateway exigem opt-in.                                                                                     |
| Gateway Caddy real, execução separada | Cinco passaram após adaptação interna de proxy.                                                                                            |
| Navegador funcional                   | 88 estados e 21 fluxos passaram.                                                                                                           |
| Estabilidade                          | 825 estados de layout/tema e 167 estados de botões passaram, sem pageerror/404 local.                                                      |
| Home/Financeiro visual                | 22 estados de cada módulo passaram; teclado, privacidade, spotlight, touch e reduced motion.                                               |
| Configurações                         | 990 estados passaram; salvar, temas, teclado e modos local/conectado conferidos.                                                           |
| Prettier e diff                       | Verificados sem mudar expectativas para esconder falhas.                                                                                   |
| Comparação de capturas                | 44 pares; 37 idênticos. Sete com até 39 pixels diferentes e até 5 níveis por canal RGB, sem deslocamento visível ou alteração de conteúdo. |

As capturas desconsideram toasts temporários; diferenças residuais foram inspecionadas, não chamadas de igualdade pixel a pixel. A suite funcional cobre erro/vazio, busca/filtros, CRUD, conflitos/replay, importação/exportação, contas, administração e transferência com fixtures. A matriz de temas inclui Light/Dark/Auto/Custom.

## Regressões e limites

Não foram identificadas regressões nas validações concluídas. A execução inicial de gateway falhou pelo proxy local, não por uma mudança no repositório. Testes padrão ignoram os cinco casos Docker até o opt-in; a execução separada os cobre. Dependências atuais emitem aviso de depreciação Starlette/httpx, sem falha de teste; atualização não foi misturada à refatoração.

Runtime AWS, n8n vivo, WAHA, SMTP, provedores externos e recuperação real dos backups de produção: **NÃO CONFIRMADOS nesta rodada**. Não houve SSH, deploy, migration, envio, pareamento ou restore em produção. Verificação HTTPS da stack completa e restauração isolada são gates do CI, não foram apresentadas como testes locais executados nesta revisão.

## Dívida restante e próxima etapa

- `app.js`, `experience.js`, `business-views.js`, CSS e DevHub continuam grandes; funções/renderers e estado global precisam de redução gradual por área.
- Scripts clássicos ainda dependem de globais e ordem de carregamento; mudar para módulos ES merece tarefa própria.
- A cascata mantém blocos complementares e overrides históricos. Consolidar um componente por vez, com comparação visual e estados dinâmicos; nenhum detector prova sozinho código morto.
- Migrations e contratos persistidos em português são compatibilidade, não convite à renomeação automática.
- Dependências Python sem versões fixas e imagens `latest` dificultam reprodução; fixação requer rodada de atualização/homologação própria.
- Exports experimentais mantêm ramos incompletos; equivalência com n8n vivo não está comprovada.
- Role superuser e cobertura de backups são pendências operacionais já relatadas, sem alteração nesta manutenção.

Próxima manutenção recomendada: isolar uma responsabilidade restante do listener de `app.js`, usando os testes existentes e contratos do módulo. Próxima integração continua condicionada a identidade, autorização e idempotência do atendimento. Novas funcionalidades e redesign não pertencem a esta revisão.
