# Refinamento visual — segunda rodada

Data: 14/10/2026. Branch: `feat/visual-refinement-round-2`.
Base: `00eecef84375b94d2057c6970071184b4ca54d53` (Configurações, PR #38).

## Escopo

Esta rodada implementa as nove fases do pedido, seguindo `ANALISE-VISUAL.md` e `MAPA-VISUAL.html` entregues na auditoria anterior. Configurações é a referência interna de hierarquia e acabamento. A Home, a sidebar, a autenticação e a landing mantêm a composição aprovada; o rodapé de origem dos dados e a acessibilidade do link de pular para o conteúdo foram corrigidos onde necessário.

O objetivo é mostrar conteúdo útil mais cedo, distinguir ações de informações e reduzir painéis encaixados. HTML, CSS e JavaScript puro continuam sendo a stack. Não há dependência nova, React, mudança de API, migration, workflow, credencial ou configuração de deploy.

O usuário confirmou o visual de Configurações no servidor. Esta revisão verifica código e testes isolados: não inspecionou a imagem atual da AWS e não publica estes refinamentos em produção. GitHub e CI não comprovam o runtime.

Cópia do frontend original criada antes das alterações por `git archive`, SHA256 `cc00e605d06510134bdd643ea053686e8c9332bf8f3774f32bde64d3da2871bd`. É uma cópia de código, sem banco ou arquivos privados.

## Referências

Foram consultadas páginas públicas de [Mobbin](https://mobbin.com/), [tabs no 21st.dev](https://21st.dev/community/components/s/tabs) e o [guia de páginas de configurações](https://mcp.21st.dev/blog/react-settings-page-components). As referências orientam ritmo, tipografia, agrupamento e exposição progressiva. Nenhum asset, texto de produto ou componente React foi copiado.

O MCP 21st não está disponível nesta sessão. A consulta foi às páginas públicas; não foi utilizada a chave exposta anteriormente nem a biblioteca autenticada do Mobbin. A fundação de paleta, temas, tokens, senha e spotlight herdada dos PRs #37/#38 continua no projeto.

## Nove fases

| Fase                    | Antes                                                                                                           | Mudança e resultado                                                                                                                                                                                                                                                                                                 |
| ----------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — Relatórios          | Cinco indicadores com destaque excessivo no primeiro; gráficos e rankings empilhados; vazios repetidos          | Quatro indicadores principais, gráfico de vendas e próximo cuidado. Rankings e movimento financeiro em expansões independentes. Clientes novos permanece na aba Clientes. As cinco visões, tabelas acessíveis, valores, comparação, privacidade e exportações foram preservados.                                    |
| 2 — Resumo              | Gráfico financeiro precedia pendências operacionais                                                             | Cuidados reais e acompanhamento da venda aparecem antes das métricas. Três cuidados ficam visíveis; os seguintes podem ser expandidos. A expansão é preservada durante atualização de dados. Não há indicador estimado ou cálculo novo.                                                                             |
| 3 — Caixa Unificada     | Perfil, campos não preenchidos e conversa tinham tratamento desigual                                            | Header, composer, mensagens e Cliente 360 seguem a mesma linguagem. Dados existentes ficam em primeiro plano; campos não preenchidos podem ser consultados numa expansão. Lista → conversa → detalhes e rascunhos permanecem.                                                                                       |
| 4 — Clientes/Vendas     | Métricas grandes e filtros atrasavam a primeira linha no celular; regras antigas disputavam posições dos campos | Métricas compactas, busca visível, filtros num popover nativo e registros em cartões com campos separados. Desktop mantém tabelas e filtros expostos. Treze regras antigas de layout mobile foram consolidadas; nenhum select ou handler foi duplicado.                                                             |
| 5 — Assistente          | Bordas e paddings encaixados estreitavam o rascunho                                                             | Leitura usa a largura do painel; tom, fontes e ações têm agrupamento claro. A área de texto supera 300px no teste de 390px. Inserir continua acrescentando ao rascunho existente, sem enviar mensagem.                                                                                                              |
| 6 — Automações          | Seis modelos apareciam antes da biblioteca                                                                      | Biblioteca e busca primeiro; fluxo Quando → Faça → Depois preservado. Modelos começam recolhidos nos dois tamanhos e continuam acessíveis por teclado. Criar, editar, histórico, habilitar/pausar e testar continuam locais.                                                                                        |
| 7 — Financeiro/Produtos | Excesso de altura nas métricas financeiras; ação de catálogo dependia do nome/card                              | Saldo continua destacado. Métricas secundárias formam duas colunas no celular; valores longos usam a largura total. Preço, tipo, estoque e ação Abrir do catálogo ficaram mais claros. Não houve redesign destes módulos.                                                                                           |
| 8 — Coerência           | Rodapé e relatórios diziam demonstração local mesmo com CRM remoto; tooltips contradiziam a autenticação        | Avisos distinguem fontes locais, compartilhadas e mistas. API não verificada/em leitura/indisponível não equivale a zero registros: Relatórios sinaliza leitura incompleta e usa “—” nos indicadores sem leitura disponível. Automações e Assistente descrevem simulação/preparação local sem negar a autenticação. |
| 9 — QA                  | Matriz anterior não cobria estes controles e layouts                                                            | Novos fluxos verificam filtros, expansões, ordem, valores longos, fontes de dados, teclado e motion. Matriz de 484 estados e regressão existente executadas. Comparação visual reutiliza a mesma base, dados, data e tamanhos da auditoria.                                                                         |

## Comportamento e dados

Os renderizadores continuam usando `operationalMetrics()`, os stores existentes, vínculos por ID, período e formatos monetários atuais. Busca não altera totais; nenhuma regra financeira foi acrescentada. Saldo de lançamentos pagos continua explicitamente diferente de saldo bancário.

Os quatro stores expõem apenas um getter de apresentação, `connectionState`, e um evento de atualização dos avisos. Não há endpoint, payload, persistência ou fallback novo. Falha de API mantém sua sinalização; não transforma dados remotos em dados locais. O resumo copiado informa a origem e a eventual leitura incompleta.

Vazios de vendas foram agrupados sem esconder lançamentos financeiros independentes. “Nenhum cliente” e “data de cadastro não informada” são situações diferentes. Atendimento continua sem taxa de conversão inventada. Configuração de CRM não comprova conexão de WhatsApp/Instagram; leitura de mensagens continua com estado separado.

## Motion e acessibilidade

- Troca de período/aba: fade e deslocamento de 4px, 210ms pelo sistema existente; apenas elementos do módulo ativo.
- Entrada do rascunho: 240ms. Troca de tom: fade de 180ms. Foram removidos blur e stagger dos botões operacionais.
- Cleanup de `will-change` verificado; nada depende da animação para aparecer. `prefers-reduced-motion` mantém zero animações na matriz.
- Abas de relatório usam tablist/tab/tabpanel, seleção anunciada e setas/Home/End. Foco é preservado após troca e atualização de fonte.
- Filtros mobile usam popover nativo: teclado, Escape, clique externo, botão de concluir e adaptação ao resize. Os controles desktop permanecem os mesmos.
- Expansões nativas funcionam com Enter/Espaço. Contexto da Caixa preserva fechamento e retorno do foco. Modais e drawers existentes continuam testados.
- O link de pular para o conteúdo fica oculto visualmente fora do foco, inclusive no Assistente; permanece acessível por teclado.

Não foram adicionados WebGL, parallax, bibliotecas de animação ou loops contínuos. A escolha de opacity/transform reduz trabalho de layout, mas não comprova 60 FPS em dispositivos reais.

## Validação

| Verificação                  | Evidência                                                                                                                                                         |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Contratos e estrutura Node   | `npm test`: 63 testes; zero falhas/skips                                                                                                                          |
| Formatação                   | `npm run format:check`                                                                                                                                            |
| Regressão de navegador       | `npm run test:browser`: 88 estados e 20 grupos de fluxos, incluindo os quatro grupos novos                                                                        |
| Matriz desta rodada          | 484 estados: 11 módulos × 11 resoluções × claro/escuro × dados locais/API vazia controlada                                                                        |
| Auditoria A01/A02 preservada | 36 estados de Ferramentas e 936 colunas de gráficos, teclado, hover e limites de tooltip                                                                          |
| Fontes e falhas              | Dados locais, remotos, híbridos e resposta 503 controlada; vazio não tratado como ausência de data                                                                |
| Interações                   | CRUD remoto existente, buscas, filtros, cartões/tabelas, exportar CSV, copiar resumo, solicitar impressão, modais, drawers, toasts, backup/importação e rascunhos |
| Motion                       | Período em 210ms, cleanup, foco e reduced motion                                                                                                                  |
| Capturas                     | 88 antes + 88 depois, mais as cinco abas de relatório e Assistente com conversa/rascunho                                                                          |

Resoluções: 1920×1080, 1600×900, 1440×900, 1366×768, 1280×720, 1024×768, 900×900, 768×1024, 430×932, 390×844 e 360×800. Automático/custom e autenticação seguem cobertos pela regressão existente.

A matriz verifica overflow da página e do módulo. A rotação decorativa já aprovada em Configurações pode avançar até 4px dentro da margem da página; essa exceção está explícita no teste, sem afrouxar o limite de overflow global.

As capturas antes/depois usam 1440×1000 e 390×1000, claro/escuro, data congelada em 13/10/2026 e as mesmas fixtures da auditoria. Local significa dados de demonstração; remoto significa APIs controladas vazias, com a identidade de teste da auditoria. Não são capturas autenticadas da produção. O aviso de sincronização em alguns screenshots locais decorre do bloqueio de rede externa do teste.

Falhas de layout encontradas durante a execução foram corrigidas: sobreposição causada por regras antigas das tabelas, ticket do Resumo excedendo a coluna, quebra de valores financeiros e perda de expansão numa atualização. Os testes de geometria e valores monetários foram ampliados para cobrir esses casos. Não há timeout aumentado, teste desativado ou asserção removida para esconder falhas.

## Arquivos e organização

- `frontend/socialmei-app.html`: composição dos módulos e controles, mantendo IDs existentes.
- `frontend/styles/socialmei.css`: seções originais de Relatórios/Resumo/CRM/Assistente/Automações/Financeiro/Catálogo; propriedades duplicadas consolidadas nos seletores alterados. Não foi anexado um bloco de overrides ao fim do arquivo.
- `frontend/scripts/app.js`: relatório, abas, origens e preservação de leitura.
- `frontend/scripts/business-views.js`: prioridades, filtros responsivos, catálogo, valores longos e motion de período.
- `frontend/scripts/inbox.js`, `experience.js`, `inbox-sync.js`, `data-and-backup.js`: composição, feedback, avisos e contagem de filtros.
- `client-store.js`, `product-store.js`, `sale-store.js`, `finance-store.js`: estado de apresentação, sem alteração do contrato da API.
- `tests/reports-browser.cjs`, `browser.cjs` e novos `visual-refinement-browser.cjs`, `data-origin-browser.cjs`, `visual-layout-browser.cjs`, `visual-motion-browser.cjs`: cobertura mantida e ampliada.
- Este relatório substitui as evidências antigas da primeira rodada; a fundação anterior permanece no histórico Git.

## Limites e próxima etapa

O CI do PR executa os jobs `validate` e `browser`; contratos de API/PostgreSQL, gateway protegido e stack/restore isolados são verificados pelo workflow existente. Consulte a execução associada ao SHA do PR, não o resultado de uma versão anterior.

NÃO CONFIRMADOS nesta rodada: runtime/imagem AWS, FPS/CPU/GPU em hardware real, Lighthouse de produção, Safari/Firefox, leitores de tela físicos e integrações reais de n8n/WAHA/Instagram/IA. Não houve deploy, migration, restore, envio de mensagem ou chamada a webhook legado.

O CSS e alguns renderizadores ainda são grandes; a revisão foi pontual. Próximo passo: revisar o comparativo e o PR. Depois da aprovação, a publicação exige uma etapa própria de backup, imagem de rollback e atualização somente do gateway, sem repetir roteiros de publicação antigos.
