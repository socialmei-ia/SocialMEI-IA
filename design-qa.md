# QA visual — Oportunidades e Divulgação

Fonte: duas imagens aprovadas anexadas ao pedido do usuário (Divulgação, 1207 × 900;
Oportunidades, 1210 × 914). Elas definem direção e composição, sem substituir os
contratos funcionais. As referências estão incorporadas à conversa; não foram
adicionadas como arquivos ao repositório.

Implementação: `frontend/socialmei-app.html`, Chromium, navegação oficial;
HTTPS local descartável para acompanhamento comercial e preparação compartilhada.
Capturas: `test-results/visual-opportunities/empty-1440-dark.png`,
`many-390-light.png`, `one-1440-dark.png`, `content-preview-1440-dark.png` e
`test-results/visual-content/{create,drafts,agenda,connections}-390-{light,dark}.png`.

## Comparação

A revisão foi de fidelidade à direção aprovada, não uma comparação pixel a pixel.
As imagens de referência omitem a sidebar, enquanto a aplicação preserva sidebar,
controles adicionais, campos e avisos reais. Capturas CSS em 1440/768/390 com
`deviceScaleFactor: 1`; matriz adicional 320/1024. PNGs completos têm alturas
variáveis conforme a tela. Não se comparou a escala reduzida do visualizador como
se fossem pixels CSS equivalentes.

- Tipografia: Inter oficial, hierarquia compacta de título, seção e controles;
  rótulos legíveis, sem introduzir fontes externas. Textos não são substituídos
  pelos termos de IA/publicação que a implementação não suporta.
- Ritmo: hero com arte lateral no desktop, formulário coeso, filtros abaixo do
  título da fila, painel vazio completo; no celular, arte omitida e campos empilhados.
- Cores: tokens oficiais claro/escuro, superfícies discretas e seleção azul;
  capturas após aplicação de tema e quadros de renderização, com movimento reduzido
  para evitar registrar cores intermediárias.
- Imagens: PNG decorativo transparente gerado, sem informações pessoais, sem logos
  inventados e sem elementos críticos desenhados por CSS. Ícones de interface
  reutilizam `renderIcon`; mídia do usuário mantém as proporções 4:5 e 9:16.
- Conteúdo: comercial persistido separado da análise heurística; conteúdo, agenda
  e conexão mantêm indicações explícitas de local/simulado/não conectado.

## Histórico de correções

1. P1: filtros mobile herdavam `position:absolute` e cobriam o hero.
   Corrigido com escopo comercial `position:static; inset:auto`; teste geométrico
   exige filtros abaixo do título em cinco larguras/dois temas. Recaptura mobile conferida.
2. P2: vazio comercial estreito herdava centralização da pilha.
   Corrigido com largura integral e margens locais; recaptura desktop conferida.
3. P2: ação remota aparecia desabilitada no modo local após mover para o hero.
   Corrigido ocultando ação e explicação comercial nesse modo; regressão local
   preserva a lista demonstrativa acima da dobra sem relaxar seus limites.
4. P2: primeiras capturas misturavam cores durante a transição de tema.
   Recapturadas com tema confirmado e renderização estabilizada.

Revisão independente abriu as quatro abas de Divulgação em desktop/mobile e dois
temas, e Oportunidades com zero, uma e três oportunidades. Nenhum P0/P1/P2 restante
identificado no escopo examinado. A inspeção de detalhes incluiu formulário,
filtros/contadores, foco, frames e avisos; não se limitou à visão geral.

5. P2: menu de opções local ficava sob as abas por causa do stacking context do hero.
   Corrigido com camada explícita no header; a regressão premium exercitou novamente
   abertura do menu e clique real em Reanalisar exemplos, sem force/click por script.

## Verificações e limites

Prévia HTTPS: autenticação, CSRF, dois negócios, persistência, recarga, conflitos,
encerramento/reabertura/histórico e simulação. Matriz visual, teclado, movimento
reduzido, ausência de erros JavaScript e reflow equivalente a 200% exercitados.
Regressões completas e CI: resultados finais na PR, sem afirmar antecipadamente
aprovação dos checks ainda em andamento.

P3 opcional: ícones Story/Feed/Reel podem futuramente ganhar símbolos mais
específicos; os rótulos permanecem explícitos. Não foi feita avaliação com leitores
de tela físicos nem medição de desempenho em hardware móvel modesto.

final result: passed
