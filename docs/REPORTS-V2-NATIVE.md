# Relatórios V2 na aplicação oficial — Etapa 4

Branch `feat/socialmei-native-integration`, PR #57 (Draft). Acesso: abrir
`frontend/socialmei-app.html` e selecionar **Relatórios** na navegação original.
Não há página independente, iframe, novo backend ou acesso a produção.

## Integração

A referência V2 foi lida integralmente. Foram reaproveitados a organização dos
indicadores, o painel de evolução/situação, barras, observações, filtros com
indicador deslizante, geração em modal e histórico. CSS e comportamento ficam
nos arquivos próprios `reports-v2.css`, `report-ui.js` e `report-data.js`, com
seletores limitados à aba/modal. A sidebar, temas e infraestrutura nativa de
modais permanecem. A base sintética de 180 dias, o histórico pré-carregado e a
chave global do protótipo não foram incorporados.

Os cálculos `operationalMetrics`, os períodos (inclusive personalizado), as cinco
visões Resumo/Vendas/Clientes/Atendimento/Financeiro, detalhes em tabelas, opção de
ocultar valores e copiar resumo foram preservados. Registros excluídos agora são
ignorados também nos totais e séries, com teste de regressão.

## Definições e limites dos dados

- Faturamento e ticket usam somente vendas **pagas** e datadas no período.
  Canceladas, rascunhos, pendentes e excluídas não entram no faturamento.
- Receitas/despesas são lançamentos **pagos**, agrupados pelo vencimento conforme
  o contrato atual. Saldo = receitas menos despesas; não é saldo bancário.
  Esses lançamentos não são somados ao faturamento de vendas.
- Situação de venda não equivale a entrega. Conversa não equivale a atendimento
  concluído. Não há taxa de conversão, probabilidade, entregas ou agendamentos
  inferidos.
- Barras de itens exigem ID de catálogo compatível, quantidade positiva informada
  e fontes de catálogo/vendas no mesmo modo. Nomes livres continuam nos detalhes,
  com ressalva; quantidade ausente aparece como “Não informada”. Produtos e
  serviços permanecem distintos. O perfil existente contextualiza o texto e a
  ordem das sugestões de leitura, sem criar métricas nem outra fonte de perfil.
- Fontes não disponíveis apresentam indisponibilidade e bloqueiam relatórios que
  dependam delas. Uma conta vazia mostra zero/estados vazios, sem amostra da V2.
  Exemplos já existentes só aparecem no modo demonstrativo local identificado.
- A comparação usa a mesma fonte/definição e janela anterior adjacente de igual
  duração. Sem um registro válido na fonte datado no início da janela anterior
  ou antes, a porcentagem fica indisponível. Base zero também não gera percentual.
  Essa verificação é conservadora: o contrato atual não comprova completude do
  histórico remoto. Valores anteriores encontrados não garantem cobertura total.

## Interações e acessibilidade

Contadores de 680 ms partem do valor efetivamente exibido, inclusive em troca
rápida de período. Durante a transição há indicação acessível de atualização;
linhas (740 ms), barras (690 ms) e indicador do período (330 ms) só animam quando
seus dados mudam. Não há fade de toda a página nem reinício por mudança de tema.
`prefers-reduced-motion` desativa os movimentos. Pontos do gráfico têm foco,
valores literais, tooltip por mouse/teclado e tabela alternativa. O gráfico
adapta sua geometria e densidade de rótulos ao celular. Modais reutilizam foco,
Escape e bloqueio do fundo oficiais. Os filtros ficam no fluxo, sem cobrir gráficos.

## Geração e arquivos

O modal permite visão geral, vendas ou financeiro, usando o período atual ou
7/30/90 dias. A prévia informa fontes/registros incluídos. As três etapas são
operações locais reais: capturar/validar, preparar CSV e guardar a cópia. Não há
servidor de geração ou progresso artificial temporizado.

Cada relatório concluído contém um snapshot: mudanças posteriores nos registros
ou filtros não alteram sua cópia. CSV real em UTF-8/BOM, ponto e vírgula, aspas e
quebras escapadas; textos que possam ser fórmulas recebem neutralização.
Valores negativos numéricos continuam numéricos. As tabelas exportadas contêm
os registros que sustentam o relatório, definições, período, fonte e comparações.

**PDF usa a impressão do navegador**: “Imprimir / salvar PDF”, não download direto.
Uma composição própria A4 usa o mesmo snapshot, texto Unicode, tabelas com
cabeçalhos repetidos e conteúdo escapado via DOM. O usuário escolhe salvar PDF
no diálogo do navegador. A validação automatizada exercita essa composição com
Chromium PDF e extrai seu texto para conferir valores e acentos.

## Histórico e isolamento

