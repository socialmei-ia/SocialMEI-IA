# Relatórios — proposta A, ainda não aprovada

Base verificada no GitHub: `82dd52b1307236cf8bb65925e9423546c0dcbe23` (PR #53), em 16/10/2026. Branch local: `reports-v1-prototype`.

Abra `prototypes/reports/index.html` no navegador, a partir do checkout completo. Também funciona com um servidor estático na raiz. Usa a fonte Inter existente, arquivos locais e dados fictícios em memória, sem API, autenticação ou armazenamento do app. A pasta está fora de `frontend/`, copiada pela imagem do gateway.

## Direções consideradas

| Direção                          | Proposta                                                                                       | Custo de uso                                                       |
| -------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| A — Resumo compacto, recomendada | Quatro indicadores, período visível, gráfico e detalhes progressivos; cinco visões preservadas | Equilibra leitura inicial e aprofundamento                         |
| B — Tabela primeiro              | Registros, filtros e exportações como entrada principal                                        | Favorece conferência; exige mais leitura para entender o resultado |
| C — Perguntas do negócio         | Organizar a página em perguntas sobre vendas, clientes e caixa                                 | Favorece iniciantes; exige mais mudanças de navegação e textos     |

Referências de direção: princípios já registrados em `docs/DESIGN-SYSTEM.md` e composição observada no app atual: hierarquia, densidade apropriada, detalhes progressivos e cores sem efeitos decorativos novos. Não houve nova pesquisa externa nem cópia de outra interface.

A foi escolhida para demonstração pela menor mudança sobre a estrutura existente. Essa escolha técnica não substitui o aceite visual do responsável. B e C são alternativas conceituais, não outros protótipos implementados.

## O que esta prévia demonstra

- Faturamento, vendas pagas, ticket e saldo; vendas e movimento financeiro separados.
- Dois períodos fictícios, comparação com valores anteriores fictícios e origem explícita.
- Resumo, Vendas, Clientes, Atendimento e Financeiro com controles locais funcionais.
- Claro/escuro, privacidade, tabela acessível, estados sem dados/carregando/indisponível.
- Cópia de resumo, CSV **de vendas** fictícias e impressão com período identificado.

Não é uma implementação dos cálculos reais nem de todas as opções da aplicação. Na integração aprovada, preservar os oito períodos, intervalo personalizado, cinco visões, comparação, canais, rankings, tabela, exportações, privacidade, origem dos dados e isolamento existentes. O contexto de atendimento fictício não prova relação comercial, conversão, integração ou envio real.

## Validação

```sh
CHROMIUM_EXECUTABLE=/usr/bin/chromium node tests/reports-prototype-browser.cjs
npx prettier --check prototypes/reports tests/reports-prototype-browser.cjs
```

Omita `CHROMIUM_EXECUTABLE` se usar o navegador instalado pelo Playwright. A suite cobre 48 estados: seis larguras (320/360/390/768/1024/1440), dois temas e quatro cenários, com movimento reduzido. Verifica períodos, comparação, cinco visões, privacidade, CSV baixado, clipboard, solicitação de impressão, período impresso e teclado; bloqueia rede externa. Capturas em `test-results/reports-prototype/`.

Revisão independente final registra resultados no relatório `docs/RELATORIOS-V1-CONTINUIDADE.md`. Aprovação visual, integração, homologação na AWS, merge e publicação continuam pendentes e separados.
