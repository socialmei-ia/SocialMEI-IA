# Preparação PostgreSQL próprio AWS — 12/11/2026

## Estado

**Destino de recuperação preparado e validado com snapshot histórico. Corte
definitivo BLOQUEADO e não executado.** A produção continua no Prisma; não houve
alteração de suas conexões, dados, credenciais, schema ou plano. Nenhuma migration
foi criada, editada ou executada. Não foram criados registros fictícios para
substituir dados reais.

Evidência sanitizada da coleta final:
[postflight](evidence/20261112-aws-postgres-preparation.json).

## Origem efetiva e backups

A API `socialmei-team-team-api-1`, a API WhatsApp
`socialmei-menu-public-api-v3` e o worker `socialmei-instagram-menu-worker`
usam Prisma. O sender WhatsApp chama a menu API por HTTP. Recuperação por e-mail
também usa conexão própria quando habilitada; não herda automaticamente um
overlay privado da API.

O PostgreSQL local existente não é a origem autoritativa. A ferramenta antiga
`team-maintenance.py backup` grava esse banco local, portanto seus dumps diários
não certificam as gravações recentes do Prisma.

Foi tentado `pg_dump`17 pela conexão efetiva da API, com `verify-full` e o mesmo
bundle de CAs confiáveis do container. Resultado final: **planLimitReached**,
sem exportação. As tentativas iniciais encontraram diferenças de CA entre a
imagem do cliente e a API; a confiança foi transportada sem reduzir TLS.
Nenhuma tentativa final contornou a restrição do provedor.

Backup Prisma comprovado disponível:

- Arquivo privado: `/home/ubuntu/.socialmei-instagram-86cdd5b/backup/prisma.dump`.
- Data do arquivo: **11/11/2026 20:19:29 UTC**.
- SHA-256: `0076d3b68ac8f50306b04f671b4eec1c6708ee62c79a9b1a9749be910979708c`.
- Snapshot schema038, 74 tabelas, 594 registros.
- Original preservado, checksum conferido contra recibo anterior.

Esse snapshot é anterior ao schema039 e às gravações posteriores. O número de
registros atuais e a diferença desde o backup são desconhecidos enquanto a
origem permanecer bloqueada. Não autoriza perda de dados nem substituição da
produção por uma cópia antiga.

## Destino criado

- Container: `socialmei-postgres-relocation-20261112`.
- PostgreSQL17.11, imagem imutável
  `sha256:ff87138949ad9a46f32ff23bd6852b52ce024a13dffe9b4087be98292cdd3b4f`.
- Diretório privado: `/home/ubuntu/.socialmei-postgres-relocation-20261112`.
- Database principal de preparação: `socialmei_relocation`; bases adicionais
  preservadas para ensaios de restauração.
- Rede Docker exclusiva e `internal`, nenhuma porta publicada e nenhuma rede
  de produção conectada. Containers de teste sem saída para provedores.
- TLS obrigatório no HBA, cliente com `verify-full`, CA privada própria e
  certificado com SAN do hostname do destino; validade de 365 dias na preparação.
  Prova negativa também executada: conexão sem TLS recusada pelo HBA.
- Usuário da aplicação sem superuser, criação de roles/bancos ou replicação;
  permissões DML e sequências concedidas sobre os objetos existentes.
- Checksums de páginas habilitados; `no-new-privileges`, capabilities removidas,
  sistema de arquivos do container somente leitura com mounts específicos.
- Reinício `unless-stopped`, limite de 192MiB e 0,35CPU **para ensaio**. Não é
  dimensionamento aprovado para produção. Database principal aproximadamente13MB.

A restauração inicial completa abortou em transação porque a extensão de
infraestrutura `prisma_postgres` não existe no PostgreSQL comunitário. A segunda
restauração omitiu exatamente duas entradas do índice: essa extensão e seu
comentário. Essa mesma exclusão constava do ensaio certificado anterior do
backup. Não houve filtro de tabelas/dados ou mudanças estruturais na aplicação;
o dump original completo permanece intacto. Ownership/ACL do destino foram
configurados para roles próprias, preservando os usuários e credenciais de
login da aplicação como registros do banco.

## Validação executada

1. Restauração transacional do snapshot038 em destino vazio.
2. Manifesto em transação `REPEATABLE READ READ ONLY`, formatos/fuso fixos,
   `row_security=off` com falha fechada. Hash ordenado de todos os registros por
   tabela, preservando duplicatas; catálogo de colunas, constraints, índices,
   triggers, funções, políticas, enums/domains e extensões.
3. Verificação de **135 FKs, zero violações**, incluindo FKs compostas de negócio.
4. Preservação de **21 sequências**, definições, ownership e `is_called`.
5. **Zero large objects**; a ferramenta bloqueia certificação se encontrar algum.
6. Novo dump do destino, SHA-256, índice conferido, restauração em outra database
   isolada e comparação integral dos manifestos: **igual**, sem seções divergentes.
   Foram preservadas 74 tabelas e594 registros, inclusive dados de contas,
   sessões, clientes, canais, mensagens e agenda contidos naquele snapshot.
