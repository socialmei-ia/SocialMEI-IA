# Onboarding V3 integrado — PR #57

> Atualização posterior: a composição vertical da etapa Negócio está documentada em [ONBOARDING-BUSINESS-NATIVE.md](ONBOARDING-BUSINESS-NATIVE.md), com capturas e regressões próprias. O restante deste guia registra a integração anterior da PR #57.

Integração autorizada explicitamente após apresentação do protótipo `experimental/onboarding-v3/`. Mesma branch `feat/socialmei-native-integration`, base inicial **b03342bb0b2023956f24aab75836c030d34ef52c**, árvore inicialmente limpa e HEAD remoto idêntico. CI inicial: **Repository checks #258, success** (em execução no início, sucesso confirmado durante a rodada).

## Abrir dentro da aplicação oficial

Na raiz, execute `python3 -m http.server 5500 --bind 127.0.0.1` (Windows: `py -m http.server 5500 --bind 127.0.0.1`). Abra **http://127.0.0.1:5500/frontend/socialmei-app.html**.

- Sem sessão: use o cadastro local existente, com dados fictícios. Ele conduz às seis etapas.
- Perfil já configurado: **Configurações → Perfil e ferramentas → Editar**. A edição começa em Negócio; os dados de identidade não são editados nesse fluxo.
- Contas autenticadas usam o fluxo existente. Os testes de conta remota interceptam APIs com fixtures sintéticas; não acessam produção.

O V3 está no onboarding oficial, sem iframe, importação do controlador do protótipo ou segunda implementação ativa. O protótipo permanece como referência histórica.

## Integração e preservação

