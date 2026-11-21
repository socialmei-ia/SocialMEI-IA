# Execução independente e correção HTTPS

Inventário restrito da execução instalada, sem alterações de serviços. O gateway personalizado e a API CRM233 continuam na AWS; não houve terceira publicação da Premium.

## O notebook não é o servidor

- Os17 contêineres ativos estão na EC2. Docker está ativo e habilitado no boot. Os28 caminhos de mounts inspecionados estão em ext4 no servidor, sem filesystem de rede ou bind do Windows.
- API → PostgreSQL Docker `socialmei-postgres-relocation-20261112`, database `socialmei_candidate040_20261114`. O frontend usa a origem HTTPS pública. Endpoints encontrados apontam a contêineres AWS, aos domínios públicos da própria instância e ao Prisma legado; não a localhost do Windows.
- Gateway, API, PostgreSQL, n8n e os workers principais usam `unless-stopped`. **GOWS usa `restart=no`**: precisa de ajuste operacional próprio para sobreviver à reinicialização da instância. Não foi modificado.
- Os arquivos da interface e suas imagens estão na AWS. As prévias locais são ferramentas de desenvolvimento, não serviços da publicação. PDFs suportados pelo backend ficam no PostgreSQL, não numa pasta do notebook.
- PostgreSQL e pgAdmin não têm portas publicadas no inventário Docker; API legada e WAHA administrativo estão limitados ao loopback da EC2. Regras AWS para SSH ainda precisam de comprovação; não foram abertas portas nem alterados security groups.

## Inconsistência de transporte confirmada

O HTTPS anuncia `Alt-Svc: h3=":443"`, mas o Caddy público publica somente80/tcp e443/tcp. Não há listener nem DNAT UDP/443 no host. Assim HTTP/3 é anunciado sem um caminho publicado correspondente.

O smoke normal chegou a falhar antes do HTML com `ERR_CONNECTION_TIMED_OUT`. Com QUIC desativado apenas no navegador de diagnóstico, a jornada real passou por login e60→61→60:19 leituras abaixo de1s. A mesma comparação não altera certificados, autenticação ou timeout. Isso sustenta corrigir a inconsistência; a causa exclusiva de todos os timeouts ainda exige confirmação depois da correção.

O smoke agora tem um guard de fetch somente leitura, sem `context.route('**/*')`. Ele preserva o transporte/cache nativos e os sinais de aborto, bloqueia operações comerciais e permite apenas os POSTs oficiais de login, troca e logout. Não se deve usar um teste que intercepta todos os arquivos como única prova da experiência normal do navegador.

## Operação HTTPS preparada, não aplicada

Plano `9a4586df6ab6276e53707892605ea7b0ff90bfa33f34b20b977a15774f85c3b1`, Caddy público `socialmei-caddy`:

- Definir somente protocolos HTTP/1.1 e HTTP/2; não abrir UDP nem criar recursos.
- Comparação com a configuração ativa permite exclusivamente esse campo. Rotas, privacidade dos logs, autenticação, certificados, credenciais, portas e imagens ficam preservados.
- Backup do Caddyfile e JSON ativos congelado em pasta privada. O executor preserva o inode do bind, faz reload pela administração local já existente e confere HTTPS, interface, JSON ativo, API e demais contêineres.
- Em falha, restaura os bytes e JSON anteriores, com reload e verificação. Não há retries de aplicação. Recibo impede repetir a operação sem reconciliação.
- Testes sintéticos cobrem delta restrito, drift, aplicação, rollback, falha de reload e ausência de aprovação. Preparação/verify na AWS passaram, sem reload.

Fonte: `tools/prepare-https-transport.py`. O CLI prepara por padrão; `--apply`/`--rollback` exigem o hash aprovado. A localização privada está em `%LOCALAPPDATA%\SocialMEI-Privado\https-transport-preflight-private.json`. A mudança do Caddy público exige aprovação operacional própria; não está incluída nas antigas publicações de46/48 arquivos, já revertidas.

Após essa correção e homologação no navegador normal, preparar nova candidata Premium, CI e plano próprio usando o gateway existente. Não reutilizar R1/R2.

## Pendências que impedem declarar operação definitiva

| Prioridade | Pendência                          | Estado efetivo                                                                                                                   |
| ---------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| P0         | HTTPS e Premium                    | Correção de transporte preparada; nenhuma nova publicação autorizada/executada                                                   |
| P0         | Reinício GOWS                      | Política `no`; alteração própria pendente, sem mexer em sessão ou vínculo                                                        |
| P0         | Banco do worker Instagram          | Configuração continua em `db.prisma.io`, divergente da API; não ativar novos respondedores                                       |
| P0         | Backup da base atual               | Timer horário ativo aponta `socialmei_relocation`, não candidate040; recibos dizem `current_production_backup=false`             |
| P1         | Backup externo e restauração atual | Rotina ativa sem configuração externa; preparo anterior não comprova recuperação da base atual                                   |
| P1         | Dados60/61                         | Manifestos/dry-runs preparados, sem carga; aplicação exige aprovação separada                                                    |
| P1         | Professor                          | E-mail solicitado; preparar `member` nos dois negócios, sem privilégios globais ou SQL; concessão produtiva depende de aprovação |

Operação cotidiana será pela interface. Alterações de código/aparência seguem PR, revisão, testes e publicação por SHA; professor não recebe acesso ao servidor, ao banco ou à senha administrativa.
