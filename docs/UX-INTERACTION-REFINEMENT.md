# Refinamento de navegação, densidade e ajuda

Base: `main` em `a55f302f5ab13c574a078fbeb5e0e653ad995303`.
Branch: `feat/ux-interaction-refinement`.

## Achados e decisões

- A marca da sidebar era um `div`. Agora é um botão que usa a navegação nativa para Início, com foco visível e sem recarregar a página ou apagar rascunhos.
- Um único cliente ocupava 540 px de uma lista de 1.100 px no desktop. O resultado filtrado determina a composição: um cliente usa duas colunas internas; vários usam uma grade responsiva; nenhum mantém o estado vazio. Não há preenchimento com registros inventados.
- A Home repetia espaços entre abertura, atalhos, conversa e seções inferiores. Foram reduzidos os intervalos e paddings, mantidos os dados, os atalhos e a hierarquia existente.
- Explicações gerais foram reunidas em Ajuda, disponível nas 13 telas nativas, inclusive na Caixa desktop. Os elementos originais de orientação foram movidos, preservando IDs e atualizações; avisos críticos de ações, fonte indisponível e permissões continuam junto da decisão.
- No celular estreito, o título do cabeçalho tem uma linha própria, preservando a leitura, a indicação de demonstração e os alvos de toque, sem aumentar o cabeçalho além de 90 px.
- Em Vendas e Clientes mobile, os intervalos entre resumo, filtros e lista foram reduzidos para manter os primeiros registros acessíveis cedo, inclusive com o cabeçalho legível. O limite de posição do teste existente foi preservado.
- Recolhíveis agora têm separação entre texto e indicador e alvo de pelo menos 44 px. A expansão de altura usa melhoria progressiva CSS e respeita movimento reduzido. O ciclo de foco, Escape, backdrop e animação continua sendo o modal nativo.
- Reanalisar exemplos confirma a conclusão por toast; iniciar/encerrar a demonstração devolve o foco à aba. Não foram criados estados artificiais de processamento.

## Referências verificáveis

Foram consultadas páginas públicas de documentação, sem presumir acesso a produtos autenticados:

| Referência                                                                                                                                   | Padrão aplicado                                                                         |
| -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| [Notion: sidebar](https://www.notion.com/help/navigate-with-the-sidebar)                                                                     | Entrada previsível para Início, ajuda consistente e acesso às ferramentas existentes.   |
| [Linear: display options](https://linear.app/docs/display-options)                                                                           | Ações secundárias discretas e composição proporcional à tarefa, preservando os filtros. |
| [Stripe: ContextView](https://docs.stripe.com/stripe-apps/components/contextview)                                                            | Contexto acessível sem abandonar o trabalho. No SocialMEI, reutiliza o modal existente. |
| [Shopify Polaris: Page](https://shopify.dev/docs/api/app-home/polaris-web-components/structure/page)                                         | Separação entre ação principal e secundárias e larguras adequadas ao conteúdo.          |
| [Intercom: personalização da Inbox](https://www.intercom.com/help/en/articles/7911926-customize-the-inbox-to-suit-you-and-how-you-work-best) | Contexto e seções recolhíveis, sem reconstruir a Caixa nem esconder ações importantes.  |
| [HubSpot: preview de registros](https://knowledge.hubspot.com/records/preview-a-record)                                                      | Detalhes acessíveis a partir da lista, preservando a revisão contextual já existente.   |

[Mobbin](https://mobbin.com/discover/apps/web) expôs apenas catálogo/login. Nenhum fluxo privado foi tratado como referência observada.

## Verificação e limites

- `tests/ux-interaction-browser.cjs`: marca por símbolo/nome/teclado, sidebar independente, rascunho preservado, Ajuda em 260 estados (13 telas × cinco larguras × dois temas × demonstração ligada/desligada), foco/Tab/Escape e abertura rápida.
- Mais 30 composições de Home/Oportunidades com zero, um e vinte registros sintéticos, sem gravações externas. Larguras: 320, 390, 768, 1024 e 1440 px.
- Regressões existentes cobrem onboarding, personalização, Caixa, classificação/revisão, dados locais/remotos, relatórios/exportações, formulários, temas, configurações e movimento reduzido. O novo fluxo integra `npm run test:browser` e o CI.
- Evidências de navegador são internas; não há nova galeria ou vídeo entregue. Validação usa Chromium automatizado. Leitor de tela e aparelhos físicos exigem homologação manual posterior.
- Sem dependências novas, mudanças de autenticação, backend, armazenamento comercial ou infraestrutura. Critério experimental de 24 horas preservado. Sem merge ou deploy.
