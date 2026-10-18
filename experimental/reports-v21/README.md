# Relatórios V2.1 — prévia para aprovação

> Registro do protótipo aprovado. A integração na navegação oficial está descrita
> em [Relatórios V2.1 nativos](../../docs/REPORTS-V21-NATIVE.md).
> Os limites de memória/sandbox abaixo pertencem somente a esta prévia.

Base inicial e `main` remota conferida: `a045b157b8ea65230c2f2b9e0a90b8e819a14375`.
Branch experimental: `feat/reports-v21-prototype`. Nenhuma alteração em `frontend/`,
autenticação, contratos, cálculos, infraestrutura ou produção.

## Abrir

Na raiz do repositório: `py -m http.server 5500 --bind 127.0.0.1` no Windows,
ou `python3 -m http.server 5500 --bind 127.0.0.1` no Linux/macOS.
Abra `http://127.0.0.1:5500/experimental/reports-v21/`.

O botão **Comparar V2** mostra a apresentação nativa com o mesmo exemplo fictício,
no mesmo enquadramento da prévia. Não é uma captura de uma conta real.
O shell foi reduzido à área de Relatórios para esta avaliação; não é uma proposta
de substituir a navegação oficial.

Versão portátil autocontida:
`node experimental/reports-v21/build-preview.cjs caminho/Relatorios-V2.1.html`.
Inclui os recursos locais, sem CDN, dependências ou chamadas de API. O navegador
gerenciado bloqueia `file://`: o artefato foi validado via HTTP local com todas
as requisições adicionais bloqueadas. A abertura direta por arquivo permanece
uma verificação no navegador do avaliador.

## Diagnóstico e proposta

A V2 já oferece contadores contínuos, desenho de linhas, barras animadas,
indicador de período, cinco visões, comparação, datas personalizadas, tooltips
com teclado, tabelas alternativas, modais com foco/inert/Escape, CSV seguro,
impressão/PDF, snapshots imutáveis e histórico por escopo. Não foram recriados.

O HTML anexado, `Relatórios MEI (1).html`, foi lido integralmente. Sua organização
de indicadores, filtros e histórico é útil. Sua paleta verde/laranja, números
aleatórios, esperas artificiais e cadeia demonstrativa n8n/Pandas/Drive/WhatsApp
não foram transportados. Não existem essas integrações nesta prévia.

A proposta reduz contornos repetitivos, destaca faturamento, diferencia gráfico,
situação e observações, oferece cinco abas visíveis e recolhe opções secundárias.
Rótulos e textos auxiliares da proposta têm piso de 12 px. Na QA foram corrigidos
corte monetário em 320 px, alvo estreito de aba em tablet, alinhamento dos KPIs
e quebra indevida dos valores na tabela do modal.

## Referências efetivamente consultadas

- [Linear Dashboards](https://linear.app/docs/dashboards): combinar gráficos,
  métricas e tabelas com aprofundamento progressivo.
- [Shopify Analytics](https://help.shopify.com/en/manual/reports-and-analytics/shopify-reports/overview-dashboard):
  período/comparação e hierarquia de leitura. Não adotamos metas ou conversão.
- [Stripe reporting](https://docs.stripe.com/stripe-reports): distinguir definições,
  filtros e exportação dos registros que sustentam o resultado.
- Mobbin retornou somente acesso/cadastro; o endereço consultado de Framer ficou
  indisponível. Não alegamos pesquisa visual de telas autenticadas ou animações.

## O que funciona

São usados HTML/CSS/scripts nativos, sem cópia do motor financeiro. `preview.js`
carrega o documento oficial, substitui somente a configuração por fontes locais,
instala o sandbox antes dos scripts e aplica os adaptadores desta pasta.
`experience.js` muda a apresentação e acrescenta interpolação das linhas a partir
da geometria efetivamente exibida (460 ms), entrada de modal (220 ms), abertura
discreta de detalhes (180 ms) e cancelamento entre operações reais de geração.
Contadores nativos (680 ms), primeira entrada das linhas, barras e seus estados
continuam reutilizados. Tema não reinicia os gráficos. Movimento reduzido não anima.

Há 180 dias determinísticos do **Ateliê Aurora fictício**, com produtos e serviços,
pagos/pendentes/cancelados e uma venda excluída para validar sua desconsideração.
Faturamento e receitas financeiras não são somados. Não há mensagens fictícias
interpretadas como atendimentos nem probabilidades de conversão.

O seletor permite exemplo, vazio, falha de fonte e carregamento. Os dois últimos
são estados explicitamente simulados, sem requisições. A geração captura,
valida CSV e guarda a cópia, sem temporização artificial ou servidor. CSV é um
arquivo real do snapshot. **PDF é Imprimir / salvar PDF**, usando a mesma cópia.
Histórico, busca, situação, detalhes e reexportação usam as funções nativas.

**Somente nesta prévia**, armazenamento é substituído por memória independente:
não lê/escreve dados do usuário, e recarregar elimina exemplos e histórico.
Fetch, XHR, WebSocket, EventSource e Beacon de negócio são bloqueados. A persistência
oficial por usuário/workspace permanece intacta e foi exercitada pela suíte V2.

## Verificação reproduzível

- `npm test`: lógica existente e testes adicionais do sandbox.
- `CHROMIUM_EXECUTABLE=/usr/bin/chromium node tests/reports-v2-browser.cjs`:
  regressão nativa, dados/API interceptados, 12 layouts, CSV/PDF, falhas e isolamento.
- `node tests/reports-v21-browser.cjs`: dez layouts em 320/390/768/1024/1440,
  claro/escuro, cinco visões, filtros concorrentes e personalizados, teclado/foco,
  CSV/PDF, cancelamento, erros, snapshots, memória isolada, movimento reduzido,
  contraste de textos/ações e CPU limitada a 4×. Sem chamadas de produção.
- `npm run format:check` e Prettier também aplicado à pasta experimental.
- `git diff --exit-code a045b157 -- frontend`: aplicação oficial preservada.

Resultados detalhados e capturas reais ficam em [evidence](evidence/).
Execução em 18/10/2026: **214 testes Node aprovados**, regressão V2 aprovada nos
12 layouts e **15 grupos de verificações da prévia aprovados** em dez layouts.
Zero erros JavaScript e zero chamadas externas/API. Nas amostras medidas, contraste
mínimo de 4,67:1 no claro e 6,20:1 no escuro. Sob CPU limitada a 4×, três trocas de
período concluíram em 1.050, 912 e 834 ms. Formatação e preservação de `frontend/`
conferidas. Não foi executada a suíte global de todos os módulos, pois nenhuma
fonte oficial foi modificada.
Antes/depois usam as mesmas fixtures e data fixa. As capturas representam estados
estáveis, depois das animações; o movimento deve ser avaliado na prévia interativa.
Os testes são Chromium desktop com emulação de viewport/CPU, não certificação de
dispositivo físico, Safari ou leitor de tela.

## Próximo passo

Aprovação visual do protótipo. Somente depois, integrar os estilos/adaptadores
aprovados aos componentes nativos e repetir regressões de isolamento e módulos.
O sandbox, os exemplos e o modo de comparação não devem ir para contas reais.
Nenhuma integração, PR, merge ou publicação foi feita nesta rodada.

Skills utilizadas: definição de escopo (`brainstorming`) e `prototype-first`.
Zero agentes. Os demais anexos não foram usados como instruções de execução.
