# Release040 — preparação, sem publicação

## Checkpoint de publicação — continuação de04da1bd

**BLOCKED.** Banco040 aprovado anteriormente; não repetir restore/migrations.
Configurações dos16 containers e15 fontesCompose foram copiadas privadamente no
servidor (0700/0600), em `.socialmei-backup038-release040-8db028c/publication-preflight`.
O plano `cutover-connections.private.json` preserva credenciais/ambiente e mounts;
quatro ambientes instalados receberam somente DSN candidata e flags de segurança
no plano. Gateway mantém seus dois binds privados e remove apenas o Caddyfile
antigo no plano. Nada aplicado. Brevo original não foi modificado.

- A imagem715 não continha o workerInstagram. Corrigida isoladamente como
  `sha256:268a7b6523a0ada2ce27da2c1cd11549cac41c949e4ff19eda06de02fdff2840`,
  fonte8db028c; arquivo/hash/import comprovados sem iniciar worker. **Não herda os
  recibos9b/B2.** Faltam gateway da mesma fonte e provas vinculadas aos IDs exatos.
  Não relabelar imagens, editar recibos ou voltar à9b descartando `fdf97ed`.
- Preflight agora recusa envio humanoWhatsApp e ingressos legados/n8n habilitados.
  `staged_environment()` preserva demais valores privados e impede DSN substituta.
- Amostra:16 containers,642,5MiB disponíveis,1646,1MiB de swap ocupada; PSIavg10/60/300
  zero,1 página swapin/0 swapout em3s, CPU3,87%. Ocupação de swap não prova pressão
  atual. API/gateway instalados sem limite/reserva explícitos. Menor custo: núcleo
  sem novos workers, substituindo serviços existentes; requer aceitação de risco
  e carga controlada.4GiB é opção para margem/expansão, não requisito inventado.
- No038 não há rótulos Bella/Brilho em nome/slug/perfil/canal. Existem16 negócios,
  umWAHA e umInstagram no mesmo workspace. Os nomes constam como exemplos visuais
  em `FINALIZACAO-SEM-PRISMA-20261112.md`, não como cadastro persistido comprovado.
  Não é possível afirmar que foram criados depois do backup sem outra evidência.
  Após corte, dono autenticado pode conferir vínculos existentes e renomear via
  `PATCH /api/v1/auth/profile`; segundo negócio via `POST /api/v1/auth/workspaces`.
  Nunca inferir identidade pelo nome nem duplicar sessão/OAuth para esses rótulos.
- Filas candidatas:26 decisõesWAHA encerradas (24confirmed/2skipped); filasIG,
  identidade e recuperação vazias. Isto não atesta filas/journals vivos no corte.

### Solicitação única ao responsável AWS

Não é necessário conceder AdministratorAccess global ao executor.

1. **Leitura:** aplicar `aws-readiness-readonly-iam.example.json` à identidade
   operacional ou entregar inventário equivalente de EC2/EBS/IP/AZ. DescribeInstances
   eDescribeInstanceTypes têm negações documentadas; não foram repetidos. Demais
   permissões não foram presumidas negadas. Sem stop/start/resize nesta concessão.
2. **Bucket e backup:** aprovar nome/custo e criar com
   `postgres-backup-bucket.cloudformation.json` emsa-east-1, por identidade do dono.
   BootstrapS3 e permissõesCloudFormation estão em `AWS-RELEASE040-PREPARATION.md`.
   Anexar `postgres-backup-iam.example.json` à identidade efetivamente usada pelo
   SDK do serviçoroot, preferindo instanceprofile existente; a identidadeSSH pode
   ser diferente. Após concessão, confirmar uma vez nesse contexto, sem imprimir
   credenciais. Substituir apenas o bucket. São8 ações limitadas ao bucket/prefixo; sem
   ListAllMyBuckets/Delete/KMS/novas chaves. Autorizar instalação da rotina, upload,
   leitura da versão exata e restauração periódica em verificador aprovado.
3. **Capacidade/corte:** aceitar piloto controlado sem workers novos, ou aprovar
   ampliação e janela (políticaec2-resize separada, somente depois de EBS/IP/Brevo
   conferidos). Autorizar corte coordenado apenas após backup externo comprovado
   e fechamento técnico dos artefatos. SMTP/Meta/WAHA têm ativações separadas.

Procedimento do dono, **não executado** (substituir placeholders sem segredos):