7. API, menu WhatsApp, worker Instagram e recuperação consultaram o **mesmo
   database e endereço de servidor, todos por TLS**, com as imagens instaladas.
8. Aplicação instalada executada internamente contra o destino: `/health`200,
   `/health/db`200, `/api/v1/auth/session`200 e CRM sem autenticação401.
9. **23 testes offline novos aprovados**, cobrindo manifesto, bloqueio de large
   objects, falhas de backup, gates de segurança e cópia externa. Revisão
   independente aprovou a preparação e identificou limites mantidos no relatório.

Não houve envio WhatsApp/Instagram/SMTP, reivindicação de filas ou criação de
clientes/agendamentos. Os workers foram configurados e tiveram a conexão
validada em processos de prova; não foram iniciados como respondedores contínuos.
O isolamento por FKs não substitui teste de autorização autenticada entre
negócios. Agendamento concorrente entre canais, login/reset com credenciais de
teste controladas e envio real permanecem pendentes de cópia atual e homologação.
A candidata039 não foi certificada usando o snapshot038.

## Backups e cópia externa

- Timer novo `socialmei-postgres-relocation-backup.timer`: por hora, persistente
  após reinício. Primeiro serviço executado com sucesso.
- Dump inicialmente `.partial`, fsync, validação de índice, promoção somente
  após sucesso e recibo SHA-256. Sem remoção automática de backups antigos.
  Arquivos incompletos nunca são selecionados como cópia válida.
- Pacote de preparação, dump original e último dump válido copiados para fora
  da AWS, com tamanho/SHA-256 conferidos novamente no computador.
- Destino: `%LOCALAPPDATA%/SocialMEI-Database-Backups/postgres-relocation-20261112`,
  fora do Git/OneDrive, DACL protegida somente para o usuário corrente.
- Pacote privado preserva configurações/ambientes inspecionados, keyrings que
  constam desses ambientes, certificados e scripts da preparação. Não substitui
  backup integral dos volumes WAHA/n8n e de outros mounts externos.
- Task Windows `SocialMEI PostgreSQL relocation external backup`, diária às03:30
  e no logon, sem senha armazenada. Execução de prova: **LastTaskResult=0**.
  Depende do computador ligado e usuário conectado; não é proteção remota24x7.
- S3: listagem/criação/configuração negadas pela role AWS. Nenhum bucket ou
  upload foi confirmado. Ferramenta preparada para bucket privado com bloqueio
  público, criptografia, versionamento, transporte HTTPS e leitura de volta
  para conferir hash; falta permissão/armazenamento autorizado.

Todos esses backups novos representam o destino histórico, não a produção
atual. Dumps, tokens, credenciais e manifestos completos permanecem privados.

## Capacidade, segurança e custos

Instância existente: `t3.small`, região `sa-east-1`, 2vCPU, cerca de1,9GiB RAM.
Na primeira inspeção havia aproximadamente471MiB disponíveis, swap usada em
cerca de1,4GiB e20GiB livres no filesystem de58GiB. A carga de CPU estava baixa.
Após os ensaios havia aproximadamente491MiB disponíveis; as provas de aplicação
rodaram uma por vez e encerraram seus containers.

Não foi criada nova EC2, EBS ou RDS nem alterado o tamanho da instância. O banco
usa armazenamento já alocado; isso não prova custo adicional zero, pois créditos
T3, tráfego e crescimento dos backups podem alterar a fatura. Não houve compra
de plano Prisma ou compromisso de capacidade. A role negou leitura EC2/S3;
tipo/criptografia do EBS, regras completas dos security groups e faturamento
efetivo não puderam ser certificados. A ausência de porta publicada e a rede
interna do destino foram verificadas por Docker.

A memória está apertada para receber carga definitiva junto com todos os
serviços. Antes do corte, definir orçamento/capacidade e comprovar folga sob carga
representativa; avaliar ao menos4GiB ou host dedicado sem redimensionar
automaticamente. Confirmar criptografia do volume e backup externo independente
do computador. Preços devem ser conferidos na conta/calculadora oficial; não há
estimativa de fatura certificada nesta preparação.

## Fontes e recuperação oficial do Prisma

