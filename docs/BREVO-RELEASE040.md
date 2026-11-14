# Brevo e ativação controlada da release040

O responsável homologou o serviço Brevo, remetente e recebimento real. Essa prova
é externa à aplicação e não foi repetida. A integração abaixo foi testada somente
com credenciais sintéticas e SMTP simulado. Nada foi instalado/ativado na AWS.

## Entrada privada — sem enviar a chave no chat

Após autorizar a criação do arquivo novo, em terminal SSH interativo da AWS e
checkout operacional isolado contendo as ferramentas (não alterar checkout ativo):

```sh
python3 tools/brevo-private-config.py prepare --file "$HOME/.socialmei-brevo/brevo.env"
python3 tools/brevo-private-config.py inspect --file "$HOME/.socialmei-brevo/brevo.env"
```

Login e chave são digitados com eco desligado, nunca como argumentos. O preparador
falha semTTY/entrada protegida, recusa Git/junction/symlink e não sobrescreve arquivos
ou credenciais existentes. Pasta0700/arquivo0600 no Linux; ACL só do usuário no
Windows. Conteúdo permanece privado em disco, sem promessa de criptografia própria.
Usar diretório local não sincronizado; não incluir o arquivo em uploads genéricos.
Não executar `source`, `cat`, `set -x` ou imprimir `docker compose config` com dados reais.

## Configuração conciliada, ainda desligada

`compose.team-brevo.yaml` deve ser o último overlay SMTP, depois dos overlays
privados conciliados e release040. Fornecer o arquivo privado como último
`--env-file`. Prefixo BREVO separado evita colisão com variáveis SMTP antigas.
API, recuperação e identidade recebem os mesmos valores; STARTTLS587 e remetente
verificado são fixados no preparador. Banco, imagens, redes e perfis são preservados.

Exemplo de renderização **somente leitura**, após conciliar os overlays instalados:

```sh
umask 077
docker compose --env-file .env.team --env-file "$HOME/.socialmei-brevo/brevo.env" \
  -f compose.team.yaml -f compose.team-recovery.yaml -f compose.team-identity.yaml \
  -f compose.team-instagram-auto.yaml -f compose.team-public-booking.yaml \
  -f compose.team-release040.yaml -f compose.team-brevo.yaml \
  --profile '*' config --format json > "$HOME/.socialmei-brevo/compose.private.json"
python3 tools/brevo-private-config.py inspect --file "$HOME/.socialmei-brevo/brevo.env" \
  --compose-json "$HOME/.socialmei-brevo/compose.private.json"
```

O exemplo não substitui overlays privados existentes: inserir os reconciliados na
posição revisada antes da release040. Usar IDs aprovados em .env.team. O gateBrevo
confere valores privados sem exibi-los, conexão igual e links com a origem do gateway.
Executar também o preflight completo em `RELEASE040-READINESS.md`; nenhum desses
gates aprova banco/produção. Não usar o JSON privado como artefato público.
O perfil `'*'` acima serve só para renderizar; não utilizá-lo com up/run.

IDENTITY_MODE/RECOVERY_MODE permanecem disabled; agendamento público permanece
false e perfis dos workers não iniciam. A origem principal é conferida para evitar
links internos ou de preview. Contas já pendentes continuam bloqueadas com modooff.
Ativação futura exige override privado aprovado com identity=enforced/recovery=smtp;
não editar a chave para alterar flags nem iniciar worker enquanto os gates faltarem.

Após dados/backup/capacidade/migration040 aprovados e imagens importadas por ID,
a troca incremental usa o mesmo conjunto de argumentos Compose privado revisado:
primeiro `up -d --no-deps --no-build --pull never team-api`, conferir liveness e
readiness real040 e só então o mesmo comando para `team-gateway`. Não iniciar
`team-migrate`, Postgres ou workers por dependência, nem usar publicador legado.
Este procedimento não foi executado e não é autorização. Falha exige o fallbackB2
com guarda040, volumes atuais preservados e nova conferência antes de retomar.

## Solicitação única ao responsável AWS/dados

