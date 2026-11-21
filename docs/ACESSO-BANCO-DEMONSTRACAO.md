# Consulta segura ao banco efetivo

Inventário somente leitura de19/11/2026 (20/11 UTC). API e worker de recuperação:
PostgreSQL17.11 em Docker EC2, host interno `socialmei-postgres-relocation-20261112`,
database `socialmei_candidate040_20261114`, role de aplicação
`socialmei_candidate040` sem superuser/createdb/createrole/bypassrls. Não é evidência
de Amazon RDS. A EC2 é t3.small emsa-east-1 por metadata da instância.

O worker WhatsApp ativo chama `team-api:8000` por hotfix, portanto usa a API
acima. O serviço antigo de menu e o worker Instagram ainda usam Prisma;
ambas as consultas de leitura falharam com OperationalError. O primeiro não é
o destino HTTP atual do worker WhatsApp. Não usar o banco histórico n8n ou
socialmei_team como se fosse o banco efetivo.

## O que já pode ser consultado

O responsável com SSH autorizado pode executar o inspector versionado por stdin
dentro do contêiner da API. Exemplo PowerShell, usando a chave já existente:

```powershell
Get-Content -Raw -Encoding UTF8 tools/inspect-mei-demo.py |
  ssh -i "$env:LOCALAPPDATA/SocialMEI-SSH/socialmei-aws-key.pem" -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu@54.94.213.7 'docker exec -i socialmei-team-team-api-1 python -B -'
```

Retorna tabelas/views, tamanhos, índices, ledger, roles técnicas, contagens por
workspace, estados de filas, referências órfãs, locks/atividade agregada e o
negócio fictício encontrado. Usa transação READ ONLY, timeout de8s e lock timeout
de1s. Não imprime nomes de clientes, e-mails, corpos de mensagens ou tokens.
Esse diagnóstico usa a conexão da aplicação; não é uma credencial humana
permanente e não deve ser distribuído ao professor/clientes.

## Acesso individual pendente de aprovação

`socialmei_team_readonly` não existe no banco efetivo. O modelo
`database/team-readonly-access.sql` não foi aplicado: foi escrito para tabelas
legadas e não cobre agenda, perfis, oportunidades e `me_*` atuais. Não aplicar
grants globais nem conceder tabelas de autenticação/payloads/jobs em bloco.

O preparo mínimo é um login individual sem privilégios administrativos, membro
de uma role NOLOGIN com SELECT em colunas/views explicitamente autorizadas.
Revisar memberships, grants herdados/PUBLIC e owner das views; somente consultar
dados de demonstração autorizados ou metadados agregados. Criar login/grants
exige aprovação operacional própria e backup das roles. Usar `\password` em
sessão privada, sem senha no comando, Git ou chat.

Após provisionamento aprovado, o caminho mais simples é SSH e `psql` **no
contêiner PostgreSQL**, com role individual e senha solicitada interativamente:

```text
docker exec -it socialmei-postgres-relocation-20261112 psql -h 127.0.0.1 -U SEU_LOGIN_READONLY -d socialmei_candidate040_20261114 -W
```

Esses privilégios ainda não estão provisionados. Não usar a role de aplicação
ou superuser compartilhada como solução permanente. Exemplos de consultas
permitidas após os grants específicos:

```sql
BEGIN READ ONLY;
SELECT version FROM socialmei.schema_migrations ORDER BY version;
SELECT schemaname, relname, n_live_tup, n_dead_tup
FROM pg_stat_user_tables WHERE schemaname='socialmei';
SELECT tablename, indexname FROM pg_indexes WHERE schemaname='socialmei';
ROLLBACK;
```

O pgAdmin instalado está ativo, mas seu único servidor salvo aponta para o
banco legado n8n, não para a API. Para aproveitá-lo, primeiro revisar a rede
Docker privada/TLS e cadastrar uma conexão individual ao database efetivo com
CA confiável, sem credencial compartilhada. Não alteramos pgAdmin/redes/5432.
Túnel SSH só deve terminar em loopback de endpoint privado aprovado; não existe
necessidade de abrir PostgreSQL à internet.

