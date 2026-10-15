# Validação da revisão técnica

Os resultados da seção histórica abaixo pertencem a 10/10/2026. A cobertura atual é descrita primeiro; revisões datadas não são evidência de uma nova coleta AWS.

## V2 Foundation — 15/10/2026

Baseline: `db775dc5ae427eafed01a7dcd0d365dc92b23a16`; branch `chore/v2-foundation`. Nenhum arquivo do app, migration ou Compose foi alterado. Testes locais usam recursos descartáveis deste ambiente, não AWS.

| Camada                                | Resultado local                                                                                                                                                  |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Node                                  | 72 passaram; inclui contrato do export Python manual/interno/timeout                                                                                             |
| API/Python + PostgreSQL16 descartável | 148 passaram, sem skips; inclui corpo real do export e erro422 sem `texto`                                                                                       |
| Operação/inventário                   | 24 passaram; cinco gateway opt-in ignorados no comando padrão                                                                                                    |
| Gateway real Caddy                    | Os cinco opt-in passaram em execução separada                                                                                                                    |
| Instalação limpa Python3.12           | requirements/constraints instalaram; `pip check` sem conflito                                                                                                    |
| Imagem API                            | Dockerfile com lock construiu; container `--network none` iniciou HTTP e respondeu `/health`/`/processar` com contrato correto                                   |
| Navegador do app                      | 88 estados e 21 fluxos passaram, incluindo contas/admin, onboarding local e módulos                                                                              |
| Temas/layout                          | 825 estados e 163 estados de botões, sem pageerror/404 local                                                                                                     |
| Motion/visual                         | 22 estados Home e 22 Financeiro; foco, touch e reduced motion passaram                                                                                           |
| Configurações                         | 990 estados passaram em local/remoto simulado                                                                                                                    |
| HTTPS/Basic                           | Quatro módulos conectados, escrita autenticada e recusa anônima passaram em containers isolados                                                                  |
| Protótipo Oportunidades               | 24 combinações: seis larguras × claro/escuro × normal/reduced motion; busca/filtros/quadro/detalhes/etapa/reset/teclado passaram, sem requisição a outro recurso |
| Formatação                            | Prettier e Black nos arquivos Python alterados; `git diff --check`                                                                                               |

Instalação: `python -m pip install -r python-service/requirements.txt` e `python -m pip check`. As versões diretas/transitivas foram fixadas às usadas nos testes. O build local usou CA do proxy como secret temporário; a imagem não incorpora essa CA. Tags de imagem base continuam flutuantes e o lock não tem hashes de distribuição.

Comandos de navegador são os mesmos do CI, mais `node tests/opportunities-browser.cjs`. O protótipo é servido pelo teste em HTTP local porque o Chromium gerenciado bloqueou `file://`; isso não é defeito do HTML nem prova de abertura em todo computador. O teste aguarda o evento de fechamento/foco do diálogo, sem tempo fixo. Capturas desktop/mobile e HTML são entregues pelo artifact `opportunities-prototype` do CI.

Ocorrências de preparação: primeira conexão SQL usou nome incorreto da role de fixture e foi repetida com a identidade do banco descartável; a primeira expectativa manual do smoke tinha contagem de texto incorreta e foi corrigida para `len(text)`. O teste HTTPS falhou com proxy ambiente aplicado aos nomes Docker internos; a fixture passou a definir `NO_PROXY` apenas nesses containers de teste e a repetição passou. Não foi alterada configuração de produção para contornar testes.

**NÃO TESTADO/BLOQUEADO:** SSH/runtime AWS nesta rodada, execução no editor n8n, registro do runner, envio/recebimento WhatsApp, SMTP/Meta/IA, onboarding Windows completo e restore de backup real. `/processar` local funciona; isso não declara o workflow na AWS homologado. A confirmação final humana do cadastro novo continua pendente. Os PRs #44/#45 permanecem separados.

O CI do SHA final do PR deve validar novamente as suites e o startup/restore isolado team. Resultados desse workflow, PR/commit e artifact ficam no GitHub; não substituir essa evidência pelo sucesso local ou pelo CI da baseline.

## Preparação da base — 14/10/2026

