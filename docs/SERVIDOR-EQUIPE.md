# Servidor protegido para a equipe

Este pacote prepara a publicação; não instala nem publica por merge. O servidor
AWS registrado pela equipe é uma referência histórica: primeiro confirme na EC2
se o IP, a chave SSH, o diretório e o projeto Compose continuam corretos. Não envie
chaves privadas ou senhas pelo chat. Este guia não muda a pilha local do notebook.

## O que será instalado

- Projeto Compose separado `socialmei-team`, com PostgreSQL, API, gateway Caddy e
  migrations 001–007. Banco/volumes próprios, sem usar o banco do n8n.
- Um novo hostname HTTPS no Caddy **existente**. O app e `/api/v1` ficam na mesma
  origem. O proxy existente só acessa o gateway; banco e API não publicam portas.
- Usuário e senha individuais solicitados pelo navegador antes de acessar o site.
  Senhas são convertidas em hashes bcrypt; não entram no config.js nem no Git.
  O gateway protege também API e saúde do banco, recusa origens externas e remove
  Authorization ao encaminhar à API.
- Clientes, Catálogo, Vendas e Financeiro remotos no workspace `team`. Todos os
  membros autorizados têm acesso de leitura e escrita ao mesmo negócio. Não é
  isolamento entre empresas nem um sistema de papéis administrativos.

O login/cadastro visual existente continua demonstrativo; a proteção real é a
janela de credenciais do navegador no servidor. HTTP Basic exige HTTPS na entrada
pública. Credenciais podem ficar em cache no navegador; para sair, feche a sessão
privada do navegador ou revogue a conta e recarregue o gateway. Não há botão de
logout de servidor nesta versão.

`n8nMessagesUrl` fica desativado no site da equipe até uma integração autenticada
ser conferida. N8n, WAHA e seus dados existentes não são movidos para o novo banco.
Os dados do notebook também **não são enviados automaticamente**. Faça backup e
planeje uma única importação do histórico após publicação: cada navegador tem
sua própria origem, portanto repetir o mesmo histórico de dois navegadores pode
duplicá-lo. Estoques e vendas precisam de reconciliação; importar vendas não baixa
estoque novamente. Esta instalação pode começar com dados de demonstração criados
na API vazia, sem usar o banco local.

## Primeiro: confirmar acesso (sem alterações)

No PowerShell do notebook, procure apenas o caminho da sua chave existente:

```powershell
Get-ChildItem "$env:USERPROFILE\Downloads", "$env:USERPROFILE\Desktop", "$env:USERPROFILE\.ssh" -Filter *.pem -File -ErrorAction SilentlyContinue | Select-Object FullName
```

Se nenhuma aparecer, a chave pode estar em outra pasta. Não gere uma nova chave
esperando que ela já tenha acesso à EC2. Confirme no painel AWS qual instância e
qual chave pública foram autorizadas. O comando SSH depende desses valores:

```powershell
ssh -i "CAMINHO_DA_SUA_CHAVE.pem" ubuntu@IP_CONFIRMADO_NA_AWS
```

Antes de aceitar um hostname/chave de servidor pela primeira vez, confirme a
fingerprint com o responsável/AWS. Não desative a verificação de host.

Após entrar, apenas confira:

```bash
pwd
docker compose ls
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Não execute publicação antes de revisar esse estado e identificar o diretório,
project name e Caddy usados de verdade. `/home/ubuntu/socialmei` é a referência
histórica, não um alvo confirmado.

## Preparar depois de confirmar o servidor

Execute no checkout **existente**, após PR aprovada/mesclada, conferindo `git
status` e preservando mudanças locais. Tenha Python 3 e Docker Compose disponíveis.
O administrador precisa registrar os backups existentes antes de recriar o proxy.
Use um hostname novo apontando para o IP confirmado, diferente de n8n/API/WAHA.

```bash
git status --short
git pull --ff-only origin main
python3 tools/team-admin.py init --host app.SEUDOMINIO
```

O comando pede o primeiro usuário e uma senha individual de pelo menos 12
caracteres, até 72 bytes. Ele usa Docker/Caddy para gerar o hash, cria arquivos
privados com permissão 600 e uma senha nova para o banco. Não sobrescreve uma
configuração existente. Arquivos gerados: `.env.team` e `deploy/team/private/`.
Não leia ou cole esses arquivos no chat. Adicione outros membros individualmente:

```bash
python3 tools/team-admin.py add-user
```

Quem recebe acesso define uma senha própria por um canal privado aprovado;
não compartilhe a conta do primeiro usuário.

## Revisão e instalação (somente com aprovação para esse servidor)

A publicação recria o Caddy existente e pode causar uma breve interrupção nas
URLs que ele atende. Os containers n8n/WAHA e seus volumes não são recriados por
estes comandos. Os custos/recursos de PostgreSQL/API adicionais precisam caber
na instância existente. Se o checkout do servidor tiver overrides locais, eles
precisam ser incorporados explicitamente e revisados antes de continuar; `-f`
específico não carrega overrides automaticamente.

Primeiro inicie só a pilha privada. Ainda não existe uma URL pública nova:

```bash
docker compose --env-file .env.team -f compose.team.yaml config --quiet
docker compose --env-file .env.team -f compose.team.yaml up -d --build
docker compose --env-file .env.team -f compose.team.yaml ps
docker compose --env-file .env.team -f compose.team.yaml logs --tail 30 team-migrate
```

Falha de migration/saúde impede que a API/gateway fiquem prontos. `team-migrate`
termina com sucesso (Exit 0); API, banco e gateway ficam ativos. Em atualização,
recrie o migrador para aplicar migrations novas antes de subir a API:

```bash
docker compose --env-file .env.team -f compose.team.yaml run --rm team-migrate
docker compose --env-file .env.team -f compose.team.yaml up -d --build
```

Valide o Caddy do gateway:

```bash
docker compose --env-file .env.team -f compose.team.yaml exec -T team-gateway caddy validate --config /etc/caddy/Caddyfile
```

A próxima etapa usa `NOME_DO_PROJETO_ATUAL`, copiado dos labels/`docker compose
ls` da pilha existente. Não use `socialmei-team` aqui. Preserve `.env`, volumes,
nomes, diretório e overrides reais. A entrada opcional importa apenas o site novo;
sem `compose.team-proxy.yaml`, o glob vazio mantém o comportamento anterior.

```bash
docker compose -p NOME_DO_PROJETO_ATUAL --env-file .env -f compose.yaml -f compose.team-proxy.yaml config --quiet
docker compose -p NOME_DO_PROJETO_ATUAL --env-file .env -f compose.yaml -f compose.team-proxy.yaml run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile
```

Depois da validação e aprovação do alvo, publique somente o proxy:

```bash
docker compose -p NOME_DO_PROJETO_ATUAL --env-file .env -f compose.yaml -f compose.team-proxy.yaml up -d --no-deps caddy
```

Não abra 5432, 8000 ou 5500 na AWS. A entrada usa as portas 80/443 existentes,
DNS do hostname novo e certificado emitido pelo Caddy. Se não houver certificado
válido, pare e confira DNS/firewall; não continue aceitando HTTP ou erro TLS.

## Conferir proteção e compartilhamento

Sem senha, esta consulta deve retornar **401**, nunca uma lista de clientes:

```bash
curl -I https://app.SEUDOMINIO/api/v1/clientes
```

Com seu usuário, curl pede a senha sem gravá-la no comando:

```bash
curl --user SEU_USUARIO https://app.SEUDOMINIO/health/db
```

Abra a URL HTTPS no computador e no celular em sessões próprias. Cada usuário
entra com sua conta. Crie um cliente fictício em um aparelho e recarregue no outro;
o registro deve aparecer, mesmo se o notebook original estiver desligado.
Revise ainda as URLs n8n/WAHA anteriores após recriar o proxy. Não trate a publicação
como concluída antes de verificar autenticação anônima, certificado e banco.

## Revogar acesso e backup

```bash
python3 tools/team-admin.py remove-user NOME_DO_USUARIO
docker compose --env-file .env.team -f compose.team.yaml exec -T team-gateway caddy validate --config /etc/caddy/Caddyfile
docker compose --env-file .env.team -f compose.team.yaml exec -T team-gateway caddy reload --config /etc/caddy/Caddyfile
```

A pasta privada é montada como diretório para o gateway ler a nova versão após
escrita atômica. Mesmo credenciais em cache deixam de ser aceitas depois de
recarregar. O utilitário recusa remover o último usuário; para bloquear todos,
remova a entrada HTTPS conforme rollback. Troca de senha usa `add-user` com o mesmo
nome e exige o mesmo validate/reload.

O `backup.sh` antigo não inclui o novo banco. Faça backup próprio antes de depender
da pilha da equipe e guarde uma cópia fora da instância; não compartilhe dumps:

```bash
umask 077
mkdir -p backups/team
docker compose --env-file .env.team -f compose.team.yaml exec -T team-postgres pg_dump -U socialmei_team -d socialmei_team -Fc > backups/team/banco.dump
tar -czf backups/team/config.tar.gz .env.team deploy/team/private
```

Use um diretório datado em backups recorrentes para não sobrescrever a cópia
anterior. Confirme status de saída dos comandos e teste restauração em banco
isolado. Não restaure esse dump no banco do n8n ou no desenvolvimento por acidente.

## Rollback

Retire só a entrada nova recriando o proxy com os arquivos/original project name
anteriores (sem `compose.team-proxy.yaml`), preservando overrides existentes.
A pilha da equipe pode então ser parada sem apagar volumes:

```bash
docker compose --env-file .env.team -f compose.team.yaml stop
```

Não use `down -v`, não renomeie volumes e não mude credenciais do n8n. O banco da
equipe fica preservado para diagnóstico ou retomada. Nunca use o workflow antigo
`Manual production deploy` para esta instalação: ele não aplica o overlay da
equipe nem suas migrations. A publicação desta etapa é manual e específica.

## Transferir o banco do notebook

A transferência inicial dos quatro módulos tem exportação consistente, prévia,
remapeamento por IDs e gravação atômica. Siga
[TRANSFERENCIA-NOTEBOOK.md](TRANSFERENCIA-NOTEBOOK.md); o backup do navegador não
substitui a exportação do banco compartilhado. A proteção por senha permanece ativa.