1. Anexar `deploy/team/aws-readiness-readonly-iam.example.json` à identidade de
   operação, ou fornecer inventário equivalente de zona/EBS/IP/ENA e permissões.
   DescribeInstances/DescribeInstanceTypes já negados não serão repetidos sem mudança.
2. Aprovar nome/custo S3 e bootstrap separado da role de backup. Com identidade
   autorizada, preencher variáveis não secretas e revisar o changeset:

```sh
aws cloudformation create-change-set --region sa-east-1 --stack-name socialmei-postgres-backup \
  --change-set-name release040-backup-bootstrap --change-set-type CREATE \
  --template-body file://deploy/team/postgres-backup-bucket.cloudformation.json \
  --parameters ParameterKey=BackupBucketName,ParameterValue="$APPROVED_BUCKET"
aws cloudformation describe-change-set --region sa-east-1 --stack-name socialmei-postgres-backup \
  --change-set-name release040-backup-bootstrap
```

Somente após aprovação específica de criação/custos:

```sh
aws cloudformation execute-change-set --region sa-east-1 --stack-name socialmei-postgres-backup \
  --change-set-name release040-backup-bootstrap
aws iam put-role-policy --role-name "$APPROVED_BACKUP_ROLE" --policy-name SocialMEIBackupPrefix \
  --policy-document "file://$PRIVATE_RENDERED_BACKUP_POLICY"
```

A política privada é cópia de `postgres-backup-iam.example.json` substituindo só o
bucket aprovado. Oito ações do caminho implementado; multipart não utilizado não
é concedido. Instalação, transferência real e restauração têm aprovação separada.
O produtor atual continua histórico: S3 não recupera dados atuais por si só.

3. Responsável Prisma deve restabelecer acesso/exportação da origem efetiva daAPI,
   sem mudar conexão, plano ou janela24h automaticamente. Depois de confirmar a
   mudança e autorizar exportação: `sudo -n python3 tools/aws-postgres-prepare.py --run export-source`.
   Verificar origem/schema/manifesto/restauração; nunca usar snapshot038 como atual.
4. Aprovar capacidade/janela só após inventário e backup restaurável. A proposta
   t3.medium segue em `AWS-RELEASE040-PREPARATION.md`. IP/DNS e IPde saída SMTP
   devem ser preservados/reautorizados: o Brevo está vinculado ao IP autorizado.
5. Aprovar separadamente040, publicação do núcleo, envios controlados e workers.

## Homologação real mínima no site principal — só depois dos gates

- Núcleo: imagem9b e rollbackB2 compatível040; confirmar API/banco, cadastro,
  persistênciaCRM/Agenda, owner/viewer e troca BellaStore↔BrilhoLimpeza.
- E-mail: destinatários controlados aprovados; um envio por fluxo (até4, incluindo
  OTP público). Verificação/link de uso único; recuperação com revogação e novo
  login; convite aceito/revogado; OTP sem reserva antes de confirmar. Registrar
  recebimento real, não só aceitaçãoSMTP. Não registrar links/tokens ou conteúdo.
- Antes do worker, conferir fila e exclusividade; nenhuma mensagem fora do escopo
  aprovado. `--limit 1` NÃO seleciona destinatário e não é proteção de canário.
  Se houver outros jobs elegíveis, parar e obter conciliação/autorização específica.
- WhatsApp: em cada negócio autorizado, mensagem nova→menu→catálogo→voltar→humano;
  bot pausado durante resposta manual; retomada explícita; reserva única naAgenda.
- Instagram: perfil correto, Direct novo→menu→serviço→reserva→Caixa/Agenda→humano.
  BellaStore tem histórico; BrilhoLimpeza ainda exige prova real completa.
- No mesmo negócio, slot reservado por um canal indisponível nos demais; no outro,
  clientes/conversas/reservas nunca aparecem. Não reenviar eventos antigos/incertos.

Falha de persistência/isolamento/duplicação ou resultado de envio incerto interrompe
ativação; manter filas/dados, sem retry cego. Autenticação de domínio próprio
(SPF/DKIM/DMARC) melhora entregabilidade; o Gmail em spam não bloqueia o preparo.
