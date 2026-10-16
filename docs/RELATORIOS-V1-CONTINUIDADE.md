# Continuidade V1 — Relatórios

Registro histórico da etapa anterior à autorização de desenvolvimento autônomo. A situação posterior está em [Rodada de desenvolvimento V1](V1-DEVELOPMENT-ROUND.md).

Rodada de 16/10/2026. Protótipo visual ainda sem aprovação do responsável. Nenhuma mudança integrada à aplicação, commit, merge, publicação ou operação na AWS.

## Estado confirmado

- `main` remota: `82dd52b1307236cf8bb65925e9423546c0dcbe23`, confirmada via conector GitHub e `git ls-remote`.
- PRs #51, #52 e #53: integradas. PR #48: aberta, head `755c8df41ee6b77ca13dfca3ecb52a70b9f3ee84`, 25 arquivos.
- Cinco checks do SHA da main concluídos com sucesso: `validate`, `browser`, `build`, `report-build-status`, `deploy`. Os nomes dos checks não identificam a versão do runtime AWS nem substituem homologação visual.
- Branch local `reports-v1-prototype` baseada nesse SHA. O checkout da rodada anterior estava em `7b90a2c`, anterior à PR #53; a proposta anterior era não versionada e não aprovada.

## Reconhecimento delimitado

| Tela                                            | Arquivos principais                                                                                                                                       |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Home                                            | `frontend/scripts/experience.js`, `frontend/styles/socialmei.css`                                                                                         |
| Negócio, Clientes, Produtos, Vendas, Financeiro | `frontend/scripts/business-views.js`, helpers/stores por módulo, `frontend/styles/workspace-refinement.css`                                               |
| Relatórios                                      | markup em `frontend/socialmei-app.html`; `renderReports()` em `frontend/scripts/app.js`; helpers em `frontend/scripts/reports.js`; CSS em `socialmei.css` |
| Caixa Unificada                                 | `inbox.js`, `inbox-sync.js`, `navigation.js`, markup e CSS existentes                                                                                     |
| Assistente / Automações                         | `experience.js`, markup e CSS existentes                                                                                                                  |
| Configurações                                   | `app.js` (`renderSettings`), markup e CSS existentes                                                                                                      |

As capturas do app atual mostram uma estrutura utilizável, sem necessidade demonstrada de reconstrução. O reconhecimento de layout cobriu as 11 telas em 1440/1024/768/390/360/320 e claro/escuro, usando dados locais fictícios e rede externa bloqueada. Isso não é QA funcional completo de todos os módulos, autenticação ou backend.

`workspace-refinement.css` tem escopo de shell, navegação e listas de gestão, usa tokens existentes e não contém regras específicas de `#reportsView`. Sua posição após as folhas anteriores estabelece uma camada de sobrescrita deliberada. Não foi demonstrada regressão causada por essa camada no reconhecimento de layout nem nos três testes de contrato. Nenhuma reescrita foi feita por tamanho ou preferência estética.

## Problemas e limites

| Prioridade                         | Evidência / limite                                                                                                                                                                      | Encaminhamento                                                                                                                                                                         |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1 visual                          | No mobile de Relatórios, título, origem, período e indicadores ocupam a maior parte da primeira tela; o gráfico exige rolagem. As ações de exportação ficam ao fim de uma página longa. | Demonstrar uma composição mais direta, preservando detalhes progressivos e funcionalidades. É proposta de usabilidade, não falha de cálculo confirmada.                                |
| P1 processo                        | Proposta anterior foi feita sobre checkout anterior à PR #53 e sem comparação visual da base atual.                                                                                     | Base atual confirmada, capturas coletadas e três direções explicitadas antes da integração. PASS técnico não equivale ao aceite do usuário.                                            |
| P2 preparação                      | PR #48 mistura protótipo de Oportunidades/testes com CI, Docker e dependências Python.                                                                                                  | Avaliar futuramente `prototypes/opportunities.html` e seu teste como proposta separada. Não incorporar CI, inventário ou dependências por arrasto. Nenhum arquivo da PR foi integrado. |
| P0 de demonstração: não verificado | Versões AWS, acesso real, persistência no alvo e fluxo completo do evento não foram homologados nesta rodada.                                                                           | Inventário e smoke em etapa própria autorizada. Não foi constatado um incidente P0 pelos testes locais; isso não comprova prontidão para o evento.                                     |

