# Validação da revisão técnica

Os resultados abaixo pertencem à revisão histórica de 10/10/2026. Para a cobertura e os limites atuais, consulte [a revisão de 12/10/2026](REVISAO-PROJETO-2026-10-12.md) e o workflow `Repository checks`.

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