```sh
aws cloudformation create-change-set --region sa-east-1 --stack-name socialmei-backup040 --change-set-name backup040-review --change-set-type CREATE --template-body file://deploy/team/postgres-backup-bucket.cloudformation.json --parameters ParameterKey=BackupBucketName,ParameterValue=BUCKET_APROVADO
aws cloudformation describe-change-set --region sa-east-1 --stack-name socialmei-backup040 --change-set-name backup040-review
# Somente após revisar/aprovar criação e custos:
aws cloudformation execute-change-set --region sa-east-1 --stack-name socialmei-backup040 --change-set-name backup040-review
# Política privada já com bucket preenchido; se a identidade for usuário, usar put-user-policy:
aws iam put-role-policy --role-name ROLE_OPERACIONAL_EXISTENTE --policy-name SocialMEIBackup040 --policy-document file://politica-backup-preenchida.private.json
```

### Backup preparado, ainda não ativado

`aws-postgres-backup.py --run --config-root /var/lib/socialmei/postgres040-backups backup`
usa somente alvo040 aprovado, receipt/hash da restauração validada e configuração
já verificada em memória (sem reabrir arquivo vulnerável a troca). Serviço root
exige pasta/arquivos/ancestrais confiáveis; copiar receipt aprovado para pasta
root-controlada,0700/0600. `postgres040-backup-target.example.json` começa false;
`current_production_backup` só muda após corte. Sem argumento, continua histórico.
Não usar o instalador antigo para substituir o timer atual.

Unidades `.service/.timer.example` horária/semanal têm sintaxe verificada, flock
e limites; não instaladas/iniciadas. SDKboto3 disponível. Aprovar previamente o
download versionado e staging do último dump verificado, sua aprovação vinculada
ao SHA e o manifesto de referência040. Esse alimentador/instalação ainda precisa
ser configurado; não chamar templates de rotina externa operacional.
Modo de restore padrão continua estrito. `archive_integrity` é opt-in040 para
dados que evoluem: verifica schema/ledger/FKs/definições de sequências e integridade
do arquivo; não compara conteúdo com origem nem estado das sequências/MAX(id).
Cheque semanal exige1GiB disponível e imagens locais imutáveis aprovadas; preferir
verificador separado. Skip por memória não é restore aprovado. Não houve restore
novo nem transferência real nesta continuação.

### Corte executável, somente depois dos bloqueios e autorização

1. Fixar uma identidade coerente API/gateway/B2 e recibos; renderizar os overlays
   privados reconciliados, release040, postgresAWS, gateway-bind e Brevo desativado.
   `--profile '*'` somente com `config`, jamais com `up`. Rodar preflight com
   `--database-runtime`; ele deve passar sem alterar recibos históricos.
2. Registrar backup externo recente/versão/readback/restore e configs privadas;
   aceitar capacidade. Preservar volumes, IP, proxyHTTPS, WAHA/n8n e sessões.
3. Na janela aprovada, bloquear novos escritores sem ACK de persistência fictício;
   preservar spool/retries. Drenar e pausar menu-sender, workerIG, menuAPI e API,
   incluindo fluxosn8n pertinentes. Se houver envio em andamento/incerto ou ausência
   de confirmação de pausa, abortar. Não limpar journals/filas nem repetir envios.
4. Aplicar DSN/CA040 a todos os consumidores; legados permanecem pausados e todos
   os envios desligados. Recriar somente API/gateway aprovados, `up -d --no-deps
   --pull never team-api team-gateway`, com o conjunto de arquivos privado aprovado.
   Não executar migrador, down/prune, restaurar banco ou recriar WAHA/n8n.
5. Validar banco efetivo040, cadastro/login/pendentes, CRM/Agenda e isolamento no
   site principal. Publicação falha se persistência/autorização/saúde divergirem.
   Só depois homologar cada canal/SMTP com autorização e um respondedor por conta;
   conferir watermark novo para evitar replay dos eventos anteriores ao corte.
6. Após novas gravações, rollback somente para B2 compatível040 usando o MESMO
   PostgreSQL040 e mantendo dados/filas. Nunca retornar conexão ao Prisma/038 ou
   usar a API86c antiga. Falha exige congelar escritores e preservar ambos os estados.

