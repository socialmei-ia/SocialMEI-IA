# PR #102 — preparação de publicação preservando os hotfixes públicos

## Escopo e situação

Base `b83689431f28fa9b7ba14c06240897e1fcaf8df3`. Alteração de senha: commit `df7c6884d6fc666155cbc53c673cd445e7119a4d`. Esta rodada registra também a entrada pela landing para sessões anônimas e uma referência explícita de gateway público sem Basic. O SHA final e seu CI constam na PR #102. Nenhum deploy, merge, backup remoto ou migration foi executado nesta preparação.

Os hotfixes implantados são informação do proprietário; os hashes, imagens, configuração ativa, modos de autenticação e espaço livre da AWS precisam ser reconferidos pelo bloco somente de leitura enviado. A inspeção anterior, feita antes desses hotfixes, não comprova o estado atual.

## Hotfixes versionados e limites

- `frontend/scripts/experience.js`: a resolução de uma sessão anônima mantém a landing. Entrar/cadastrar são ações explícitas; uma sessão válida continua restaurando o aplicativo. Falhas de sessão não abrem dados locais como dados autenticados.
- `deploy/team/Caddyfile.public`: referência pública sem desafio HTTP Basic. Mantém verificações de Origin, limites, cabeçalhos e encaminhamento de cookies à API; endpoints técnicos continuam exigindo Bearer no backend. Rotas privadas/desconhecidas e `/health/db` não são publicadas.
- A configuração privada antiga `deploy/team/Caddyfile` permanece para os ambientes privados e suas regressões. **Não utilizá-la para reconstruir o gateway público existente.** A referência pública também não deve sobrescrever cegamente o Caddy instalado: conservar suas rotas, mounts, cabeçalhos e demais hotfixes efetivos.
- Um gateway público só é aceitável com autenticação individual habilitada e autorização por workspace na API. Configuração desconhecida/desabilitada bloqueia a atualização.

## Payload mínimo

A mudança de senha altera somente estes arquivos de runtime:

1. `python-service/account_auth.py`
2. `frontend/scripts/auth-store.js`
3. `frontend/scripts/app.js`
4. `frontend/scripts/experience.js`
5. `frontend/scripts/password-strength.js`

Não há dependência nova, migration, mudança de configuração privada, parâmetros Argon2 ou armazenamento. O máximo de 128 caracteres permanece. Senhas antigas continuam verificáveis; a lista de bloqueio aplica-se apenas a senhas novas.

Para preservar ajustes não versionados da AWS, preparar o payload a partir de **cópias privadas dos cinco arquivos instalados**, aplicando nelas apenas o diff desses arquivos entre `b836894` e `df7c688`. Executar `git apply --check` e depois aplicar o patch apenas no diretório temporário. Não substituir `experience.js` instalado por uma cópia integral do Git. Conflito ou origem incompatível bloqueia a publicação. Conferir que o trecho que mantém a landing permaneceu intacto e revisar qualquer outra diferença de frontend.

O pacote de preparação contém esse patch, hashes da base e da alteração, e este roteiro. Não contém arquivos da AWS, configuração privada ou credenciais. O patch não altera o Caddy nem tenta migrar o backend antigo para a candidata completa.

## Gates antes de pedir aprovação de publicação

- CI completo verde no HEAD final da PR, incluindo navegador, preview HTTPS e banco descartável.
- Snapshot recente do Git e containers instalados; alterações locais existentes identificadas e preservadas, sem reset/clean/pull automático.
- Confirmar que os demais arquivos da API instalada correspondem à base compatível `b836894`, ou documentar/revisar suas diferenças. A imagem da API não pode ser presumida compatível pelo SHA do frontend. Divergência exige nova validação; não fazer atualização parcial sobre API antiga sem evidência.
- Confirmar landing anônima, ausência de Basic no gateway ativo, sessão individual habilitada e integrações externas desabilitadas conforme configuração efetiva.
- Preservar toda a cadeia Compose dos labels e os mounts privados, sem imprimir variáveis ou Compose completo.
- Conferir espaço para dump, imagens e rollback. A medição anterior de 94% de ocupação exige nova medição e bloqueia builds até demonstrar capacidade suficiente. Não executar prune nem remover backups/volumes automaticamente.

## Backup a preparar antes da atualização autorizada