O [erro oficial](https://www.prisma.io/docs/postgres/error-reference#your-account-has-restrictions-planlimitreached)
confirma que `planLimitReached` bloqueia consultas sem apagar os dados. A opção
de liberação por24h existe uma única vez por workspace, se ainda disponível;
caso já consumida, solicitar liberação/exportação ao suporte. Não foi ativada
janela nem contratado plano automaticamente.

O [procedimento oficial de backup](https://www.prisma.io/docs/postgres/database/backups)
usa `pg_dump` com conexão direta. Snapshots automáticos dependem do plano e
não garantem recuperar gravações posteriores. Não restaurar snapshot sobre a
origem; obter exportação atual ou, quando disponibilizado pelo provedor,
recuperação em outra base. Não foi usada API de restauração/destruição do Prisma.

## Procedimento preparado para a futura troca

**Nenhum dos passos de corte abaixo foi executado. Não executar enquanto houver
um bloqueio ou sem confirmação explícita do responsável.**

1. Restabelecer exportação oficial do Prisma, conferir identidade efetiva e
   gerar dump atual consistente. Não usar o snapshot038 para substituir a origem.
2. Restaurar em **outra database nova e vazia**, preservando exatamente o ledger
   atual (esperado039, a confirmar), sem aplicar migrations ou juntar diferenças
   por nome. Verificar dependências de extensões e permissões com a cópia atual.
3. Repetir validação integral de dados/estrutura/sequências e prova de restauração
   externa. Preparar capacidade, TLS, backup remoto24x7 e alertas de falha.
4. Homologar candidata/imagens exatas contra essa cópia. Com contatos e contas
   controlados, testar autenticação/recuperação, CRM, Bella/Brilho, WhatsApp,
   Instagram, agendamento e disputa pelo mesmo horário. Manter remetente único;
   não consumir ou reenviar filas históricas para contatos reais.
5. Registrar imagens, envs, mounts, redes, keyrings, registros, journals e spools
   atuais, sem imprimir segredos. Validar configurações de destino dos quatro
   consumidores e de outros jobs/integrações identificados; a URL da menu API é
   independente da URL da API principal.
6. Apresentar resultado e obter confirmação do corte e janela. Preparar manutenção
   de escritas humanas e pausa coordenada de produtores/consumidores. Antes de
   parar, conciliar envios em andamento/incertos; preservar ingresso durável e
   eventos novos sem confirmar processamento que ainda não foi persistido.
7. Com escritores parados, verificar transações ativas, registrar fronteira final,
   gerar **dump final** e manifesto da origem no estado quiescente. Restaurar em
   nova base vazia e comparar com a origem, inclusive sequências. RPO pretendido0;
   discrepância, ingresso não reconciliado ou exportação bloqueada impedem avanço.
8. Trocar somente conexões dos serviços necessários para a mesma base, sem
   migrador e sem recriar WAHA/n8n/volumes. Começar com envios desativados; verificar
   readiness, login, leitura/uma operação controlada e persistência. Então liberar
   um consumidor por conta e acompanhar filas/recibos antes de abrir tráfego.
9. Preservar Prisma e configurações anteriores. Antes de novas escritas, rollback
   de conexão pode voltar ao estado anterior, se a origem estiver saudável. Após
   qualquer escrita no destino, simples troca de URL pode perder dados: congelar
   escritores, preservar ambos os bancos, exportar diferenças e reconciliar sob
   nova aprovação. Nunca sobrescrever a origem ou repetir envios incertos.

## Rollback da preparação e limites de aprovação

Como produção não mudou, não há conexão a reverter agora. O postflight comparou
imagem, Config, HostConfig e Mounts dos três consumidores de produção com a
captura anterior: todos iguais. Não confundir isso com auditoria completa de
todas as redes ou com origem funcional enquanto o Prisma estiver bloqueado.

Para retirar somente a preparação: desabilitar/parar o timer novo, parar o
container `socialmei-postgres-relocation-20261112` e desabilitar a task Windows
nova. **Manter diretórios, databases, dumps, certificados e recibos**, sem apagar
volumes ou restaurar sobre produção. O ciclo dump/restauração do destino foi
comprovado; rollback após escritas futuras de produção ainda exige o gate acima.

Faltam para autorizar a troca: dados atuais acessíveis e copiados, comparação com
a origem final, schema039 real preservado, homologação completa, capacidade e
backup remoto contínuo aprovados e confirmação humana do corte.

### Permissões externas pendentes — continuação funcional

Sem aplicar políticas IAM nesta execução. Para um bucket aprovado e privado,
a role de backup precisa de s3:ListBucket no ARN do bucket e s3:PutObject e
s3:GetObject somente no prefixo postgres-relocation/*. GetObject também
autoriza HeadObject e a leitura de volta para verificar SHA; não é necessária
permissão de exclusão. Para multipart de dumps maiores, incluir
s3:AbortMultipartUpload e s3:ListMultipartUploadParts no mesmo prefixo.

A preparação inicial do bucket, sob aprovação do responsável e por identidade
administrativa separada, exige s3:CreateBucket,
s3:PutBucketPublicAccessBlock, s3:PutEncryptionConfiguration,
s3:PutBucketVersioning e s3:PutBucketPolicy. Não iniciar criação com novos
custos sem a autorização específica exigida na continuação atual.
SSE-S3/AES256 não necessita de permissões KMS.

Para completar a inspeção sem alterar a EC2: ec2:DescribeInstances,
ec2:DescribeVolumes, ec2:DescribeSecurityGroups, cloudwatch:GetMetricData e
cloudwatch:ListMetrics. Custos faturados exigem acesso de leitura à cobrança,
como ce:GetCostAndUsage, autorizado pelo responsável da conta.