[Baseline, decisões e limites](../FUTURE-READINESS-REVIEW.md). Comandos executados no checkout de revisão com fixtures locais, sem conta ou banco da AWS:

| Comando / camada                                                  | Resultado e alcance                                                                                                       |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `npm test`                                                        | 71 passaram; sintaxe, recursos, contratos de stores/dados, navegação, exports e executor local de migrations              |
| `npm run format:check`                                            | Formatação dos arquivos cobertos pelo Prettier; não formata Python                                                        |
| `python -m unittest discover -s python-service -p 'test_*.py'`    | 140 passaram com `TEST_DATABASE_URL`/`DATABASE_URL` para PostgreSQL 16 descartável; sem skips                             |
| `python -m unittest discover -s tests -p 'test_*.py'`             | 19 passaram; cinco de gateway ignorados por exigirem opt-in                                                               |
| `SOCIALMEI_TEAM_GATEWAY_TEST=true` + suite `test_team_gateway.py` | Cinco passaram separadamente com Caddy e rede próprios                                                                    |
| `npm run test:browser`                                            | 88 estados e 21 fluxos, incluindo contas, CRUD, filtros, replay, rascunhos, transferência e teclado                       |
| `node tests/stability-browser.cjs`                                | 825 estados de layout/tema e 167 estados de botões passaram; 11 resoluções e Light/Dark/Auto-Light/Auto-Dark/Custom       |
| `node tests/visual-browser.cjs`                                   | 22 estados Home e 22 Financeiro; foco, touch, spotlight, privacidade, vazio e reduced motion                              |
| `node tests/settings-browser.cjs`                                 | 990 estados; modo local/remoto simulado, salvar, temas e teclado                                                          |
| `node tests/team-browser.cjs`                                     | HTTPS e Basic reais em containers descartáveis, API mock: quatro módulos conectados, escrita autenticada e recusa anônima |
| OpenAPI completo                                                  | JSON igual à main `92d4c20…`, 53 operações e modelos preservados                                                          |

Python exige dependências de `python-service/requirements.txt`. Os casos de integração são ignorados sem `TEST_DATABASE_URL`; esse skip não equivale a banco validado. A configuração e os comandos do teste de banco usam exclusivamente uma instância descartável, porque as suites alteram suas fixtures. Para navegador, instalar Chromium com Playwright ou definir `CHROMIUM_EXECUTABLE`; o caminho dessa variável é local ao computador, não um arquivo para versionar.

Teste adicional do executor contra PostgreSQL real descartável: status em banco vazio → schema continuou ausente; migrate → 11 versões instaladas; status → histórico lido. Só o comando migrate criou estrutura. O setup/config Compose foi validado separadamente; n8n/WAHA da stack completa e o notebook Windows não foram iniciados por esta revisão.

Não executar `*-browser.cjs` que exportam função como CLIs independentes. `browser.cjs` já chama os helpers de contas, módulos remotos, catálogo, vendas, financeiro, relatórios, contato e transferência. As cinco suites principais acima são as mesmas usadas no CI.

Comparação visual: 44 pares antes/depois de 11 telas em 1440/390px e claro/escuro. 39 idênticos; cinco com 6–40 pixels diferentes e no máximo quatro níveis por canal RGB, sem mudança de geometria/conteúdo. São diferenças residuais de rasterização, não igualdade pixel a pixel. Dados fictícios, relógio fixo, movimento reduzido e toasts temporários ocultos na comparação.

Na primeira execução paralela, as suites funcional/estabilidade/visual falharam durante a inicialização da experiência; repetições isoladas foram verificadas sem alterar expectativas. A causa pontual dessas falhas de inicialização não foi isolada. O primeiro teste HTTPS também exigiu selecionar o Chromium local e ajustar somente o proxy interno dos containers descartáveis; o ajuste de proxy não foi versionado nem aplicado à AWS. Registrar essas ocorrências, não transformar tentativa falha em resultado de produção.

O CI ainda valida startup da stack team, migrations e restore em banco próprio. Esse gate remoto deve ser conferido no SHA final do PR; resultado antigo não o substitui. Não houve teste de restore do banco real, mensagem WhatsApp, ativação de workflow, SMTP, Meta ou IA remota nesta revisão.