Usar a rotina team documentada, reconciliada com os arquivos Compose efetivos; não executar o backup legado que para n8n. Registrar SHA do checkout, IDs/digests de API e gateway, IDs/StartedAt dos demais containers, mounts e hash dos arquivos instalados.

Guardar com permissões privadas: dump e índice do PostgreSQL team, configuração efetiva e arquivos privados, Caddyfile ativo/no disco, os cinco arquivos originais e imagens anteriores completas de API e gateway. Validar hashes, índice do dump e restauração em destino descartável; manter cópia privada fora da VPS. Interromper se o backup ou a verificação falhar. Não incluir esse conteúdo na PR ou no pacote público.

**Imagem anterior não é sinônimo de estado instalado.** Se um hotfix foi aplicado na camada gravável do container, salvar somente a imagem original perde esse hotfix. Conferir `docker diff` sem publicar seu conteúdo privado e comparar os arquivos com a imagem. Preparar bases privadas de rollback equivalentes ao filesystem instalado, incorporando as cópias reais dos hotfixes, inclusive o Caddyfile e frontend, sem inserir variáveis de ambiente ou credenciais no build. Configurações montadas continuam preservadas pelos mounts. Se houver alteração não identificada ou não for possível demonstrar equivalência, interromper. Não usar um rollback histórico que volte a exigir Basic ou esconda a landing.

O backup real ainda não foi executado: esta entrega prepara o procedimento e os gates, sem alegar proteção já concluída.

## Atualização proposta — somente após aprovação específica

1. Fixar os SHAs e o estado instalado aprovados, backups conferidos e payload aplicado em cópias temporárias. Não misturar PR #101 ou atualizar dependências.
2. Preparar imagens derivadas das **bases de rollback equivalentes ao estado atualmente instalado**, previamente preservadas e validadas conforme o parágrafo acima: copiar somente `account_auth.py` para `/app/account_auth.py` na API e os quatro JS para `/srv/frontend/scripts/` no gateway. Não executar `rm -rf /srv/frontend`, instalar pacotes ou copiar Caddyfiles do Git.
3. Validar sintaxe e diferenças das imagens. Exigir igualdade do Caddyfile anterior/novo e dos demais arquivos não autorizados, incluindo configurações de gateway; comparar também a configuração ativa com a de disco. Divergência não prevista bloqueia. Não reconstruir pelos Dockerfiles genéricos, que podem reintroduzir a configuração privada antiga.
4. Preparar um override privado que mude somente as duas imagens no Compose efetivo. Comparar a configuração normalizada, retirando apenas esses dois campos, exigindo igualdade integral. Não imprimir o Compose.
5. Após autorização explícita, recriar somente `team-api` e `team-gateway`, com `--no-deps --no-build`, preservando todos os mounts, redes, configuração e demais serviços. Não executar `team-migrate`, atualização do PostgreSQL, n8n, WAHA ou Caddy público.
6. Conferir igualdade dos containers não envolvidos; registrar imagens, hashes, resultado e hora. Não usar o workflow genérico de produção.

## Homologação

Em ambiente descartável: cadastro com 7 caracteres rejeitado; 8 aceitos sem composição obrigatória; senhas extremamente comuns rejeitadas; aviso de senha fraca preservado. Login existente funciona; troca para 8 caracteres revoga sessões anteriores; sessões antigas não recuperam dados; outro workspace recebe 404 para registros alheios. Revalidar CSRF, rate limiting e Argon2.

Na publicação autorizada: HTTPS com certificado validado; raiz/assets 200 sem `WWW-Authenticate: Basic`; visitante anônimo vê landing e só abre autenticação por ação explícita. APIs protegidas sem sessão retornam 401; caminhos privados/desconhecidos retornam 404. Os endpoints públicos de política/sessão têm respostas próprias 200 e não devem ser tratados como falha. Testar login com conta de teste autorizada, nunca pedir senha real no chat. Escritas de homologação devem usar negócio fictício identificado e autorizado, sem tocar registros existentes.

## Rollback

Se falhar um gate antes da troca, não publicar. Se falhar teste crítico após a troca, usar a cadeia Compose preservada e override com as duas imagens anteriores; recriar exclusivamente API/gateway, sem dependências ou build. Revalidar HTTPS, landing, ausência de Basic e login. Como não há migration, não restaurar banco automaticamente; registros criados após o backup devem ser preservados. Manter as imagens e os backups até aceite final. Não fazer rollback para um gateway histórico com Basic ou frontend anterior ao hotfix da landing.
