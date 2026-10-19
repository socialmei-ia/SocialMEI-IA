# Análise de Clientes V2 — integração nativa

Base: main `6f4c8e1795cbb2e9074845edd9ac099a8ea3925b`.
Branch: `feat/client-analysis-v2`. Referência: HTML `analise-de-clientes-v2.html`
enviado pelo responsável; implementação direta autorizada, sem novo protótipo.

## Experiência

A aba Oportunidades substitui a Calculadora V3 por três seções:

- **Em análise:** mensagem conhecida, informações faltantes, pergunta copiável e
  classificação humana Quente/Morno/Frio. A classificação leva à fila de interesse.
- **Chance de fechar:** filtros por nível, indicador qualitativo, evidências,
  motivos, sugestão prudente, consulta/revisão da conversa e restauração da
  classificação automática. Não há percentuais ou probabilidades.
- **Atenção:** prioridades crítica/alta/normal; filtros abertos/resolvidos,
  evidências e resposta copiável; resolver/reabrir altera apenas a sessão.

Recusas, compras concluídas e pós-venda sem solicitação de suporte ficam em
**Fora da fila comercial**, sem serem tratados como vendas potenciais. A urgência
é um indício textual da mensagem decisiva, não um SLA ou avaliação clínica.
A janela de 24 horas do motor continua explicitamente experimental.

O HTML de referência orienta estrutura e interações; tokens, navegação, modais,
tipografia e temas são os nativos. O indicador das abas acompanha a seleção;
setas, Home/End e foco são suportados. O movimento reduzido desativa efeitos.
Os seletores novos usam `data-analysis-*`, sem colidir com Cliente 360.

## Dados e limites

O motor `intent-engine.js`/`priority-engine.js` e o contrato de leitura existente
não mudaram. O adaptador novo apenas organiza seus resultados para apresentação.
Sem contrato confiável de conversas vinculadas, contas remotas ficam vazias e
oferecem acesso a Configurações → Integrações. Não há fallback para exemplos.

No modo local, uma demonstração opcional usa conversas fictícias originais da
Caixa e oito casos adicionais isolados. Esses casos não são gravados no CRM,
nem inseridos na Caixa. Nenhum cliente do HTML anexado é importado como real.
Revisões, níveis manuais e alertas resolvidos ficam somente em memória, são
limpos por identidade/workspace e ao encerrar/recarregar a demonstração.

Copiar usa a área de transferência e informa falhas. Abrir na Caixa/consultar
cliente exige vínculo local já disponível. Não existe envio de WhatsApp,
notificação ou resolução remota. Sugestões precisam de revisão humana.

## Escopo e verificação

Removidos HTML, CSS, script e testes exclusivos da Calculadora V3. O helper
`client-analysis.js` substitui seu script na ordem nativa. Relatórios V2.1,
financeiro, autenticação, backend, banco e infraestrutura não foram alterados.
A análise avulsa de mensagens e o modal de revisão existentes foram preservados.

Testes focados: regras de apresentação, negações, suporte versus venda, exclusões,
urgência antiga, classificações manuais e demonstração; navegador com três abas,
todos os filtros, detalhes, resolver/reabrir, copiar/falha, revisão, Caixa,
identidade, conta remota vazia, teclado/foco, XSS e ausência de chamadas externas.
Matriz: 320/390/768/1440 px, claro/escuro. Capturas: `client-analysis-v2/`.
A regressão global continua incluindo onboarding, personalização, Relatórios,
Oportunidades e os demais módulos. Resultados finais constam na PR.

Histórico da Calculadora permanece documentado para rastreabilidade, mas o recurso
não é carregado pelo frontend. Sem merge ou deploy nesta rodada.
