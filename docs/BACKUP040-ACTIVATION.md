# Backup da base efetiva

## Estado operacional em 21/11/2026

O timer separado `socialmei-postgres040-backup.timer` foi instalado e ativado mediante aprovação da operação `c1ca8494a420`. O primeiro ciclo exportou `socialmei_candidate040_20261114`, schema040, com TLS `verify-full`, snapshot compartilhado e validação de hashes. O timer histórico e os containers da aplicação foram preservados. [Evidência sanitizada](evidence/20261121-backup040-automatic-active.json).

Os recibos e arquivos ficam protegidos na AWS. O relatório de retenção não exclui cópias; o alerta de falha usa o journal local. Armazenamento externo e entrega externa de alertas continuam pendentes. Na ativação inicial, verificou-se apenas a integridade do arquivo. A restauração posterior da mesma cópia está comprovada abaixo; a prova anterior também permanece preservada.

Rollback autorizado: desabilitar somente `socialmei-postgres040-backup.timer`, preservando dumps, recibos e a rotina histórica. Não restaurar sobre produção. Não repetir o instalador nem o primeiro ciclo para continuar uma sessão.

A cópia produzida pelo primeiro ciclo da rotina nova também foi restaurada em Docker local isolado, sem rede: 78 tabelas, 21 sequências e 1.002 registros conferem com o manifesto. O ensaio não restaurou nem alterou produção. [Prova sanitizada](evidence/20261121-backup040-timer-copy-restored.json).

`backup-restore-rehearsal.py --run --dump <dump> --manifest <manifesto> --approval-receipt <aprovação privada> --restoration-proof <recibo privado> --package-output <arquivo privado.tar>` prepara um conjunto portátil com os três arquivos e um índice de hashes. Exige prova integral da restauração do mesmo dump, destino privado fora do Git e arquivo novo. Não inclui a configuração de conexão, não sobrescreve cópias e não envia ao provedor. O pacote contém o banco completo e deve permanecer privado. Cópia externa automática segue pendente.

O primeiro disparo agendado foi observado em 21/11/2026 às 18:17:39 (-03), sem execução manual: segundo backup concluído, retenção sem exclusões. Essa cópia agendada também foi restaurada integralmente em ambiente isolado, com 78 tabelas, 21 sequências e 1.002 registros comparados ao manifesto. [Evidência](evidence/20261121-backup040-scheduled-restored.json). Nenhuma restauração foi aplicada em produção.

## Histórico da preparação

O texto abaixo registra as etapas anteriores à ativação; o estado acima e os recibos operacionais prevalecem.

A inspeção de 21/11 confirmou que o timer histórico ativo usa `socialmei_relocation`, não `socialmei_candidate040_20261114`. Seus recibos têm `current_production_backup=false` e `external_uploaded=false`. Isso não comprova recuperação da base usada pela API.

Preparação local, sem instalação de serviços:

- `tools/aws-postgres-backup.py --run --config-root <diretório privado aprovado> backup` preserva o destino padrão histórico. A configuração explícita exige aprovação, permissões privadas e recibo de restauração vinculado ao hash do dump validado.
- Quando `current_production_backup=true`, uma consulta somente leitura verifica database exata, ledger 001–040 e PostgreSQL 17 antes de exportar. Divergência bloqueia o dump. O recibo registra identidade observada, schema inteiro e `restore_verified=false`: validar o índice do arquivo não equivale a restaurá-lo.
- `deploy/team/postgres040-backup.service.example` e `.timer.example` propõem uma unidade separada, com lock, limites de recursos e horário deslocado. Não sobrescrever nem remover a rotina histórica.

Antes da ativação, reconciliar a base efetiva, espaço, configuração privada e imagem PostgreSQL; obter aprovação do destino e da operação. Ensaiar restauração isolada e preservar o recibo privado. Instalar o script revisado e as unidades somente depois de aprovar seus hashes e o rollback. Reversão da agenda: desabilitar apenas o novo timer; preservar dumps e o timer histórico. Não restaurar sobre produção.

