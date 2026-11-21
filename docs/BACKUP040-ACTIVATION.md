# Backup da base efetiva: ativação pendente

A inspeção de 21/11 confirmou que o timer histórico ativo usa `socialmei_relocation`, não `socialmei_candidate040_20261114`. Seus recibos têm `current_production_backup=false` e `external_uploaded=false`. Isso não comprova recuperação da base usada pela API.

Preparação local, sem instalação de serviços:

- `tools/aws-postgres-backup.py --run --config-root <diretório privado aprovado> backup` preserva o destino padrão histórico. A configuração explícita exige aprovação, permissões privadas e recibo de restauração vinculado ao hash do dump validado.
- Quando `current_production_backup=true`, uma consulta somente leitura verifica database exata, ledger 001–040 e PostgreSQL 17 antes de exportar. Divergência bloqueia o dump. O recibo registra identidade observada, schema inteiro e `restore_verified=false`: validar o índice do arquivo não equivale a restaurá-lo.
- `deploy/team/postgres040-backup.service.example` e `.timer.example` propõem uma unidade separada, com lock, limites de recursos e horário deslocado. Não sobrescrever nem remover a rotina histórica.

Antes da ativação, reconciliar a base efetiva, espaço, configuração privada e imagem PostgreSQL; obter aprovação do destino e da operação. Ensaiar restauração isolada e preservar o recibo privado. Instalar o script revisado e as unidades somente depois de aprovar seus hashes e o rollback. Reversão da agenda: desabilitar apenas o novo timer; preservar dumps e o timer histórico. Não restaurar sobre produção.

Armazenamento externo, monitoramento de falhas e recuperação independente ainda exigem configuração e comprovação. Reutilizar `tools/postgres-external-backup-plan.py` e o ensaio de restauração existente. Não criar bucket ou contratar serviço sem aprovação de custo. Esta preparação não ativa S3 nem declara backup produtivo operacional.
