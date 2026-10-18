# Etapa Negócio — integração da composição vertical aprovada

Integração na aplicação oficial, exclusivamente na branch `feat/socialmei-native-integration`. HEAD inicial local e remoto: `f1b62cf5fc7e60bc6058a4c371715677ad299571`, árvore limpa. `main` continuava em `f07892f`. A aprovação desta rodada autoriza integrar e testar; não autoriza publicação. Nenhum merge, deploy ou acesso à produção.

## O que mudou

A etapa 2 agora segue a composição aprovada: introdução e nome do negócio; busca junto ao título das áreas; seis áreas em grade; especialidades abaixo, com a mesma largura; escolha atual e alternativa de lista completa; ofertas e detalhes opcionais; navegação no fim do conteúdo.

- Desktop: três colunas de áreas e especialidades. Tablet: duas. Mobile: uma, com descrições completas e alvos amplos. Não há painel lateral nem alturas artificiais para preencher a tela.
- Rodapé em fluxo normal somente na etapa Negócio. Voltar/Continuar permanecem lado a lado no celular quando cabem, podendo ocupar duas linhas com texto ampliado. Na edição, Cancelar e Continuar também têm alvos de pelo menos 44 px. As demais etapas conservam o rodapé fixo existente.
- A seleção de área mantém foco no botão e não força rolagem até as especialidades. Há feedback de seleção, contagem de opções e atualização de até 180 ms. Uma seleção rápida cancela a animação anterior; a infraestrutura existente respeita movimento reduzido.
- Busca, aliases, acentos, lista completa, IDs e as 23 especialidades continuam no modelo/controlador nativo. O controlador do protótipo não é carregado pela aplicação.

## Preservação das escolhas

O comportamento anterior redefinia produtos/serviços sempre que a especialidade mudava. Isso podia retirar serviços, categorias, capacidades ou ferramentas ao normalizar o perfil. A integração protege as escolhas explícitas e os perfis recuperados: mudar de especialidade não altera esses tipos de oferta nem descarta os respectivos dados.

Sugestões iniciais de tipo de oferta continuam funcionando durante a descoberta de uma conta nova, antes de escolhas explícitas ou de concluir a etapa. Voltar de uma etapa ainda vazia não bloqueia essas sugestões. Se o usuário alterar produtos/serviços deliberadamente, a normalização existente continua se aplicando.

Explorar outra área ou pesquisar também não invalida a especialidade já escolhida. O resumo mantém a escolha visível; é possível continuar com ela sem selecionar outra atividade. Validação de especialidade ausente permanece obrigatória, com mensagem próxima ao seletor e anúncio acessível.

A revisão permite voltar diretamente, mudar e retornar. Cancelar a edição não grava o rascunho; confirmar continua usando o mesmo repositório, escopo e momento de persistência. Nenhuma alteração em `business-profile.js`, autenticação, stores, chaves ou contratos. Preferências continuam **locais neste navegador, inclusive para contas autenticadas**, sem sincronização entre dispositivos.

## Arquivos

