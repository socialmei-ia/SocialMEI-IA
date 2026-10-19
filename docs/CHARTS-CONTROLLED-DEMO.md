# Gráficos e dados de teste controláveis

Base: `main` em `987cd2989bd1001f8903f10fbc56191df974888f`, já com as PRs #61 e #62. Branch própria: `feat/charts-controlled-demo`. Nenhuma alteração de backend, autenticação, infraestrutura ou publicação.

## Uso

Em **Configurações → Usar dados de teste**, ative a amostra. Início, as cinco seções de Negócio, Oportunidades e Relatórios usam uma fonte fictícia de leitura. Um aviso permite desativar sem voltar às Configurações. Caixa Unificada, Divulgação e demais módulos mantêm suas fontes e comportamentos existentes; nenhuma conversa é inserida na Caixa.

O botão é um switch acessível por teclado. A preferência fica neste navegador, por identidade/workspace resolvidos pelo repositório de perfil existente. Sem identidade ou com armazenamento indisponível, a leitura falha fechada. Não há sincronização entre dispositivos.

Desativar devolve as referências originais de `appData`. Novos espaços locais e remotos começam com coleções comerciais vazias, em vez de receber os antigos exemplos automaticamente. Registros já salvos são preservados: não há como apagar seletivamente exemplos antigos sem arriscar dados inseridos pelo usuário.

## Base pequena e coerente

- Seis clientes fictícios, com mensagens comerciais, pesquisa, dúvida, recusa e suporte/pós-venda.
- Dois itens explicitamente de exemplo, distinguindo produto físico de serviço.
- Oito vendas distribuídas nos últimos 35 dias, com dias sem registros, uma pendente e uma cancelada.
- R$ 415 em vendas pagas no conjunto completo; R$ 155 em despesas pagas e R$ 40 a pagar. Totais de cada período variam com a data corrente.
- Receitas financeiras correspondem às vendas pagas; as duas fontes continuam separadas nos cálculos. Não se somam para inflar o faturamento.
- Datas relativas ao dia atual na zona usada pela aplicação. Cadastros precedem os registros correspondentes.

O provider congela a amostra e nunca a conecta aos stores. Renderizadores consultam `businessViewData()`/`businessViewConversations()`; persistência e transportes continuam usando o estado original. Ações de cadastro, edição, pagamento, estoque, menus de registros e backup ficam bloqueadas durante a demonstração. Entradas nativas de criação/edição/confirmação também recusam alterações nesse modo. Revisões de intenção e resolução de alertas permanecem experimentais e em memória, sem envio.

Relatórios mantém seu motor, comparações, sanitização CSV e impressão/salvar PDF do navegador. Snapshots fictícios identificam a fonte e usam um namespace de histórico separado do histórico normal, além da identidade/workspace/configuração de fonte. Nenhuma amostra é enviada para API ou salva como cadastro comercial.

## Refinamento visual

O levantamento direcionado encontrou barras e minigráficos em Resumo e Financeiro; Vendas e Clientes já utilizam indicadores/tabelas e não receberam gráficos artificiais. Atendimento em Relatórios continua mostrando vínculos/mensagens disponíveis, sem inferir conclusão de atendimento.

As barras existentes receberam grade discreta compartilhada, espaçamento, cantos, escala tabular, foco e hover. Alturas interpolam em 480 ms a partir da seleção anterior; a mesma geometria não repete a entrada. Minigráficos têm traços arredondados e desenho progressivo de 560 ms quando a série muda. Cache visual reinicia na troca de identidade/modo. Observadores ignoram atualização de nós de texto, evitando trabalho por quadro durante a contagem dos KPIs.

Relatórios V2.1 preserva suas linhas, pontos, slider, contagens e morph existentes; recebeu apenas acabamento de traço e destaque do ponto ativo. Tooltips continuam acessíveis por mouse/teclado, com valores em tabela. Todos os novos movimentos usam a preferência de movimento reduzido.

## Verificação reproduzível

- `npm test`: contratos, cálculos, exemplos pequenos/coerentes/imutáveis, isolamento e falha de armazenamento.
- `npm run format:check`.
- `CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser`: regressões completas, incluindo a nova suíte.
- `node tests/charts-demo-browser.cjs`: cinco larguras (320/390/768/1024/1440), dois temas, modo ligado/desligado, teclado/foco, tooltip, CSV/snapshot, leitura protegida, recuperação e conta remota simulada com troca de usuário/workspace e nenhuma escrita.

Regressões de CRUD/composição que precisavam dos antigos registros agora recebem **explicitamente** `tests/fixtures/legacy-local-business.json`. As asserções originais de transações e geometria foram preservadas; os exemplos não voltaram à inicialização do produto.

Limites: testes em Chromium automatizado, sem certificação de aparelho físico ou leitor de tela. O modo de teste não é um sandbox de toda a aplicação: somente as fontes descritas são substituídas. Não há integração nova com canais, alertas ou serviços externos.

## Resultado local e capturas

`npm test`: **232 passaram, nenhuma falha ou skip**. `format:check`: aprovado. A regressão completa de navegador passou em **88 estados e 28 fluxos**; a suíte específica final validou **90 estados**. O PDF fictício foi gerado com Chromium e conferido com `pdftotext`, incluindo identificação da fonte e faturamento do snapshot. A suíte visual adicional passou em **22 estados de Home e 22 de Financeiro**.

Foram corrigidos durante a validação um ciclo de atualização por evento de dados (o refresh agora acompanha mudança de identidade) e a carga automática dos antigos registros locais. Os fixtures existentes foram explicitados sem reduzir as asserções de regressão. O CI remoto é informado na PR para o SHA publicado, separadamente destes resultados locais.

Capturas reais da navegação oficial, com o modo ligado:

| Tela          | Desktop claro                                           | Desktop escuro                                         | Mobile claro                                          | Mobile escuro                                        |
| ------------- | ------------------------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------- | ---------------------------------------------------- |
| Resumo        | [1440 px](charts-demo-evidence/overview-1440-light.png) | [1440 px](charts-demo-evidence/overview-1440-dark.png) | [390 px](charts-demo-evidence/overview-390-light.png) | [390 px](charts-demo-evidence/overview-390-dark.png) |
| Financeiro    | [1440 px](charts-demo-evidence/finance-1440-light.png)  | [1440 px](charts-demo-evidence/finance-1440-dark.png)  | [390 px](charts-demo-evidence/finance-390-light.png)  | [390 px](charts-demo-evidence/finance-390-dark.png)  |
| Relatórios    | [1440 px](charts-demo-evidence/reports-1440-light.png)  | [1440 px](charts-demo-evidence/reports-1440-dark.png)  | [390 px](charts-demo-evidence/reports-390-light.png)  | [390 px](charts-demo-evidence/reports-390-dark.png)  |
| Configurações | [1440 px](charts-demo-evidence/settings-1440-light.png) | [1440 px](charts-demo-evidence/settings-1440-dark.png) | [390 px](charts-demo-evidence/settings-390-light.png) | [390 px](charts-demo-evidence/settings-390-dark.png) |

[PDF fictício conferido](charts-demo-evidence/demonstration.pdf) · [90 estados da suíte específica](charts-demo-evidence/results.json).
