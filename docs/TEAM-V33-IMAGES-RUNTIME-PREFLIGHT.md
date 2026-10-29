# Team v33 — auditoria do runtime e imagens compiladas fora da VPS

O servidor AWS possui ~1,9 GiB RAM, ~516 MiB disponíveis e 1 GiB de swap
utilizada. O banco da equipe já foi atualizado a **33 migrações**, com backup
verificado `team-auto-20261029-005509-e2bfd3`. O código funcional revisado
está preparado em stage limpo no SHA
`c19d44b6ef6b8f125e6cafe60a7adfc0477cf454`.

## Invariantes observadas na VPS

- API instalada: imagem Docker
  `sha256:1a593002996bd4463a22000bc8b23f73af4efeaab8c20bf128709b57aee8d78f`,
  redes `socialmei-team_api`, `socialmei-team_database` e
  `socialmei_team_egress`. **Não** substituir a rede `egress` pela
  `automation` simplesmente porque o arquivo Compose do Git é novo.
- Gateway instalado: imagem Docker
  `sha256:941bb458c0f7e6b6ca681cd9c493a9329f237b2bdeb2d9228c49cd04f36bc2d0`,
  redes `socialmei-team_api` e `socialmei_team_web`.
- O gateway recebe **Caddyfile privado** em `/etc/caddy/Caddyfile:ro`,
  além de `/etc/caddy/private:ro` e
  `/srv/frontend/config.js:ro`. A imagem candidata não pode eliminar nem
  reconfigurar essas três montagens.
- O banco `team-postgres` deve continuar acessível apenas via rede
  `database`, sem portas públicas, nem conexão com `automation`.
- WAHA/WebJS e n8n estão vivos no próprio host; **nenhum** deles deve ser
  recriado ou conectado a novas redes por esta fase.

## Auditoria somente leitura

Use `tools/team-v33-runtime-audit.py` no Ubuntu com
`--target team`. A ferramenta:

1. Confere o stage Git exato 001–033, API/DB em estado saudável, ledger 033
   e as quatro tabelas novas presentes.
2. Examina somente metadados Docker dos serviços `team-api`,
   `team-gateway` e `team-postgres`; nunca exibe credenciais nem o
   conteúdo dos arquivos privados.
3. Compara o SHA-256 do Caddyfile privado no host com o arquivo efetivo
   montado dentro do gateway.
4. Retorna hashes dos IDs de imagem, redes, destinos das montagens e flags
   sanitizadas; não mostra caminho do arquivo privado nem configuração bruta.
5. Indica se as imagens candidatas com labels de revisão corretas estão
   carregadas; não constrói/puxa imagens nem reinicia serviços.

**Importante:** a auditoria **não** representa aprovação de deploy. Um
publicador precisa verificar também o modelo Compose resolvido, montar
as imagens de rollback e assegurar troca de apenas API/gateway, com
reversão após falhas.

## Compilação no GitHub Actions em vez da VPS

`.github/workflows/team-v33-candidate-images.yml` compila as duas
imagens com source **fixado** em
`c19d44b6ef6b8f125e6cafe60a7adfc0477cf454` num runner GitHub
descartável. Exporta `images.tar.gz`, `image-receipt.json` e
`SHA256SUMS` para um artefato
`SocialMEI-Team-v33-c19d44b6ef6b` (retenção 14 dias).
As imagens contêm apenas o código do repositório; **nenhuma variável de
ambiente privada de produção** é carregada no build.

O artefato é um pacote de imagens para a próxima etapa, não uma
publicação na AWS. Antes de transferi-lo à VPS, verificar SHA-256,
identidade das imagens, destino e espaço livre. Não usar
`docker image prune`, `docker compose down`, o workflow legado da
branch main nem `docker compose up --build` do projeto inteiro.

## Próxima etapa

Preparar publicador separado, com **artefatos de rollback das imagens
antigas**, comparação exata do Compose runtime e montagens, e
`docker compose up --no-deps --no-build --pull never` apenas de
`team-api` e `team-gateway` quando os gates passarem. A URL pública
e autenticação devem ser testadas antes da confirmação. Não ativar
envio Direct, publicação Meta, bot WhatsApp ou sentimento nesta fase.


## Transferência e importação sem recriar containers

O artefato do build aprovado está no workflow
[GitHub Actions — Team v33 images](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/40815471116).
O ZIP contém apenas `images.tar.gz`, `image-receipt.json` e
`SHA256SUMS` e é destinado à importação manual controlada, não ao deploy.

1. Faça download do artefato `SocialMEI-Team-v33-c19d44b6ef6b` na
   interface GitHub Actions, na seção **Artifacts**. Não é preciso
   obter tokens nem colocar segredos GitHub na VPS.
2. No PowerShell Windows, transfira o ZIP:
   ```powershell
   scp -o IdentitiesOnly=yes -i "$HOME\.ssh\socialmei-key.pem" "$HOME\Downloads\SocialMEI-Team-v33-c19d44b6ef6b.zip" ubuntu@54.94.213.7:/home/ubuntu/socialmei-v33-images.zip
   ```
3. No Ubuntu, use `tools/team-v33-import-images.py`, obtido do commit
   aprovado da release, com `--target team --bundle
   /home/ubuntu/socialmei-v33-images.zip --inspect`. Em caso de
   aprovação, use `--apply` com o mesmo arquivo.
4. O importador só chama `docker load`, após conferir SHA256, tags,
   labels e IDs de imagem. Nunca altera containers, Compose, Caddyfile,
   PostgreSQL, WAHA, n8n ou dados de usuários.

O pacote é disponibilizado pelo GitHub por **14 dias**; baixar
diretamente via API geralmente exige autenticação GitHub, por isso
não instruir a colocar um Personal Access Token ou senha na VPS.
O build foi feito na própria infraestrutura GitHub, sem consumir RAM
da AWS.

**Depois da importação** ainda é necessário preparar snapshot de
rollback e validar o Compose real antes de substituir API/gateway.
A importação é reversível no sentido de que não muda o serviço em
execução; não apagar nem limpar as imagens antigas.
