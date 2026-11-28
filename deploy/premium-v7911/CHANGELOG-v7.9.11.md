# v7.9.11 — Evolução criativa (visual + código; somente frontend)

## Visual
- Cliente 360° no celular: a lista abre primeiro (nenhum cliente é selecionado nem há rolagem automática); o painel abre ao toque, com botão "Voltar à lista de clientes"; o botão flutuante "Novo cliente" some com o painel aberto. Na lista, até 700 px ficam só nome e total (e-mail, última compra e seta ocultos); o selo "Melhor cliente" vai para baixo do nome.
- Caixa no celular — DECISÃO: filtros de situação em quebra de linha (sem rolagem). Motivo: o histórico oscilou entre rolável e duas linhas; só a quebra de linha nunca corta um rótulo (em 390 px os cinco ficam visíveis). O vazio acima dos filtros caiu de ~44 px para ~28 px.
- Oportunidades (celular e desktop): os 4 cartões de resumo, que repetiam o funil e o "Retomar hoje", foram trocados por uma linha de texto ("N negociação(ões) pede(m) retorno hoje. R$ X em negociação."); os elementos seguem no HTML, ocultos, e continuam sendo atualizados. No celular, ao trocar para Quadro/Semana os controles sobem ao topo.
- Oportunidades: tocar numa ficha do Quadro abre a oportunidade na lista já expandida (corrigido: não expandia) e o clique fantasma que a recolhia foi bloqueado; o nível de interesse pode então ser mudado por toque, sem arrastar.

## Código
- scripts/v22-native.js: o código nativo (212 KB, antes um <script type="text/plain"> no HTML) virou arquivo próprio; node --check passa. v22-bootstrap.js o lê de forma síncrona e o executa no mesmo ponto de antes (uma carga assíncrona atrasava a base e quebrava v74-automacoes.js, que espera o DOMContentLoaded).
- styles/app-base.css: o <style> de 77 KB do HTML virou arquivo, na mesma posição da cascata (o caminho da fonte passou a ../assets/). socialmei-app.html caiu de 293 KB para ~3 KB.
- Remendo de DOM unificado (1 caso): comparação com período anterior e "Como ler" de Relatórios agora são gerados em v22-native.js (rpHow, repCompare); removido enhanceReport de v75-gestao.js. Pequena diferença intencional: o parágrafo de comparação vazio deixa de ocupar ~8 px.
- tools/teste-regressao.cjs: teste automatizado (14 rotas × claro/escuro × 1440/390 px; falha por erro de console, overflow horizontal ou contagens de "aguardando resposta" divergentes entre barra lateral, Início e Caixa). Como rodar (Windows): npm install --no-save playwright; npx playwright install chromium; node tools\teste-regressao.cjs
- window.SocialMEIVersion = "7.9.11".

## Não feito (ver relatório)
- Redução de !important (meta -30%): tentada por comparação de pixels e não alcançada; nenhuma remoção aplicada.
- Demais remendos de DOM (v75-gestao, v76-experiencia, v76-negocios, v782/v791-inicio, v64-caixa, v65-shell etc.) só inventariados.
- Padronização das marcas de versão nos scripts.