## Evidências e limites da auditoria

- Ledger001–040,78 tabelas,146FK, nenhuma constraint não validada.
- Zero órfãos nos seis vínculos verificados de vendas, conversas e agenda.
- Nenhum deadlock registrado e nenhuma transação longa na amostra; isto não é
  monitoramento contínuo. Estatísticas de varredura não provam índice ineficiente
  em tabelas pequenas; não remover índices com base nesta amostra.
- Ensaio local de dump/restore em database separado e descartável comparou
  tabelas, hashes, sequências, FKs, ledger, estrutura e grants com igualdade.
  Corrigida diferença textual de cast ARRAY em CHECK com regex contendo `$`;
  alterações semânticas continuam reprovadas. Isso não certifica restore da
  produção nem backupS3. Fonte/restauração foram exclusivamente sintéticas.
- Ledger guarda nomes/data, sem checksum. Cadeia correta não certifica conteúdo
  dos arquivos historicamente aplicados. Nenhuma migration foi executada.
- RLS desativado; isolamento atual depende das sessões, consultas e FKs compostas.
  A regressão testa IDs cruzados; não introduzimos RLS invasivo neste incremento.
- Backup horário local ativo com178recibos, último hash/tamanho conferidos. O
  recibo ainda se identifica como destino histórico e `current_production_backup=false`.
  Não certifica backup atual nem restauração040.
- Configuração S3 ausente na rotina inspecionada; ListBuckets AccessDenied e
  EC2DescribeInstances UnauthorizedOperation. Nenhum recurso cobrado foi criado.
  Existência/versionamento/cifragem/restore de outro bucket não confirmados.

Já existem templates S3/IAM e ferramentas em `deploy/team/postgres-backup-*`,
`tools/postgres-external-backup-plan.py`, `tools/backup-restore-rehearsal.py`.
Antes de ativar: selecionar explicitamente database040, exportação consistente,
versionamento/cifragem/bloqueio público, retenção, upload+readback por hash,
restore em destino separado e alarme por falha/atraso. Não reutilizar como prova
o dump histórico038. Estimativa depende de volume/retensão/região e orçamento;
nenhum recurso ou compra foi autorizado nesta entrega.

Estimativa de planejamento: a [tabela oficial regional AWS](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/sa-east-1/index.json),
consultada em20/11/2026UTC, informa S3Standard sa-east-1 aUS$0,0405/GB-mês,
PUT/LIST aUS$0,007/1.000 e GET aUS$0,00056/1.000. Com **1GB retido**,1.000PUT
e1.000GET/mês, o subtotal ilustrativo éUS$0,04806/mês. Volume futuro, versões,
configurações, restore, logs, alarmes, tráfego, câmbio e impostos devem ser
orçados separadamente; não é previsão da fatura completa nem preço de EC2.
O dump histórico medido tem447.575bytes, mas não dimensiona um backup atual040.

Permissões mínimas do executor no bucket/prefixo aprovado: GetBucketVersioning,
GetEncryptionConfiguration, GetBucketPublicAccessBlock, GetBucketOwnershipControls;
ListBucket limitado ao prefixo; PutObject, GetObject e GetObjectVersion só nos
objetos desse prefixo, exigindoTLS. O template existente não concede DeleteObject
nem administraçãoIAM/EC2. Criação do bucket/política usa autorização separada do
provisionador de infraestrutura. Não mudar o prefixo histórico em uso sem revisão.
Para monitorar: registrar horário do último backup040 confirmado, verificar idade
máxima, bloquear execução simultânea e ligar OnFailure a um destino autorizado,
sem anexar dump, credenciais ou conteúdo de clientes ao alerta.
