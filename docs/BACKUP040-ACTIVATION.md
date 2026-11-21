# Backup da base efetiva: ativação pendente

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

O timer preparado usa `--with-manifest`. Na configuração privada aprovada, preencher `export_helper_image_id` com o ID imutável já carregado e `export_source_dsn` com a URI privada do mesmo database pelo loopback do namespace PostgreSQL (`sslmode=disable`, sem opções adicionais). O runner confirma a base, impede imagens ausentes/mutáveis, não passa credenciais em argumentos e limita o helper a256MiB/0,5CPU. A exportação tem limite externo de180s; em falha remove somente o helper identificado por nome, label e namespace próprios, preservando a base e os arquivos parciais. O recibo periódico inclui o hash do manifesto. A rotina histórica continua usando seu caminho anterior, sem essa flag.