Atualização14/11: o responsável escolheu o backup038 de11/11 e autorizou perda
posterior. Esse backup foi restaurado em database nova na AWS e evoluído para040;
exportação atual/recuperação Prisma não são mais requisitos. Evidência real e
limites em [PostgreSQL AWS](AWS-POSTGRES-PREPARATION-20261112.md) e
[recibo](evidence/20261114-authorized-backup038-to040.json).
O banco candidato está040, com aplicação testada isoladamente. A imagem de ensaio
7158915…/fonte8db028c não substitui os recibos abaixo, vinculados às imagens9b/B2.
Antes de publicar, disponibilizar imagens correspondentes e validar o gate completo
com os overlays privados conciliados. Não usar código anterior à guarda040.
`compose.team-postgres-aws.yaml` prepara DSN/CA comum e rede externa privada;
renderizar com todos os perfis somente para inspeção, nunca para ativação automática.
Preflight de rede externa exige `--database-runtime`, com objetos `network`
(Name/Internal) e `postgres` (Name/State/HostConfig.PortBindings/NetworkSettings.Networks)
obtidos somente por leitura, sem ambiente/credenciais. Migrador fica isolado em perfil;
o corte para esta database já040 não deve executar migrations.

Código das imagens: `9b34ac80ee5f2d9d6a12aa1b5c7e254bccb0c4d8`.
Commits posteriores de ferramentas/evidência não substituem essa identidade.
Produção não foi publicada, migrada, reiniciada ou reconfigurada.

## Artefatos e configuração

- API: build local com `deploy/team/Dockerfile.release040-api`, contexto raiz,
  argumento `SOCIALMEI_RELEASE_SHA` completo. Inclui o worker Instagram.
- Gateway: `deploy/team/Dockerfile`, mesmo argumento SHA. Ambos possuem label OCI.
- Os arquivos `.dockerignore` específicos excluem configurações privadas do contexto.
- Renderizar configuração **em arquivo privado**, com `--env-file` privado e, nesta
  ordem: `compose.team.yaml`, `compose.team-recovery.yaml`,
  `compose.team-identity.yaml`, `compose.team-instagram-auto.yaml`,
  `compose.team-public-booking.yaml`, `compose.team-release040.yaml`.
- Informar IDs imutáveis em `SOCIALMEI_API_IMAGE`/`SOCIALMEI_GATEWAY_IMAGE` e
  `TEAM_AUTH_ENABLED=true`. Não exportar o JSON de configuração para logs/Git.
- `tools/release040-preflight.py --compose-json <privado> --rehearsal <recibo040>
--rollback-rehearsal <recibo de rollback> --source-sha <SHA completo>
--api-image <ID> --gateway-image <ID>` verifica
  artefatos locais, conexões iguais, redes, mounts, comandos e recursos desligados.
  Nunca aprova produção nem executa publicação. Perfis opcionais continuam inativos.
- O overlay exige Compose com suporte a `!reset`/`!override`, remove builds/bind de
  código e dependência implícita do migrador. Migrador fica em `maintenance040`.
  Isso não autoriza executar esse perfil. Não usar publicadores legados.

## Sequência obrigatória para uma publicação futura

1. Confirmar a candidata040 derivada do backup038 explicitamente escolhido pelo
   responsável e seu recibo de restauração. Não exportar nem reativar Prisma.
2. Comprovar backup externo e restauração isolada, IAM e capacidade sob carga.
   A amostra AWS registra API antiga unhealthy e pouca RAM; não aprova capacidade.
3. Conciliar overlays, redes, sessões, filas, volumes, credenciais e patches
   instalados. Comparação de três arquivos não certifica toda a árvore instalada.
4. Conferir por leitura a identidade040, privilégios e recibos do destino já
   validado. Precheck039 é histórico; não reaplicar migrations na candidata.
5. Obter aprovação específica para troca de conexão e publicação. Coordenar pausa
   dos escritores e backup040 antes do corte, sem exportação da origem descartável.
6. Publicar apenas IDs aprovados, incrementalmente e sem acionar dependências ou
   migrador automático. Validar readiness autenticado040, login, sessões, isolamento,
   Agenda e filas antes de liberar tráfego. Interromper em qualquer divergência.
7. Ativar SMTP/canais separadamente, após capacidade, conta/destinatário controlado,
   permissões Meta e exclusividade do respondedor comprovados.

Rollback aprovado em ensaio: candidata9b → imagemB2 com guarda040, preservando
o mesmo banco040, contas pendentes, sessões e filas. Não fazer downgrade de schema,
restaurar backup antigo sobre gravações novas ou repetir envios incertos. Reverter
somente imagens/configuração conciliada; conferir saúde, identidade e isolamento.
Falha de persistência, saúde, duplicação ou isolamento impede continuar a ativação.

Evidências sanitizadas em `docs/evidence/20261113-mission3-release.json`,
`20261113-runtime-capacity.json` e `20261113-schema040-rollback-rehearsal.json`.
