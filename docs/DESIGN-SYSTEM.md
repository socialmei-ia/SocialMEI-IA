# Design system visual do SocialMEI.IA

Referência da implementação na branch `feat/visual-redesign`, iniciada em `31a94c2b1c9eb4b80c5a6413e71e1cd383178862`. O [relatório de redesign](../VISUAL-REDESIGN-REPORT.md) separa validação local, CI e publicação no servidor.

## Direção

Uma interface de trabalho tranquila, com azul para ações e dourado para a identidade. A landing tem composição editorial; o aplicativo prioriza leitura, próximos passos e informação existente. Branco quente no tema claro e azul profundo no escuro, sem efeitos luminosos em tabelas ou animações contínuas na Home.

Mobbin orienta a hierarquia e o espaço entre texto e demonstração. Os dois componentes fornecidos como referência de 21st foram adaptados para HTML, CSS e JavaScript puro. Não há React, Tailwind, biblioteca de animação nova ou assets copiados de outras marcas.

## Fonte e tipografia

Inter variável já existente em `frontend/assets/inter-variable.woff2`, com licença preservada. `--font-ui` inclui fontes de sistema como fallback. O carregamento continua com `font-display: swap`; não existe promessa de layout shift zero.

| Uso                   | Token / orientação                                                   |
| --------------------- | -------------------------------------------------------------------- |
| Metadados             | `--text-xs`: 12px                                                    |
| Controles             | `--text-sm`: 14px                                                    |
| Corpo                 | `--text-base`: 15px; `--leading-body`: 1.55                          |
| Títulos internos      | Escalas fluidas `--heading-sm` e `--heading-lg`                      |
| Títulos editoriais    | Escalas `--display-sm` e `--display-md`; landing com regras próprias |
| Entrelinha de título  | `--leading-heading`: 1.16                                            |
| Entrelinha de display | `--leading-display`: 1.06                                            |
| Valores               | Algarismos tabulares, peso 550–600; número principal maior           |

Evitar caixa alta em conteúdo longo, peso 800 em todos os títulos e títulos de landing nas telas operacionais. Alguns componentes legados ainda têm tamanhos próprios; esta etapa não converteu todos os valores existentes em tokens.

## Cores

| Papel                 | Claro     | Escuro    |
| --------------------- | --------- | --------- |
| Fundo                 | `#F7F7F2` | `#0C1624` |
| Superfície            | `#FFFFFF` | `#142134` |
| Superfície secundária | `#EEEFEA` | `#1B2B42` |
| Borda                 | `#DFE3E7` | `#304057` |
| Texto principal       | `#1C2B3A` | `#EEF3FA` |
| Texto secundário      | `#526171` | `#B6C4D5` |
| Texto discreto        | `#657282` | `#A4B3C6` |

Azul de marca `#1E73D8` e dourado `#F2B11B` permanecem. Usar os tokens semânticos `--brand-primary-text`, `--on-primary`, `--success`, `--warning` e `--danger`, porque os estados e o contraste variam por tema. Não substituir todos por cores literais da tabela.

O tema automático acompanha o sistema. O tema custom mantém contrato, validação, persistência e ajustes de legibilidade existentes em `storage-and-themes.js`. As variáveis `--landing-*` controlam as superfícies públicas; não presumir que toda personalização do aplicativo recolore a landing.

## Espaço, forma e componentes

- Escala principal de 4px: `--space-1/2/3/4/6/8/12` = 4/8/12/16/24/32/48px. Os aliases anteriores permanecem por compatibilidade.
- Raios `--r-sm/md/lg` = 10/16/22px. Pílulas apenas para estados, tags e avatares apropriados.
- Controles compartilhados usam `--control-height`: 44px; autenticação usa campos de 48px. Não implica que todos os ícones legados já tenham alvo de 44px.
- Sombras pequenas para superfície interativa e sombra média para menus. Borda e contraste de fundo devem separar painéis antes de acrescentar sombra.
- Botão primário identifica a ação principal; secundários têm borda discreta. Destrutivos conservam estado de perigo e confirmação existentes.
- Inputs mantêm rótulos, foco visível, erros e validação. O indicador de senha é complementar e não bloqueia envio.
- Tabelas usam cabeçalho discreto, linhas legíveis e ações previsíveis. Nas larguras pequenas permanece a apresentação mobile já existente, sem ocultar campos por estética.
- Modais compartilham cabeçalho, corpo e rodapé mais espaçados. Drawers conservam ciclo de foco, fechamento e comportamento por módulo.

## Shell e personalidade dos módulos

Sidebar desktop de 232px, linha ativa azul suave, topbar calma e conteúdo com limite de largura de 1500px. A navegação de negócio e os destinos originais continuam funcionando. Sidebar compacta, menu mobile e contexto são comportamentos existentes, não uma arquitetura de navegação nova.