| Arquivo                                      | Motivo                                                                                                                                                                             |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/socialmei-app.html`                | Reorganização apenas do painel 2 e feedback/contagem do seletor. Todos os IDs anteriores preservados.                                                                              |
| `frontend/styles/business-profile.css`       | Composição vertical, grids responsivos, seleção e rodapé contextual, incluindo texto ampliado.                                                                                     |
| `frontend/scripts/experience.js`             | Proteção das escolhas, validação coerente ao explorar áreas, atualização do seletor e foco/motion.                                                                                 |
| `tests/adaptive-onboarding-browser.cjs`      | Regressões de layout, preservação, edição mobile, teclado, movimento e legibilidade interna dos botões.                                                                            |
| `tests/personalization-browser.cjs`          | O cenário que muda perfumaria para costura passa a escolher explicitamente somente serviços; também verifica que a mudança de especialidade preserva produtos antes dessa decisão. |
| Este guia, capturas e atualização do guia V3 | Evidências e instruções de revisão.                                                                                                                                                |

Comparação direta dos painéis HTML confirmou que as etapas 1, 3, 4, 5 e 6 não foram alteradas. Home, catálogo, Oportunidades, Relatórios, autenticação e persistência não receberam código novo nesta rodada.

## Verificação e limites

Resultados finais em [validation.json](onboarding-business-native/validation.json), com dados sintéticos e APIs interceptadas:

- `npm test`: **211 aprovados, zero falhas**.
- `npm run format:check`: aprovado; sintaxe e `git diff --check` aprovados.
- `CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser`: **88 estados e 25 fluxos aprovados**, incluindo conta/cadastro, Oportunidades, personalização, catálogo, vendas, financeiro, relatórios, temas, layout e motion; zero erros JavaScript.
- `CHROMIUM_EXECUTABLE=/usr/bin/chromium node tests/adaptive-onboarding-browser.cjs`: **seis cadastros, 108 estados de layout e 18 composições aprovados**, reexecutado após o ajuste final do rodapé. Inclui as regressões de persistência, isolamento e edição.
- Captura final dedicada: **18 estados oficiais**, rodapé em 320×480 e texto ampliado 200%, aprovados e conferidos visualmente.

Cobertura adicional: seis áreas expondo os 23 IDs; grupos com 2/3/6 especialidades; seis larguras de 320 a 1440 px e claro/escuro; foco após seleção e transições; busca vazia e sem resultados; lista completa; teclado e radios; seleções rápidas e movimento reduzido; rodapé em 320×480; texto ampliado 200%; edição mobile; revisão retroativa; ofertas mistas, serviços e categorias preservados; cancelamento, confirmação, falha de armazenamento e isolamento por usuário/workspace/sessão.

Achados corrigidos durante a rodada:

- A primeira proteção das ofertas considerava uma etapa vazia revisitada como uma escolha concluída. O teste de ida/volta detectou a falha; a marcação agora exige uma oferta válida ou uma decisão explícita.
- A regressão antiga de personalização pressupunha apagar produtos ao trocar a profissão. O teste agora preserva a escolha anterior e só espera um perfil de serviços depois da alteração explícita feita pelo usuário.
- A revisão visual detectou “Continuar” cortado dentro do botão em 320 px com texto ampliado, embora não houvesse overflow da página. O rodapé agora permite quebra de linha entre ações, e o teste verifica também o conteúdo interno dos botões.

Capturas e testes usam Chromium local. Texto ampliado por estilos não equivale a certificar zoom nativo, leitor de tela, todos os navegadores ou dispositivos físicos. Não houve auditoria geral, uso de dados reais ou validação de serviços de produção. Não há novo backend a homologar nesta mudança.

## Capturas reais dentro do SocialMEI

Páginas completas de `frontend/socialmei-app.html`, viewport de 1000 px de altura, mesmo nome fictício. “Antes” remete à captura oficial anterior já registrada; “Depois” é o frontend integrado nesta branch. Não são imagens compostas nem capturas de um iframe.

| Largura | Antes claro                                                                              | Depois claro                                                       | Antes escuro                                                                            | Depois escuro                                                     |
| ------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| 1440    | [Abrir](../experimental/onboarding-v3/screenshots/business-layout/before-1440-light.png) | [Abrir](onboarding-business-native/business-beauty-1440-light.png) | [Abrir](../experimental/onboarding-v3/screenshots/business-layout/before-1440-dark.png) | [Abrir](onboarding-business-native/business-beauty-1440-dark.png) |
| 768     | [Abrir](../experimental/onboarding-v3/screenshots/business-layout/before-768-light.png)  | [Abrir](onboarding-business-native/business-beauty-768-light.png)  | [Abrir](../experimental/onboarding-v3/screenshots/business-layout/before-768-dark.png)  | [Abrir](onboarding-business-native/business-beauty-768-dark.png)  |
| 390     | [Abrir](../experimental/onboarding-v3/screenshots/business-layout/before-390-light.png)  | [Abrir](onboarding-business-native/business-beauty-390-light.png)  | [Abrir](../experimental/onboarding-v3/screenshots/business-layout/before-390-dark.png)  | [Abrir](onboarding-business-native/business-beauty-390-dark.png)  |

Também há capturas de duas e três especialidades para cada largura/tema. Rodapé: [320 px](onboarding-business-native/footer-320-dark.png), [texto ampliado](onboarding-business-native/footer-text-200-320-dark.png). Edição mobile: [tela completa](onboarding-business-native/business-editor-390-dark.png), [ações do rodapé](onboarding-business-native/business-editor-footer-390-dark.png). [Busca sem resultados](onboarding-business-native/business-empty-390-dark.png).

## Abrir a branch localmente

Na pasta do repositório atualizado, execute `py -m http.server 5500 --bind 127.0.0.1` no Windows ou `python3 -m http.server 5500 --bind 127.0.0.1` no Linux. Abra `http://127.0.0.1:5500/frontend/socialmei-app.html`.

Use o cadastro local existente ou **Configurações → Perfil e ferramentas → Editar** para um perfil já configurado. A integração está somente na branch de desenvolvimento; o endereço de produção continua com a versão publicada anteriormente.

Execução direta, sem agentes. Aplicada a regra de `prototype-first` do repositório, com aprovação visual explícita antes desta integração. Publicação depende de autorização específica do usuário.
