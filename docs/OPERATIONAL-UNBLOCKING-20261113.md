# Missão4 — resultado operacional, sem publicação

Base `b66703e`; coleta em14/11 01:13:48UTC (13/11 22:13:48Fortaleza).
Nenhum deploy, restart, limpeza, SQL, exportação, envio ou mudança AWS.

## Capacidade observada

2vCPU,5,01% na amostra; RAM1.905MiB, disponível533MiB.16 containers ativos,
27 inativos. Cgroups:999MiB residentes incluindo cache/kernel,1.501MiB em swap;
host:1,55GiB em swap. Em3s: swapin/out e majorfaults0, PSI0; não há evidência
de thrashing nessa janela nem eventos OOM observados. Não é ensaio sob carga.

| Serviço         | RAM atual MiB | Swap MiB | Papel/ação futura                                                |
| --------------- | ------------: | -------: | ---------------------------------------------------------------- |
| WAHA existente  |         358,9 |    591,5 | Preservar até identificar sessões e dependências                 |
| n8n             |         310,9 |     85,2 | Orquestração existente, com runner Python                        |
| GOWS piloto     |          60,9 |    241,3 | Sessões próprias; não trocar motor ou duplicar respondedor       |
| API principal   |          40,1 |     41,3 | Conexão configurada Prisma                                       |
| pgAdmin         |          38,6 |    209,3 | Administração opcional; parar exige autorização                  |
| Três PostgreSQL |          82,5 |    109,2 | Stack/equipe/destino histórico; nenhum substitui o Prisma da API |

12 serviços ativos não têm limite; reservas configuradas são0. Limites não são
RAM alocada. Parados não consomem RAM de processos; preservá-los para rollback.
Gateway público Caddy e gateway da equipe são necessários. Menu API/worker
WhatsApp, edgeGOWS e workerInstagram preservam o piloto; não criar concorrentes.
API Python legada e bancos locais precisam de confirmação de uso antes de remoção.

Imagem9b existente, sem rebuild: importação isolada de API/identity/recovery/IG
atinge76–77MiB por processo, sem tráfego ou SQL. Planejamento para manter stack e
adicionar PostgreSQL útil +4workers: aproximadamente500–912MiB adicionais,
mais384MiB de folga operacional. São bandas de planejamento, não carga medida.
2GiB não está aprovado;4GiB é a primeira faixa recomendada para ensaio autorizado.
Não há preço, saldo de créditos CPU ou capacidade sob carga certificados.

Proposta **não aplicada**: `deploy/team/release040-capacity.example.yaml`.
Limites somam1.376MiB, reservas544MiB; não incluem o PostgreSQL externo nem os
serviços antigos. Renderização+preflight aprovaram só6 mudanças de memória,
preservando imagens, banco, redes e flags. Limitar memória não substitui capacidade.

## Saúde, dados e configuração

- API instalada86cdd5b: `/health`200; Dockerunhealthy, readiness503 nos registros.
  Healthcheck periódico existe. Não foi localizado defeito independente nele.
  Amostra atual não contém `planLimitReached`; recibo anterior confirma
  `provider_account_limit` e exportação0bytes. Não houve nova consulta ao banco.
- API/menu têm host/porta/banco/usuário/senha/chaves de parâmetros iguais na
  configuração; isso não comprova identidade/schema/dados ao vivo. Strings DSN
  diferentes não foram tratadas como bancos diferentes.
  -33backups locais do destino **histórico**; último447.575bytes com SHA/tamanho
  conferidos. Timer ativo e último serviço com sucesso. A primeira leitura sem
  privilégio foi inconclusiva; leitura restrita de metadados como root resolveu.
- S3 não configurado. IAM permanece dependência externa, sem repetir operações
  anteriormente negadas. Cópia Windows/restauração anteriores são históricas;
  não comprovam backup externo contínuo atual nem proteção integral de WAHA/n8n.
- `postgres-backup-iam.example.json` é proposta não aplicada: prefixo restrito,
  HTTPS, semDelete/Create. Bucket aprovado deve ser privado, criptografado,
  versionado e protegido por política; uploader usaAES256. Validar upload,
  leitura de volta e restauração. Nenhum desses acessos foi ativado.
- API e PostgreSQL destino não publicam portas; redes API/database/destino
  interno são privadas. Volumes WAHA/n8n, estado do workerIG e binds privados
  foram identificados sem copiar seus conteúdos. Preservar todos.
- Gateway monta `/etc/caddy/Caddyfile` por fora da imagem e seu hash difere da
  candidata. Comparação por `caddy adapt`, sem exportar configurações, confirmou
  diferença semântica: faltam7matchers públicos explícitos (incluindo publicbooking);
  nenhum matcher privado adicional foi encontrado. Isso não prova endpoint
  inacessível nem equivalência das demais políticas, pois há rotas genéricas.
- Preparado `release040-gateway-bind.example.yaml`: exige caminhos privados
  existentes e usa o Caddyfile versionado da imagem. Teste offline recusou bind
  antigo e aprovou modelo conciliado, removendo somente esse bind e preservando
  ambas as fontes privadas. Nada aplicado. Conferir caminhos/políticas e obter
  aprovação antes da mudança, sem copiar nem substituir credenciais.
- CamposSMTP_HOST/PORT/USER/PASSWORD/FROM estão ausentes/vazios no ambiente da
  API; modos identity/recovery ausentes. Isso não inspeciona outros arquivos ou
  serviços. Automações IG antigas já estão habilitadas: não herdar ativações
  cegamente na release040. Perfis novos devem continuar desligados.

## Ativação futura: gates e autorizações

1. Recuperar acesso à origem e dump atual; janela Prisma exige autorização própria.
2. Aprovar bucket/IAM, comprovar upload externo+readback+restauração da cópia atual.
3. Escolher capacidade: consolidação de serviços comprovadamente dispensáveis ou
   ampliação autorizada; testar carga e picos, sem ativar respondedores paralelos.
4. Aprovar040; confirmar identidade039, privilégios/locks e backup antes de aplicar.
5. Conciliar Caddy/overlays e consumidores; aprovar publicação e eventual troca de
   provedor separadamente. Usar IDs9b e fallbackB2 compatível040 já ensaiado.
6. Homologar login, pendentes, sessões, isolamento, CRM e Agenda; falha bloqueia avanço.
7. Cadastrar SMTP privado e autorizar destinatário controlado; testar recuperação,
   verificação e convites antes de habilitar workers.
8. Autorizar WhatsApp controlado e confirmar sessão, persistência e respondedor único.
9. Autorizar Meta/Instagram controlado, permissões e webhook; testar pausa humana.
10. Abrir empreendedores gradualmente, observando memória, filas, erros e backups.

Reverter somente imagens/configuração reconciliada e manter040/dados/filas.
Não fazer downgrade, restaurar backup histórico sobre gravações novas ou repetir
envios incertos. Evidência: `evidence/20261113-mission4-operational-readiness.json`.
