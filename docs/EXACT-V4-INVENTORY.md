# Divulgação V4 — inventário antes da substituição

Golden master imutável: `frontend/reference/Divulgacao-V4-original.html`.
A adaptação anterior renderizava outro estúdio e dois refinadores concorrentes.

| Seção/estado/interação original                                              | Equivalente integrado                                | Contrato/decisão                                                         |
| ---------------------------------------------------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------ |
| Header, sessão, tema, progresso, hero/palavras, ideia diária                 | DOM/CSS original escopado; perfil e tema oficiais    | Sem cadastro ou tema paralelo; substituição de texto requer confirmação  |
| Dock Criar/Rascunhos/Agenda/Conexões, indicador, teclas 1–4/setas            | Abas oficiais `contentWorkspace-*`                   | Um controlador de navegação, ocultação com teclado mobile                |
| Telefone à esquerda, campos à direita e accordion numerado                   | DOM original com IDs nativos preservados             | Nenhum iframe; reflow e animações extraídos                              |
| Story/Feed/Reel, overlays editáveis, CTA/hashtags                            | `SocialMEIContentStudio` + binder visual V4          | Editor único; texto literal seguro, formato e validação oficiais         |
| Sugestões tema/produto/objetivo/tom e aplicar                                | Regras locais explicitamente identificadas           | Sem IA externa, promoções não são fatos conhecidos; revisão necessária   |
| Imagem/vídeo, soltar, zoom/arrastar/setas, alt, safe, Feed claro, fullscreen | Validação de mídia nativa + apresentação V4          | Mídia somente sessão; não há upload real; URLs revogadas                 |
| Salvar/novo/editar/duplicar/excluir, confirmação, feedback                   | Repositório `SocialMEIContentDrafts` por identidade  | Escrita confirmada antes de sucesso; limite40; exclusão confirmada       |
| Busca/formato/ordem/miniaturas                                               | Biblioteca nativa renderizada em DOM V4              | Somente registros do escopo atual; sem coleção paralela                  |
| Backup V4 e JSON nativo                                                      | `repository.importMany`, validação antes de escrita  | IDs/escopo importados não confiados; mídia bruta não importada/exportada |
| Agenda 14 dias, seleção/horários/filtros/editar/cancelar                     | `SocialMEIContentPreparation` autenticado            | Preserva revisão, idempotência, CAS, papel e workspace; só simulação     |
| Simular3publicações da semana                                                | Controle original desabilitado com motivo            | API atual não oferece transação de lote revisada; não contornar revisão  |
| Instagram/WhatsApp/Facebook, nome/bio                                        | Preparação pública existente e perfil oficial        | Nunca conectado; nome autenticado não sobrescrito por cadastro paralelo  |
| Ctrl+S, Escape, foco, toque, reduced motion                                  | Binder V4 + modais oficiais                          | Sem atalhos fora da aba; sem eventos duplicados                          |
| Recursos anteriores extras                                                   | Details de preparação compartilhada/piloto/simulação | Permanecem funcionais e desabilitados por padrão conforme flags oficiais |

Sem novos endpoints, migrations, providers ou armazenamento remoto. Detalhes locais
adicionais, se persistidos, pertencem ao próprio rascunho validado por escopo.

## Integração e exceções verificáveis

- A composição, ícones e CSS foram extraídos do golden master. Classes permanecem
  sob `#contentStudioView #exactV4-root`. O reset estritamente local neutraliza a
  adaptação anterior; não afeta outras abas nem atributos geométricos SVG.
- `vw` e breakpoints de composição usam a largura efetiva do miolo por
  `ResizeObserver`/variável CSS, preservando as dimensões originais dentro da
  sidebar. Não há `container-type`, para manter dock e tela cheia fixos à viewport.
- A segunda barra foi retirada: tema, indicador e progresso originais usam um
  portal temporário na topbar oficial. Ajuda, Ferramentas, sessão e navegação
  continuam os oficiais; os nós voltam ao módulo ao sair de Divulgação.
- Texto, mídia e confirmação continuam no editor e repositório oficiais. Tema,
  produto, objetivo, tom, alt e geometria são apresentação opcional do mesmo
  rascunho local. O trabalho em andamento usa o mesmo envelope por identidade;
  não é um registro compartilhado nem uma publicação. IDs antigos e campos
  obrigatórios dos rascunhos continuam válidos.
- Miniaturas JPEG de até200px/40000caracteres pertencem ao rascunho local. Imagem
  original/vídeo/blob/URL de sessão nunca são persistidos. Backups excluem as
  miniaturas e importações descartam imagens, URLs, IDs e escopos fornecidos.
- O calendário lê preparações reais da API existente. Agendar/reagendar abre o
  fluxo autenticado de revisão com versão/idempotência; não grava um agendamento
  local fingindo ser remoto. Cancelamento e histórico mantêm o mesmo backend.
- Simular3publicações permanece desabilitado: falta transação de lote revisada.
  WhatsApp/Facebook não possuem contrato de preparação equivalente; permanecem
  desabilitados com motivo. Instagram usa a preparação pública existente.
- Nome do negócio vem do perfil/identidade oficiais, sem cadastro paralelo. Bio
  sem campo suportado permanece vazia/somente leitura. Editar leva a Configurações.
- Os modelos originais de texto V4 são locais e requerem revisão humana; não
  comprovam promoções, qualidade, estoque, preço ou disponibilidade. Não há
  publicação externa, upload, IA paga ou conexão real.

## Evidências focadas

- `tests/exact-v4-browser.cjs`: criação/edição literal na prévia, sugestões, mídia,
  zoom/setas/área segura, CRUD, miniatura, backup original/nativo, agenda14dias,
  recuperação do editor, isolamento local e estados honestos sem backend.
- Capturas originais/integradas e canvas normalizado em
  `test-results/exact-v8-v4/divulgacao-*.png`,1440/390/320 claro/escuro.
- Compara também tokens, largura/raio do telefone e raio do formato contra o HTML
  original na mesma largura disponível, além das capturas de página completa.
- Modelos locais:15testes focados inicialmente aprovados, incluindo regressão
  vermelha/verde de apresentação/recuperação no mesmo repositório e recusa de
  thumbnails executáveis/geometria inválida/IDs de outro escopo.

## Ajustes mínimos exigidos pela integração

- Cabeçalho do telefone usa classe `v4-phone-header` para não colidir com `.hd` do
  cabeçalho oficial. O estilo extraído permanece equivalente.
- No celular, o seletor de tema oficial em Ferramentas evita um segundo botão na
  topbar; sessão/progresso continuam associados à mesma aba. Não há terceira linha
  de cabeçalho em320px.
- Dock tem alvo mínimo44px (até2px adicionais nas variantes menores do original).
  ResizeObserver acompanha os botões para que o indicador cubra a opção inteira
  após fontes, sidebar e breakpoints alterarem sua largura.
- Setas/Home/End mantêm a etapa de formato aberta; clique por mouse/toque conserva
  o avanço progressivo original. Isto evita perda de foco por recolhimento imediato.