Armazenamento externo, monitoramento de falhas e recuperação independente ainda exigem configuração e comprovação. Reutilizar `tools/postgres-external-backup-plan.py` e o ensaio de restauração existente. Não criar bucket ou contratar serviço sem aprovação de custo. Esta preparação não ativa S3 nem declara backup produtivo operacional.

Retenção: `python tools/backup-retention.py --directory <backups privados>` verifica hashes e propõe preservar as últimas 24 cópias, uma diária por 14 dias e uma semanal por oito semanas. Não apaga arquivos. Cópias antigas só ficam elegíveis com recibo de restauração independente, hash e versão externa correspondentes. Recibos históricos ou inválidos são preservados. O alarme `postgres040-backup-alert.service.example`, ligado por `OnFailure`, registra prioridade crítica no journal sem conteúdo privado. Entrega externa do alerta continua dependente de um destino autorizado.

## Exportação e restauração conectadas

`deploy/team/Dockerfile.backup040` reúne clientes PG17, Python e o validador existente. O exportador aceita `--profile 040` e confere exatamente os nomes das migrations001–040. Dump e manifesto compartilham o snapshot; alteração de sequência durante a cópia impede promover o arquivo parcial. Isso não comprova que todos os escritores estiveram parados.

O padrão remoto continua exigindo TLS `verify-full`. `--isolated-loopback` aceita exclusivamente `127.0.0.1` com transporte local explícito: usar o helper revisado no namespace do contêiner PostgreSQL confirmado, sem publicar portas, com configuração privada e destino novo fora do Git. Não encaminhar o banco pela internet ou usar a opção com outro host.

Após aprovação do export, os arquivos `source.dump` e `source-manifest.private.json` alimentam diretamente `backup-restore-rehearsal.py`, com aprovação própria vinculada aos hashes. Exigir `full_comparison`; o recibo nativo resultante já é aceito pelo gate do backup. A imagem do próprio helper pode validar a restauração, dispensando uma segunda imagem da API. Tudo foi ensaiado com a cadeia040 real e dados sintéticos em contêineres locais isolados; exportação/restauração produtivas, agenda e cópia externa não foram executadas.

O timer preparado usa `--with-manifest`. Na configuração privada aprovada, preencher `export_helper_image_id` com o ID imutável e `export_source_dsn` com a URI do database efetivo. A AWS exige TLS: usar `export_transport=tls_verify_full`, hostname do PostgreSQL, `sslmode=verify-full` e `sslrootcert=/certs/source-ca.crt`. O arquivo local da CA é informado em `export_tls_ca_file`, com hash fixado em `export_tls_ca_sha256`, e montado somente para leitura. Nunca alterar HBA ou desabilitar SSL para executar a cópia. O modo `isolated_loopback` permanece disponível apenas para destinos previamente revisados que aceitem esse transporte.

O runner confirma a base, impede imagens ausentes/mutáveis, não passa credenciais em argumentos e limita o helper a256MiB/0,5CPU. A exportação tem limite externo de180s; em falha remove somente o helper identificado por nome, label e namespace próprios, preservando a base e os arquivos parciais. O recibo periódico inclui o hash do manifesto. A rotina histórica continua usando seu caminho anterior, sem essa flag.

Compatibilidade preparada para a transferência WhatsApp: após uma migration041 especificamente autorizada, o backup pode selecionar explicitamente `schema=041` e `source=approved_schema041_destination`. Isso exige o ledger completo041, imagem compatível e recibo nativo de restauração041 vinculado ao dump. A configuração040 continua estrita: não há transição automática nem aceitação de um recibo040 para aprovar041. Ambos os perfis passaram na exportação/restauração isolada com a cadeia real de migrations; essa capacidade nova não altera o lote operacional congelado em `dbd8ed4`.