Até 20 cópias, exclusivamente neste navegador; não sincronizam entre dispositivos
nem sobrevivem à limpeza do armazenamento. A chave inclui o escopo do perfil
existente (identidade/workspace validados) e os contratos públicos das fontes.
Não contém credenciais. Trocas de identidade, workspace ou fonte não recuperam
cópias incompatíveis. Ausência de sessão/escopo seguro bloqueia geração; não há
fallback para um histórico compartilhado. Conteúdo corrompido/incompatível é
rejeitado. A chave legada compartilhada do protótipo não é lida.

Busca, situação e detalhes operam sobre as cópias disponíveis. Erros reais de
geração ficam identificados e sem exportações. Falha de armazenamento permite
baixar a cópia temporária, com aviso explícito de que não será recuperada depois.
Falhas de arquivo e da API têm feedback, sem reaproveitar valores antigos como
se fossem válidos.

## Validação

Fixtures sintéticas e APIs interceptadas localmente; nenhuma chamada de produção.
Testes em `report-data.test.cjs`, `reports-v2-browser.cjs` e regressões existentes:

- fonte local e API, conta vazia, totais pagos/pendentes/excluídos e fonte em erro;
- janela atual/anterior, cobertura insuficiente e comparação desativada;
- troca rápida, contador interrompido, ausência de replay de linhas e movimento reduzido;
- geração, fechamento/foco do modal, cópia imutável, busca e filtro de situação;
- CSV com fórmulas neutralizadas e PDF válido com valores/acento conferidos;
- quota, erro de arquivo, erro de fonte, recuperação após recarga e isolamento;
- 320/360/390/768/1024/1440 px nos dois temas, teclado e erros JavaScript;
- regressões de Oportunidades, onboarding e personalização, além das demais abas.

Resultados confirmados: **206 testes Node passaram**; o fluxo focado de Relatórios
passou nos **12 layouts** (seis larguras × dois temas), incluindo CSV/PDF, falhas e
isolamento. A regressão visual adicional passou em **36 estados de ferramentas e
936 pontos de gráfico**, nove resoluções. O teste de movimento/foco também passou.
`npm run format:check` e `git diff --check` passaram. A revisão pela skill
`interface-finish-gate` resultou em **PASS**, com as capturas e verificações acima;
**zero agentes** utilizados.

Capturas em [reports-v2](reports-v2/). Fixtures são explicitamente sintéticas e não
representam faturamento de contas reais. Resultados finais dos comandos constam
na descrição da PR e na entrega da rodada.

## Pendências para integração definitiva

Homologação humana das definições comerciais e da experiência de impressão;
contrato remoto para cobertura/completude do histórico e eventual histórico de
relatórios sincronizado; relações comerciais adicionais para entrega,
atendimento concluído ou encomendas, caso sejam implementadas. Nada disso é
simulado nesta etapa. Perfil e histórico continuam locais conforme seus avisos.
Sem merge ou deploy nesta rodada.

## Capturas conferidas na aplicação oficial

| Estado             | Desktop claro                                       | Desktop escuro                                     | Mobile claro                                      | Mobile escuro                                    |
| ------------------ | --------------------------------------------------- | -------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------ |
| Resumo             | [1440 px](reports-v2/dashboard-1440-light.png)      | [1440 px](reports-v2/dashboard-1440-dark.png)      | [390 px](reports-v2/dashboard-390-light.png)      | [390 px](reports-v2/dashboard-390-dark.png)      |
| Gerar relatório    | [1440 px](reports-v2/generate-modal-1440-light.png) | [1440 px](reports-v2/generate-modal-1440-dark.png) | [390 px](reports-v2/generate-modal-390-light.png) | [390 px](reports-v2/generate-modal-390-dark.png) |
| Resultado          | [1440 px](reports-v2/ready-modal-1440-light.png)    | [1440 px](reports-v2/ready-modal-1440-dark.png)    | [390 px](reports-v2/ready-modal-390-light.png)    | [390 px](reports-v2/ready-modal-390-dark.png)    |
| Histórico          | [1440 px](reports-v2/history-1440-light.png)        | [1440 px](reports-v2/history-1440-dark.png)        | [390 px](reports-v2/history-390-light.png)        | [390 px](reports-v2/history-390-dark.png)        |
| Conta vazia        | [1440 px](reports-v2/empty-1440-light.png)          | [1440 px](reports-v2/empty-1440-dark.png)          | [390 px](reports-v2/empty-390-light.png)          | [390 px](reports-v2/empty-390-dark.png)          |
| Fonte indisponível | [1440 px](reports-v2/source-error-1440-light.png)   | [1440 px](reports-v2/source-error-1440-dark.png)   | [390 px](reports-v2/source-error-390-light.png)   | [390 px](reports-v2/source-error-390-dark.png)   |

Outras larguras conferidas nos dois temas: **320, 360, 768 e 1024 px**.
[PDF de validação, produzido pela composição de impressão](reports-v2/report-valid.pdf)
e [CSV do mesmo snapshot](reports-v2/report-valid.csv). Ambos contêm apenas fixtures sintéticas.
