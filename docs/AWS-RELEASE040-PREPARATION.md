# Preparação AWS — continuação de edc12d3

Somente código local, testes e propostas. Nenhum recurso criado, stop/start,
redimensionamento, upload real, migration, troca de banco ou publicação.

## Entregas utilizáveis

- `deploy/team/postgres-backup-bucket.cloudformation.json`: bucket sa-east-1
  privado, quatro bloqueios públicos, ownership enforced, AES256, versionamento,
  política HTTPS e Retain em exclusão/substituição. Sem expiração/exclusão de dados.
  Não foi submetido à AWS; o nome aprovado é obrigatório e não tem default.
- `postgres-backup-iam.example.json`: papel operacional separado do bootstrap,
  objetos limitados a postgres-relocation/*, leitura da versão exata e das
  propriedades de segurança do bucket. HTTPS obrigatório, semCreate/Delete.
  Os ARNs são placeholders, não permissões instaladas.
- `tools/aws-postgres-backup.py`: verifica owner/bucket privado/versionado/AES256
  antes de upload, restringe endpoint ao S3 regional AWS, usa chave por SHA256 e
  PUT condicional. Checkpoint privado fsync permite reconciliar envio incerto por
  HEAD sem rePUT automático; GET fixa VersionId e confere tamanho/hash.
  O recibo local sobrevive à falha externa. Não envia os33 históricos em lote.
- A rotina horária existente pode usar esse código após instalação/configuração
  explicitamente autorizadas; nada foi instalado. O produtor permanece preso ao
  destino **histórico**, não foi redirecionado ao Prisma ou promovido a backup atual.
- `tools/postgres-external-backup-plan.py`: plano e simulações sintéticas de
  negação, corrupção, repetição e reinício; schemas038/039/040 sem migrations.
- `tools/backup-restore-rehearsal.py`: default apenas plano. Execução futura exige
  dump local, manifesto privado e autorização explícita vinculada aos dois SHA256s
  e imagem PG local imutável. Exemplo de autorização tem valorfalse.
  Cria somente containers próprios sem rede/portas/volumes reais, restaura em uma
  base nova e compara tabelas, estrutura, FKs, ledger e sequências usando o
  validador existente. Cleanup confere ownership; não aceita DSN externa.
  Igualdade/restauração não comprova frescor nem privilégios mínimos da produção.
- O inventário ignora checkpoints external.private.json para não contá-los como
  novos backups. Não houve nova coleta geral.

## Permissões: fatos e mínimo necessário

`DescribeInstances` tinha negação documentada. Uma consulta nova, única, de
`DescribeInstanceTypes` também recebeu UnauthorizedOperation, sem retry.
Listagem globalS3/criação tinham negação resumida. Isso NÃO prova negação dos
GETs/PUTs seguintes: os scripts antigos interrompiam a sequência no primeiro erro.
Demais permissões permanecem desconhecidas; nenhuma chamada negada foi repetida.

O responsável pode executar com identidade própria ou delegar:

1. **Inspeção:** `aws-readiness-readonly-iam.example.json` na identidade de operação,
   ou fornecer inventário equivalente. Permite conferir tipos, zona, volumes,
   grupos, IPelástico e atributos sem alterá-los. Describe exigeResource*;
   a proposta restringe a região. Não inclui escrita, billing ou acesso administrativo.
2. **BootstrapS3:** aprovar nome/custo e criar o bucket via template revisado.
   A listaS3 do plano inclui ownership, publicblock, encryption, versioning, policy
   e tagging; o caminhoCloudFormation tem permissões próprias separadas. Papel de
   backup não precisa criar buckets nem listar todos os buckets da conta.
3. **Backup:** anexar política prefixada, preencher bucket/expected_bucket_owner
   somente no arquivo privado e autorizar instalação da rotina e transferência.
   Validar propriedades, upload controlado, versão/readback e restauração antes
   de aceitar a proteção como operacional. Restore periódico exige manifesto
   correspondente ao dump e fronteira consistente de escritores.
4. **Ampliação:** aprovar orçamento e janela. `ec2-resize-iam.example.json` limita
   stop/start a uma instância e ModifyInstanceAttribute ao atributoInstanceType,
   nos tipos revisados (inclui rollback). Validar a política na conta antes de uso.
   Não concedeRunInstances/Terminate/ModifyVolume/PassRole nem criação de snapshots.

Nenhuma permissão de catálogo de preços é necessária: o recibo existente veio do
catálogo público AWS. Créditos, descontos e faturamento real continuam desconhecidos.

## Ampliação segura preparada

`tools/aws-release040-preparation.py --prices docs/evidence/20261113-aws-instance-prices.json`
gera plano sanitizado; não possui modoexecute/apply. Checklist privado opcional
não é ecoado e campos ausentes permanecem bloqueios. Mesmo completo, não autoriza.

Referência já consultada: t3.medium4GiB US$49,06/730h; t3a.medium4GiB US$44,17.
Incrementos sobre t3.small: US$24,53 eUS$19,64. Só computação Linux on-demand,
sa-east-1; exclui EBS, snapshots, IPv4, CPUextra, S3, tributos e descontos.
Preferência inicial: t3.medium, mesma família. Não requer rebuild das imagensamd64.

Antes de qualquer stop: comprovar tipo original, EBS de TODOS os estados/volumes,
ENA/HVM, disponibilidade na zona, controladores externos, IPelástico ou planoDNS,
backup restaurável e manifestos privados de mounts/restart policies/sessões/filas.
Snapshot/AMI novo exige autorização/custo próprios. Não presumir preservação do
IPv4 efêmero; não alocarEIP nem alterarDNS por iniciativa automática.

Atualização Brevo: o responsável vinculou o SMTP ao IP de saída AWS autorizado.
O checklist agora exige revisar essa autorização depois de stop/start; DNS
preservado não comprova que o Brevo aceitará um IP novo. Não alterar allowlist
automaticamente. Entrada privada e ativação em `BREVO-RELEASE040.md`.

Sequência futura: pausa coordenada autorizada de escritores/respondedores; parada
graciosa semforce; alterar sótipo; iniciar mesma instância; conferir volumes,
rede/IP/DNS, sessões e proprietários antes de retomar uma única vez; medir carga.
Rollback: mesmo procedimento para tipo original, com os volumes atuais; sem
restaurar dados antigos, substituir sessões, alterar banco ou publicar release.
ReadinessPrisma503 conhecida não é resolvida por aumentarRAM; comparar o baseline.

## Validação e bloqueios

58 testes direcionados aprovados; ajuste final do checklist validado no subconjunto
de6 testesAWS. Sem repetir regressões funcionais ou consultar preços novamente.
CloudFormation/IAM verificados localmente, ainda não validados pelo serviçoAWS.
Executorrestore:5 testes simulados; ensaioDocker não executado porque o daemonLinux
local está indisponível. Não foi iniciado, para não subir serviços existentes.

Continuam necessários dados atuais, permissões, autorização de custos/instalação,
inventárioEC2/IP, Docker isolado para restauração real e autorizações separadas de
transferência, stop/start e publicação. Produção e imagens permanecem preservadas.
