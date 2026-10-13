# Acesso da equipe ao banco

## Decisão desta estabilização

MEIs usam **sessão e API**, não logins SQL. Desenvolvedores usam PostgreSQL local com dados sintéticos. Consulta à produção fica restrita a responsáveis autorizados, com login PostgreSQL individual, perfil de consulta e caminho de rede privado. Docker equivale a privilégio administrativo e não é necessário para um integrante que só consulta dados.

O perfil `socialmei_team_readonly` está preparado em `database/team-readonly-access.sql` e foi testado em banco descartável. **Não foi aplicado à AWS e nenhum integrante foi provisionado.** Ele concede leitura explicitamente a CRM/canais e às colunas de identificação do workspace; não concede escrita, senhas, sessões, convites, configuração do negócio ou acesso automático a novas tabelas. Não é RLS: permite consultar os negócios nas tabelas concedidas e só deve ser atribuído a um mantenedor autorizado a essa consulta. Não usar para contas de clientes.

## Caminho de rede

PostgreSQL team está apenas na rede interna do Compose. Um túnel SSH apontando para `127.0.0.1:5432` na VPS **não funciona por suposição**, pois não existe esse bind confirmado. Para consulta humana, preferir pgAdmin/cliente instalado em rede privada com acesso ao banco team e HTTPS protegido, com login individual; alternativa é VPN/bastion ou encaminhamento restrito aprovado pelo responsável. O pgAdmin legado e a URL histórica não comprovam acesso à rede team. Nenhuma porta/mount/rede foi alterada nesta rodada.

## Procedimento do responsável

Executar somente depois de conferir runtime, autorização do integrante e backup privado de dados **e roles**. O dump do banco team não inclui definições globais de roles. Armazenar esse backup separadamente e nunca publicar seu conteúdo, pois pode incluir hashes de autenticação.

1. Conferir os privilégios existentes e a necessidade da pessoa. A aplicação SQL deve ocorrer em transação, com `ON_ERROR_STOP`, no banco `socialmei_team`; não usar o `database/permissions.sql` legado do n8n como perfil team.
2. Aplicar o arquivo `team-readonly-access.sql` pelo acesso administrativo privado. Ele recusa um perfil preexistente que seja login/superuser/creator/bypassRLS. Não revoga grants já existentes; a conferência de permissões continua necessária.
3. Criar um **login novo individual**, sem superuser/createdb/createrole/bypassRLS. A senha é definida com `\password` em terminal interativo, nunca como argumento, script versionado ou mensagem de chat. Não compartilhar a senha da API nem de um administrador.
4. Conceder somente o perfil de consulta; validar efetivamente com esse login que leitura autorizada funciona e INSERT/UPDATE/DELETE, auth e outros bancos estão bloqueados. `NOINHERIT` exige selecionar o perfil com `SET ROLE`; o responsável também precisa verificar CONNECT da conta antes do login.
5. Registrar pessoa, finalidade e data de revisão de acesso fora de arquivos públicos com dados pessoais. Revogar o vínculo/perfil e desativar o login individual quando necessário; remover acessos de SSH/pgAdmin/VPN associados separadamente.

Não existe nesta rodada um perfil universal de developer na produção: desenvolvimento de schema usa ambiente isolado e migrations revisadas pelo mantenedor. A role da aplicação precisa de seus próprios grants após inventário; substituir a role configurada no runtime sem conferir dependências pode interromper auth, migrations e backup.

## Limites

As permissões do perfil foram exercitadas nos testes, inclusive recusa de role privilegiada. Grants/roles/logins/firewall reais da AWS permanecem NÃO CONFIRMADOS. A implantação depende de uma coleta sanitizada e de configuração privada pelo responsável; não há procedimento de compartilhamento de segredo neste guia.