## Executado em 10/10/2026

| Verificação                                              | Resultado                                                                                                                      |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Testes Node de dados, backups, temas, exports e recursos | 15 testes passaram.                                                                                                            |
| Contratos Python: rotas, modelo e respostas              | 3 testes passaram; preservados `/`, `/health`, `/processar` e chaves JSON.                                                     |
| Backup com Docker falso                                  | 5 testes passaram: sucesso, falha de dump, falha de archive, falha de restart e volume ausente. Não executam containers reais. |
| Comparação de extração JavaScript                        | AST de 22 módulos igual à fonte aprovada, excluindo comentários/formatação e declaração de configuração literal movida.        |
| Comparação da cascata CSS                                | 13.010 declarações preservadas em ordem/contexto/valor; uma media query adjacente consolidada.                                 |
| Assets extraídos                                         | Ícone e fonte com bytes idênticos aos data URIs da fonte aprovada; licença Inter preservada.                                   |
| Compose                                                  | `docker compose --env-file .env.example config --quiet` passou. Antes da correção, YAML inválido.                              |
| Shell                                                    | `bash -n backup.sh` passou.                                                                                                    |
| Regressão offline no Chromium                            | 88 estados (11 módulos × 4 larguras × claro/escuro) e oito fluxos passaram, sem erros JavaScript.                              |
| HTTP da API Python                                       | TestClient confirmou `/`, `/health`, resposta de `/processar` e rejeição de payload inválido (422).                            |
| Dependências e formatação                                | `npm ci --ignore-scripts --no-audit --no-fund` e `npm run format:check` passaram.                                              |

Os testes são reproduzíveis pelos comandos do [DEVELOPMENT.md](../DEVELOPMENT.md). A comparação pontual AST/cascata foi feita contra o arquivo aprovado fornecido nesta sessão; SHA-256 e origem estão em [PROJECT-REVIEW.md](../PROJECT-REVIEW.md).

Após a liberação das permissões do ambiente, o navegador e o TestClient puderam executar. A regressão usou `CHROMIUM_EXECUTABLE=/usr/bin/chromium`, serviços externos bloqueados e movimento reduzido. Verificou cadastro/login/onboarding locais, CRUD e busca vazia, rascunhos do Inbox, Assistente sem envio, automações simuladas, CSV, persistência, exclusão e restauração JSON, sidebar mobile, temas automático/custom e toasts. Resumo e oito capturas estão em `test-results/`.

## Publicação

A branch `chore/project-review` foi enviada ao GitHub e o [PR #6](https://github.com/socialmei-ia/SocialMEI-IA/pull/6) foi aberto como rascunho. O CI remoto precisa ser conferido antes do merge. A publicação não aplica mudanças na VPS.

A primeira execução do CI identificou uma opção de testes indisponível no Node 22: `--test-isolation=none`. O comando foi corrigido para `node --test tests/*.test.cjs`, mantendo os 15 testes. O ambiente local usa Node 24; a compatibilidade com Node 22 é verificada pelo job remoto.

## Não executado nesta revisão

- O daemon Docker local ficou acessível após a liberação, mas build/containers, Caddy/TLS, PostgreSQL, n8n e WAHA não foram executados. A validação Compose não prova funcionamento da infraestrutura.
- Sem acesso à VPS/serviços externos: nenhuma mensagem enviada, credencial validada, workflow ativado, consulta SQL aplicada, sessão WAHA iniciada ou backup real produzido.

## Gate antes do merge/deploy

O CI deve executar formatação, contratos e a regressão de navegador: 11 módulos × 4 larguras × claro/escuro, além dos fluxos locais de CRUD/auth/onboarding/backup/Assistente. Capturas e resumo ficam em `test-results/`, publicados como artifact do job.

Revisão manual complementar: landing e animações com movimento normal, formulários nos quatro tamanhos, tema custom, teclado/foco, filtros/estados vazios do Inbox, modais/drawers e conservação dos dados já existentes. Os testes offline não substituem homologação da integração remota.

Não há baseline visual novo aprovado nem resultado de integração externa nesta revisão. Se o CI falhar, ajuste a implementação/teste com evidência antes do merge, sem tratar a falha como ruído.