Nenhum bug pequeno da aplicação oficial foi demonstrado que justificasse uma correção nesta rodada. A única implementação ficou no protótipo e em seu teste. Não foram alterados stores, scripts oficiais, configuração de deploy, contratos ou dados reais.

## Proposta visual

Três direções e respectivos custos de uso estão em `prototypes/reports/README.md`: A, resumo compacto com detalhes progressivos (recomendada e prototipada); B, tabela primeiro; C, perguntas do negócio. Referências de princípios reutilizam o design system já documentado; sem nova pesquisa externa.

Prévia: abrir `prototypes/reports/index.html` a partir do checkout. A pasta foi retirada de `frontend/`, pois `deploy/team/Dockerfile` copia essa árvore para o gateway. Arquivos do protótipo: HTML, CSS e JS locais, mais README; teste em `tests/reports-prototype-browser.cjs`.

Capturas da base em `test-results/v1-current/` e da proposta em `test-results/reports-prototype/`. As bases fictícias diferem; comparar composição, não valores comerciais ou pixels equivalentes.

A proposta mantém cinco visões demonstrativas, dois períodos, comparação fictícia, privacidade, tabela, resumo copiado, CSV de vendas e impressão identificada. A futura integração deve preservar todos os períodos e contratos reais: a prévia não é substituta funcional do renderer existente.

## Verificações executadas

| Verificação                                                                      | Resultado / alcance                                                                                                                                                                                        |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reconhecimento via Playwright, script temporário `work/inspect-v1.cjs`           | 132 combinações de tela/largura/tema; presença da tela confirmada, sem overflow global nem erros JS. Movimento reduzido e rede externa bloqueada.                                                          |
| Helper `tests/reports-browser.cjs`, invocado pelo script com servidor/browser    | Passou: totais, períodos, IDs homônimos, canais, fonte compartilhada simulada, privacidade, SVG e mensagens desativadas. Não executado como CLI avulsa.                                                    |
| `node --test tests/workspace-refinement.test.cjs`                                | Três testes passaram.                                                                                                                                                                                      |
| `CHROMIUM_EXECUTABLE=/usr/bin/chromium node tests/reports-prototype-browser.cjs` | 48 estados passaram: seis larguras × dois temas × quatro cenários. Mais período, comparação, cinco visões, privacidade, CSV, clipboard, impressão/período e teclado. Sem erros JS ou requisições externas. |
| Sintaxe JS, Prettier dos arquivos da proposta e `git diff --check`               | Passaram. Suites de backend, banco e todos os módulos não foram repetidas; não há mudanças nesses componentes.                                                                                             |

O teste de impressão verifica solicitação e estilos em mídia print; não é aprovação manual de paginação de PDF. Não há diálogos ou menus novos no protótipo. O teste de teclado cobre os controles exercitados, sem equivaler a auditoria completa com leitor de tela.

Revisão independente `anti-ui-slop-reviewer`: PASS após corrigir orientação financeira sem evidência, identificação de período na impressão e escopo do CSV. Comparação anterior mantém ticket coerente com quantidade inteira. Isso é parecer técnico do protótipo, sem substituir aprovação estética do responsável.

## Próxima decisão

Aprovar ou ajustar a direção A. Somente após aprovação explícita: integrar Relatórios na branch, preservar contratos e cálculos reais, executar regressão pertinente, revisar e preparar PR sem merge. Depois desse ciclo, iniciar Caixa Unificada; Assistente/Automações e QA geral vêm na sequência. Feature freeze em 23/10 segue apenas proposta, sem confirmação. Oportunidades, onboarding adaptativo, IA e integrações reais permanecem planejamento futuro.

Recursos efetivos nesta rodada: implementação direta; `coordinator` e `anti-ui-slop-reviewer` como agentes separados seguindo os perfis do repositório (sem carregamento nativo por nome); somente a skill local `prototype-first`, já lida na rodada anterior. Nenhum outro especialista foi acionado.