| Arquivo                                  | Alteração                                                                                                                                                                                           |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/socialmei-app.html`            | Composição editorial, cabeçalhos, feedback ligado aos campos, detalhes opcionais recolhidos, descoberta em colunas, prévia movida para Ferramentas e rodapé de ações acessível                      |
| `frontend/styles/business-profile.css`   | Consolidado o estilo de onboarding no lugar de sucessivas sobreposições; tokens oficiais, claro/escuro, estados de foco/seleção e reflow. Estilos de Home/catálogo e diálogo de contato preservados |
| `frontend/scripts/experience.js`         | Controlador existente adaptado: edição com retorno direto, resumo atualizado, sugestões explícitas, guardas de navegação, validação e movimento. Sem alterar autenticação ou armazenamento          |
| `tests/adaptive-onboarding-browser.cjs`  | Regressões do fluxo e dos achados da revisão, seis larguras, dois temas, teclado, movimento, texto ampliado e geometria                                                                             |
| Este guia e `docs/onboarding-v3-native/` | Evidências de avaliação e limites                                                                                                                                                                   |

Mantidos os seis passos, seis grupos, 23 especialidades, todos os IDs anteriores, catálogo extensível, busca e seleção progressiva, ofertas mistas, nove capacidades condicionais, canais/prioridade, edição/cancelamento e revisão final. Nome do workspace remoto continua indisponível para alteração pelo onboarding; identidade autenticada permanece somente leitura.

`business-profile.js`, stores, autenticação, chaves e contratos não foram modificados. O perfil comercial continua sendo salvo **somente após confirmar a revisão**, no repositório existente, com escopo esperado de usuário/workspace. Falha de armazenamento mantém respostas e apresenta erro. Cancelar não grava o rascunho. Perfil permanece **local neste navegador, inclusive em conta autenticada**, sem sincronização entre dispositivos.

## Experiência resultante

- **Você:** introdução e formulário em composição editorial, feedback contextual e dados do cadastro reutilizados.
- **Negócio:** ícones SVG consistentes, seis áreas, busca e especialidades progressivas, seleção explicitamente resumida. Cidade, Instagram e CNPJ continuam acessíveis em detalhes opcionais; um campo inválido abre os detalhes antes de receber foco.
- **Ofertas:** grupos de serviços/produtos, seleção múltipla, inclusão por botão ou Enter. Texto pendente também é considerado ao continuar; limite de 30 impede descarte silencioso, inclusive entre os dois grupos de negócio misto.
- **Rotina:** escolhas agrupadas em Atendimentos, Pedidos e entregas e Estrutura, preservando todas as capacidades existentes.
- **Ferramentas:** sugestões iniciais apenas de recursos disponíveis, sem selecionar interesses futuros automaticamente. Preferências salvas anteriormente são preservadas. Recursos futuros têm grupo próprio, com aviso explícito; marcar interesse não libera um módulo. A prévia usa apenas ferramentas disponíveis. No celular, opções vêm antes da prévia.
- **Revisão:** identidade, negócio e escolhas atualizados ao voltar diretamente de uma edição. Campos obrigatórios são revalidados nesse caminho. Pular uma etapa opcional preserva escolhas já preenchidas; não apaga respostas.

Não são criados produtos, serviços, preços, estoque, clientes, vendas ou conexões. O restante da aplicação mantém os módulos e a navegação existentes.

## Movimento, teclado e desempenho

O helper oficial `SocialMEIMotion` é reutilizado, sem biblioteca nova. Saída de **160 ms**, entrada de **180 ms**, deslocamento de **8 px** e progresso CSS de **320 ms**. Mudança de área revela especialidades uma vez; digitar busca não repete essa animação. A preferência de movimento reduzido elimina efeitos.

Durante a transição, painel fica inerte e controles de navegação desabilitados; cliques rápidos não disparam duas etapas. O foco vai para o título após a entrada. Etapas futuras continuam bloqueadas, anteriores aceitam teclado/mouse/toque. Enter em texto avança; no campo de inclusão adiciona a opção. Tab/Shift+Tab e Space conservam controles nativos.

O rodapé acompanha sua altura real por `ResizeObserver`, inclusive texto ampliado e mensagens, reservando espaço para os campos finais. Não há loop de animação permanente, animação de layout nem alteração de stores para efeitos visuais. `transition-sample.json` contém uma amostra local incluindo resize; ela **não é medição de FPS nem garantia de desempenho em aparelhos físicos**.

## QA e revisão independente

**Resultados finais:** `npm test` — **211 passaram**; `npm run format:check` — **passou**; `CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser` — **88 estados e 25 fluxos passaram**, com zero erros JavaScript no resumo. QA focado final — **108 estados de layout e seis cadastros passaram**. `git diff --check` também passou. O relatório completo de navegador está em [browser-summary.json](onboarding-v3-native/browser-summary.json). Comandos reproduzíveis:

```sh
npm test
npm run format:check
CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser
```

O teste focado `CHROMIUM_EXECUTABLE=/usr/bin/chromium node tests/adaptive-onboarding-browser.cjs` cobre **seis cadastros** (barbearia, salão, assistência de celulares, perfumaria, costura e negócio misto), edição/cancelamento, opcionais, quota, recuperação, troca de usuário/workspace e sessões ausente/indisponível. As APIs são interceptadas e não recebem escritas de perfil. São **108 estados de layout** em 320/360/390/768/1024/1440 px nos dois temas, incluindo telas relacionadas. Capturas principais são de viewport, sem montagem artificial.

Incluídos: CTA visível, último campo alcançável, busca vazia, CNPJ inválido em detalhes fechados, retorno direto, foco, cliques repetidos, resize durante movimento, texto ampliado a 200% por estilos de QA em 320 px, limite de escolhas e pendentes nos dois grupos. O teste de ampliação é uma prova de reflow de texto; não substitui teste manual de zoom e leitor de tela em dispositivos físicos.

Um revisor independente examinou o diff e as seis etapas em desktop/mobile/claro/escuro. Seu parecer inicial foi **CONDITIONAL PASS** por dois problemas P2: cabeçalho obsoleto ao retornar de edição e texto pendente acima do limite. Ambos tiveram regressões que falharam antes da correção e passaram depois; o caso misto recebeu cobertura adicional. Não foram acionados agentes redundantes. Não há alegação de certificação WCAG completa ou auditoria de segurança.

## Evidências e comparação

As imagens “antes” foram capturadas no HEAD inicial desta rodada, antes de editar o frontend; são de página inteira. As imagens “depois” mostram o viewport real: o conteúdo abaixo da dobra continua disponível por rolagem. Não devem ser comparadas como diff de pixels em dimensões idênticas.

| Etapa       | Antes mobile claro                                          | Depois mobile claro                                        | Depois mobile escuro                                      | Depois desktop claro                                        | Depois desktop escuro                                      |
| ----------- | ----------------------------------------------------------- | ---------------------------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------- |
| Você        | —                                                           | [Abrir](onboarding-v3-native/after/you-390-light.png)      | [Abrir](onboarding-v3-native/after/you-390-dark.png)      | [Abrir](onboarding-v3-native/after/you-1440-light.png)      | [Abrir](onboarding-v3-native/after/you-1440-dark.png)      |
| Negócio     | [Abrir](onboarding-v3-native/before/business-390-light.png) | [Abrir](onboarding-v3-native/after/business-390-light.png) | [Abrir](onboarding-v3-native/after/business-390-dark.png) | [Abrir](onboarding-v3-native/after/business-1440-light.png) | [Abrir](onboarding-v3-native/after/business-1440-dark.png) |
| Ofertas     | —                                                           | [Abrir](onboarding-v3-native/after/offers-390-light.png)   | [Abrir](onboarding-v3-native/after/offers-390-dark.png)   | [Abrir](onboarding-v3-native/after/offers-1440-light.png)   | [Abrir](onboarding-v3-native/after/offers-1440-dark.png)   |
| Rotina      | —                                                           | [Abrir](onboarding-v3-native/after/routine-390-light.png)  | [Abrir](onboarding-v3-native/after/routine-390-dark.png)  | [Abrir](onboarding-v3-native/after/routine-1440-light.png)  | [Abrir](onboarding-v3-native/after/routine-1440-dark.png)  |
| Ferramentas | [Abrir](onboarding-v3-native/before/tools-390-light.png)    | [Abrir](onboarding-v3-native/after/tools-390-light.png)    | [Abrir](onboarding-v3-native/after/tools-390-dark.png)    | [Abrir](onboarding-v3-native/after/tools-1440-light.png)    | [Abrir](onboarding-v3-native/after/tools-1440-dark.png)    |
| Revisão     | [Abrir](onboarding-v3-native/before/review-390-light.png)   | [Abrir](onboarding-v3-native/after/review-390-light.png)   | [Abrir](onboarding-v3-native/after/review-390-dark.png)   | [Abrir](onboarding-v3-native/after/review-1440-light.png)   | [Abrir](onboarding-v3-native/after/review-1440-dark.png)   |

[Texto ampliado em 320 px](onboarding-v3-native/after/text-200-320-dark.png). Os exemplos são sintéticos; o frontend mostrado é `frontend/socialmei-app.html`.

## Limites e próximos passos

Permanecem as limitações conhecidas de persistência local do perfil. Nenhum contrato remoto novo, endpoint legado, autenticação sensível ou infraestrutura foi alterado. Sem merge, deploy ou mudanças em AWS, banco, n8n, WAHA ou credenciais.

A próxima etapa é avaliação humana do onboarding integrado e homologação em dispositivos reais/tecnologias assistivas. PR #57 deve permanecer aberta em Draft até decisão específica do responsável.