| Área                          | Papel visual                                                                                        |
| ----------------------------- | --------------------------------------------------------------------------------------------------- |
| Home                          | Saudação, busca de ações, conversa em andamento, prioridades e últimas vendas reais do estado atual |
| Caixa Unificada               | Conversas, mensagens e contexto do cliente com superfícies diferenciadas                            |
| Clientes / Vendas             | Diretório e registros com filtros e ações de rotina                                                 |
| Produtos                      | Identificação, preço e disponibilidade no catálogo existente                                        |
| Financeiro                    | Saldo registrado destacado; resumo em uma coluna até 720px para preservar a leitura monetária       |
| Relatórios / visão de negócio | Dados, períodos e gráficos; tooltip e navegação acessível preservados                               |
| Assistente                    | Contexto, intenção e rascunho revisável; não confundir sugestão local com IA remota integrada       |
| Automações                    | Etapas, preparação e resultado da rotina local, sem afirmar execução externa                        |
| Configurações / Administração | Navegação de preferências, conta e permissões sem mudar regras de acesso                            |
| Auth / onboarding             | Mesma identidade, campos claros e progressão existente; sem abrir cadastro público                  |

## Motion

| Token                               | Duração | Uso                          |
| ----------------------------------- | ------- | ---------------------------- |
| `--motion-instant`                  | 100ms   | Resposta mínima              |
| `--motion-fast`                     | 150ms   | Hover, ícone e controle      |
| `--motion-base`                     | 210ms   | Estado de componente e toast |
| `--motion-page` / `--motion-dialog` | 280ms   | Troca interna e diálogo      |
| `--motion-drawer`                   | 300ms   | Painel lateral               |
| `--motion-medium`                   | 340ms   | Composição curta             |
| `--motion-slow`                     | 600ms   | Reveal seletivo              |
| `--motion-hero`                     | 760ms   | Entrada principal            |
| `--stagger`                         | 50ms    | Sequência curta              |

As curvas existentes `--ease-standard/out/enter/exit/spring` foram mantidas. A landing também mantém tokens próprios e sequências já implementadas: reveal 680ms, display/mask 780ms na definição pública final. Portanto, os tokens centrais ainda não representam todas as animações legadas.

- **Fade / up:** chegada de mensagem, menu e conteúdo por viewport; preferir opacity/transform.
- **Scale:** feedback pequeno de controle, sem ampliar linha de tabela inteira.
- **Blur / mask / stagger:** títulos e demonstrações da landing. Evitar texto operacional desfocado ou atraso na leitura do aplicativo.
- **Slide:** drawer com foco preservado.
- **Parallax / morph:** não adicionados nesta etapa. Não são necessários para o objetivo.
- **Spotlight:** somente três demonstrações públicas; um único elemento acompanha o ponteiro por frame. Não usar no app inteiro.

`prefers-reduced-motion` elimina as animações do aplicativo e desliga spotlight. Touch/coarse também desliga spotlight; nenhuma regra bloqueia o scroll touch. O novo indicador de senha anuncia o resumo com debounce de 700ms e anima apenas suas barras.

## Responsividade e acessibilidade

Preservados breakpoints por componente: 640px em partes da Home, 720px em gestão, 900px no shell e 1000px em navegação pública. Não houve migração global dos breakpoints. A matriz testa 1920, 1600, 1440, 1366, 1280, 1024, 900, 768, 430, 390 e 360px, em claro, escuro, automático claro/escuro e custom.

Preservar IDs, `data-*` de eventos, relações ARIA e foco ao editar componentes. Cor não substitui texto de estado. O indicador de senha tem `role="meter"`, regras textuais, sugestão expansível por teclado e anúncio sem incluir a senha. Não armazena nem transmite o valor.

A validação automatizada não substitui revisão com leitores de tela reais, alto contraste do sistema ou aparelhos físicos.

## Onde alterar

- `frontend/styles/socialmei.css`: tokens, shell, landing e componentes existentes. Procurar seções e seletor original antes de acrescentar override.
- `frontend/styles/account-ui.css`: conta e administração.
- `frontend/styles/interaction-components.css`: apenas os dois novos componentes auxiliares.
- `frontend/scripts/experience.js`: experiência pública e Home; métricas reutilizam as fontes existentes.
- `frontend/scripts/password-strength.js`: avaliação e montagem do indicador, sem alterar autenticação.
- `frontend/scripts/spotlight.js`: efeito de ponteiro limitado à landing.

A dívida de CSS monolítico permanece. A consolidação desta etapa remove propriedades superadas dos seletores alterados; não elimina toda duplicação histórica nem renomeia classes que os scripts utilizam.
