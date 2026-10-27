# V25 — publicação controlada de API e gateway

A candidata de aplicação é `1b28e84eacc5a782504b810114ba19775a1df58e`, com CI aprovado. O publicador adicional é ferramenta operacional revisada; conferir também seu CI antes de `--apply`. Não usar o publicador genérico antigo, que assume26 migrations e integrações desativadas inclusive OAuth.

`tools/v25-release-publish.py` exige `--folder`, `--rollback-backup` e, para inspecionar/publicar, `--restore-evidence`. O padrão é inspeção; `--inspect` é equivalente. `--apply` faz o corte; `--rollback` restaura imagens/configuração anteriores, preservando migrations aditivas. Não faz build, merge ou alteração de PostgreSQL/n8n/WAHA/Caddy público.

## Evidências e limites

- Preparação funcional001–031; ledger instalado deve corresponder exatamente à preparação. Na primeira execuçãoV25,001–026; depois de rollback com SQL aditivo retido, uma nova preparação pode registrar001–031 e nenhuma migration pendente.
- Backup de rollback com4 arquivos e SHA256SUMS; os IDs/tags dos containers e as configurações das imagens no Docker-save devem coincidir com a instalação anterior. As camadas referenciadas precisam existir no arquivo e o Caddy privado arquivado precisa coincidir com a preparação.
- `build-image-ids.private.json` fixa imagens, IDs e SHA; árvore exportada em `source/` precisa coincidir integralmente com os blobs Git da candidata.
- `restore-evidence.private.json` é **relato do operador**, não prova de restauração executada pelo publicador. Registra backup e seus hashes conferidos, prefixo001–026 restaurado,001–031 ensaiado, rede none,384MiB, SHA da candidata e `migration_sha256` com hashes dos31 SQLs. Só registrar após restauração realmente relatada/conferida.
- Preflight verifica containers, Compose efetivo, env, volumes/redes, imagens, checkout/hotfix preservado, Caddy em disco/ativo e adaptador da imagem nova. O modo OAuth connect é preservado; envio, ingresso e publicação permanecem desligados.
- A migration reutiliza a conexão da API, mas confirma host/alias, banco, usuário e rede do PostgreSQL team. URL com substituição de host por query é recusada. Um runner com a imagem nova e PYTHONPATH=/app aplica somente o prefixo revisado em transação; env temporário privado é removido.

## Corte e retorno

Antes de alterar serviços, faz backup atualizado, verifica novamente o baseline e executa migrations. Troca somente API e gateway com `--no-deps --no-build --pull never`. A fonte privada do Caddy já montada é substituída atomicamente antes da recriação do gateway; o checkout antigo e seu hotfix não são sobrescritos.

HTTPs, sessão remota, rotas anônimas e arquivos frontend são conferidos. Resultado final registra SHA, imagens/containers e backups em recibo privado; login real pelo navegador permanece uma aceitação manual.

Falha após início da troca aciona rollback somente dos serviços afetados; alteração da fonte Caddy já conta como gateway afetado. Unknown/concurrent Caddy bytes are never overwritten. Se não for possível verificar/restaurar o Caddy, o gateway não é recriado com configuração desconhecida e o erro exige intervenção; a API ainda recebe tentativa de restauração. A conferência de rollback não depende de imagens candidatas.

**Não repetir `--apply` com preparação antiga após rollback.** Gerar nova preparação contra as imagens/configurações restauradas e capturar novo backup de rollback dos containers recriados. Seus IDs mudaram; o backup anterior continua preservado como evidência, mas não pode atestar o novo baseline. Reutilizar fonte/imagens candidatas somente após conferir seus hashes; não apagar nem tentar desfazer migrations aplicadas. Envios e workflows externos continuam desligados/inválidos até homologação própria.

A janela operacional deve excluir edições concorrentes de Compose/env/Caddy. O lock serializa este publicador; outros operadores precisam respeitar a janela. Artefatos e logs são privados0700/0600 e podem conter credenciais; nunca anexá-los ao chat/GitHub.

## Verificações desta implementação

20 testes focados do publicador,141 operacionais (14 opt-in não executados na chamada geral),17 focados do preparador incluindo Caddy real e compatibilidade do parser com um Docker-save real. Os testes do publicador usam fixtures sintéticas; nenhum corte real foi executado por esses testes. SMTP/Meta/WAHA reais continuam fora dessa evidência.
