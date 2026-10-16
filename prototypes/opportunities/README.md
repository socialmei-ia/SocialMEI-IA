# Oportunidades — análise e priorização local

Branch `feat/local-purchase-intent`, derivada de `reports-v1-prototype` (PR #54), no commit `9dd185e55ea0c84eceaa3996817464687d039176`. Esta etapa depende dessa base experimental; não autoriza merge ou publicação de nenhuma das branches.

Sirva a raiz do checkout conforme o [guia de prévias](../README.md) e abra `/prototypes/opportunities/`. A primeira área analisa oito clientes sintéticos e sugere quem acompanhar primeiro. Abra **Ver conversa** para conferir evidências, acrescentar uma mensagem fictícia ou revisar o encaminhamento com motivo. Reiniciar ou recarregar descarta alterações e revisões.

A análise avulsa anterior continua abaixo da fila: digite uma mensagem ou carregue um exemplo e clique em **Analisar intenção**. Comparação de até três textos, contextos fictícios e biblioteca de seis exemplos manuais continuam independentes.

## Prioridade entre clientes

`priority-engine.js` reutiliza `intent-engine.js`, sem DOM nem persistência. Contrato: `prioritizeCustomers(customers, {referenceTime, reviews})`, disponível em `SocialMEIPriority` e Node. Cada cliente tem `id`, `name` e `messages` com `id`, `author` (`customer`/`mei`), `text` e `at` (ISO UTC). Só mensagens do cliente entram na análise; IDs repetidos são rejeitados. O cenário separado está em `priority-scenario.js`.

- Grupos comerciais: acompanhar primeiro (compra explícita, combinação elevada ou orçamento), responder consulta, esclarecer decisão, retomar contexto antigo e entender necessidade. Suporte, compra relatada como concluída e desistência aparecem em outra área, sem representar menor importância no atendimento.
- Dentro de cada grupo: prazo reconhecido em sinal comercial de até 24 horas, recência do sinal decisivo e ID estável. Não há soma de mensagens, score ou probabilidade. Os sinais de mensagens separadas não são combinados para fabricar intenção elevada.
- Recusa posterior prevalece sobre compra anterior. Nova consulta ou intenção após recusa, ressalva ou pós-venda exige esclarecimento. Consulta de acompanhamento não apaga uma intenção explícita; saudação, item ou urgência isolada não renovam a data do sinal decisivo.
- Sinal comercial com mais de 24 horas vai para retomada de contexto. O limiar é uma escolha demonstrativa, não uma regra validada para todos os negócios. A referência fixa é 16/10/2026, 12h UTC; datas ausentes, inválidas ou futuras impedem desempate por recência e preservam a ordem informada da conversa.
- O retorno preserva análises/evidências por mensagem, `decisiveMessageId`, motivos, próximo passo, recomendação automática e eventual revisão. Uma revisão `{group, reason}` altera o encaminhamento e reordena a lista, mantendo a recomendação original visível. Nova mensagem invalida a revisão daquele cliente; reanalisar preserva revisões.

O cenário distingue Ana (sinais combinados e prazo), Bruno (orçamento), Camila (preço, mesmo com mais mensagens), Diego (conflito/objeção), Helena (intenção antiga), Gabriela (suporte), Eduardo (compra relatada) e Fernanda (desistência posterior). Não confirma pagamento, resolução de suporte ou mudança real de interesse; decisões e mudanças de contexto ainda precisam de revisão humana.

## Contrato e critérios

`intent-engine.js` não depende da interface: `SocialMEIIntent.analyzeMessage(text)` no navegador ou `require('./intent-engine.js').analyzeMessage(text)` em Node. Aceita até 4.000 caracteres; tipo inválido e excesso de tamanho geram erro. Texto vazio retorna informações insuficientes.

O resultado contém `version`, `category`, `label`, `explanation`, `rule`, `nextStep`, `signals`, `missingInformation` e `limitations`. Cada sinal tem `id`, `label`, `polarity` e até três evidências `{text, start, end}`; os índices seguem UTF-16 e reproduzem exatamente `text.slice(start, end)`. Não há score, probabilidade ou estado acumulado no motor.

- Recusa acompanhada de consulta comercial ou compra não negada exige esclarecimento de conflito; recusa isolada deve ser respeitada.
- Fala relatada, pós-venda, condições, objeções, incerteza e negações modificam a leitura antes de avaliar intenção elevada.
- Pesquisa declarada é exploratória. Compra explícita sem ressalva reconhecida, ou a combinação item + preço + disponibilidade + entrega/pagamento/orçamento, gera intenção elevada provisória.
- Consulta comercial isolada gera interesse inicial. Elogio, urgência ou menção a produto isolados não bastam; ausência de sinais gera informações insuficientes, nunca baixa intenção automática.

Os padrões são heurísticas finitas em português. Não compreendem toda a linguagem, não verificam catálogo, estoque ou preço, não resolvem ironia nem mantêm histórico. Podem produzir falsos positivos e negativos; as evidências e limitações permitem revisão humana. Sentimento não entra no cálculo da categoria.

## Isolamento e verificação

Motor e interface não usam APIs, stores do aplicativo, armazenamento persistente ou integrações. Textos e comparações ficam em memória, descartados ao limpar ou recarregar. Conteúdo informado é renderizado como texto. Nada envia respostas ou altera clientes reais.

```sh
CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:intent
CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:priority
```

Omita a variável se usar o Chromium do Playwright. Os testes cobrem categorias, negação, conflito, evidências literais, texto novo, limites, determinismo, navegação por teclado, edição, comparação, isolamento e dez combinações de largura/tema (320, 360, 390, 768 e 1440 px; claro/escuro). Capturas ficam em `test-results/purchase-intent/`. A suíte também é chamada por `test:development`.

Análise avulsa — capturas da primeira rodada: [desktop claro](captures/analysis-1440-light.png), [desktop escuro](captures/analysis-1440-dark.png), [mobile 390 claro](captures/analysis-390-light.png) e [mobile 390 escuro](captures/analysis-390-dark.png). São saídas do navegador sobre dados sintéticos, sem montagem visual. Comparação, contexto e estado vazio também são capturados pela suíte.

Priorização: [desktop claro](captures/queue-1440-light.png), [desktop escuro](captures/queue-1440-dark.png), [mobile 390 claro](captures/queue-390-light.png) e [mobile 390 escuro](captures/queue-390-dark.png). A suíte grava fila, visão inicial, detalhes e revisão em `test-results/customer-priority/`, verifica dez combinações de largura/tema e valida que os trechos pertencem à mensagem do cliente correto.

## Próxima fase proposta — depende de aprovação

Definir autorização, minimização e retenção de conversas reais; preparar amostra rotulada por pessoas e medir erros, sobretudo recusa/pós-venda; incluir histórico e contexto autorizado do negócio por um contrato versionado. Só depois validar integração contextual à Caixa/Cliente 360 com controle de acesso, revisão humana e rastreabilidade. Uma avaliação comparativa poderá orientar a adoção de modelos de linguagem; probabilidades exigiriam metodologia e calibração próprias. Nenhuma dessas integrações faz parte desta entrega.
