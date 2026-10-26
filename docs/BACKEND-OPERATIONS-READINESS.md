# Operação e segurança de contas — candidata #111

25/10/2026. Código preparado em desenvolvimento. Nenhuma operação em AWS, Meta, n8n ou WAHA; nenhuma credencial real usada. O novo frontend do proprietário continua fora desta mudança.

## Sessões: contrato para o frontend

- `GET /api/v1/auth/sessions` retorna `{sessions:[{id,created_at,expires_at,current}]}`: até100 sessões ativas da própria conta, com a atual primeiro. Datas ISO8601. Não retorna token, hash, IP, user-agent nem dados de outros usuários. O escopo é a conta pessoal, incluindo seus próprios acessos em negócios distintos.
- `POST /api/v1/auth/sessions/{id}/revoke`, JSON `{}`:204, ou404 se não pertence à conta/está encerrada. Revogar a atual também limpa o cookie.
- `POST /api/v1/auth/sessions/revoke-others`, JSON `{atual:"senha atual"}`:204. Exige senha atual, mantém somente o acesso utilizado e registra auditoria. Limites persistentes evitam tentativa ilimitada de senha.

Autenticação por sessão, Origin e CSRF continuam obrigatórios. A migration025 acrescenta identificador público UUID distinto do segredo de autenticação, sem revogar sessões existentes. Não há uma tela nova; o frontend futuro poderá consumir estes contratos.

## Diagnóstico privado

`GET /api/v1/admin/diagnostics` exige administrador da plataforma. Um dono de negócio comum recebe403 e um visitante401. Resposta no-store, sem detalhes de conexão, credenciais, clientes ou mensagens.

Informa serviço CRM, SHA declarado na construção, autenticação, verificação read-only do banco, migrations esperadas, schema da recuperação/sessões/fila, configuração de e-mail e contagens agregadas da fila. A lista de migrations usa nomes exatos e possui teste de correspondência com o repositório.

O campo `release_sha` é nulo quando não foi fornecido um SHA40hex válido. A imagem da API aceita build arg `SOCIALMEI_RELEASE_SHA`, encaminhado pelo Compose team; imagem com label OCI de revisão. Este valor é metadado declarado no build, não atestado criptográfico da imagem. Conferir também digest/arquivos/Compose efetivo na VPS. Não atribuir um SHA fictício a uma imagem antiga.

`database.status=ready` significa somente que os contratos de schema testados estão acessíveis neste processo. Não significa homologação de todos os módulos. n8n/Instagram/WAHA retornam `not_verified`: o endpoint não faz chamadas externas nem inventa saúde operacional.

## Recuperação durável

Migration026 cria uma solicitação por usuário, com geração UUID e estados `pending`, `processing`, `sent`, `uncertain`, `expired`. A requisição202 persiste antes de responder; contas desconhecidas têm a mesma resposta e não geram entrega. Uma solicitação nova invalida o código anterior. Nenhum código em texto puro, destinatário ou senha SMTP fica na fila.

O worker explícito `python recovery_worker.py --run --limit 10` processa no máximo o limite1–100 por invocação. Não é iniciado pela API nem agendado automaticamente. Utiliza a configuração privada SMTP já documentada; sem ela, falha fechado. Precisa de instalação/agendamento homologados para enviar e-mails reais.

A posse do pedido é persistida antes do SMTP. O código256bits é gerado em memória no processamento, somente seu hash é salvo e expira em15min. Processamento iniciado e abandonado por mais de2min vira `uncertain`. Falha SMTP também vira `uncertain`, invalida aquele código e nunca é reenviada automaticamente. `sent` representa aceitação SMTP, não leitura/entrega na caixa postal.

Pedidos pendentes de mais de15min expiram sem envio. Depois de uma interrupção, pedidos ainda `pending` permanecem no banco para a próxima execução. Interrupção entre commit e envio não oferece exatamente uma entrega: o usuário pode precisar solicitar novamente. Uma nova solicitação/troca de senha pode tornar inútil um e-mail que já estava em trânsito; somente o código mais recente válido funciona. Locks por credencial e geração evitam que um envio antigo apague ou conclua um pedido novo.

O frontend da recuperação permanece o existente. Não se afirma configuração Gmail, envio real, fila remota ativa ou sincronização de serviços externos.

## Instalação e rollback a homologar

1. Conferir CI no SHA final, estado efetivo da VPS e hotfixes landing pública primeiro/gateway sem Basic. Não usar o deploy genérico para reconstruir a stack inteira.
2. Backup completo restaurável, imagens anteriores, configurações privadas e arquivos efetivos. Migrations025/026 são aditivas; executadas nesta rodada somente em PostgreSQL descartável.
3. Construir a API com o SHA correto, manter autenticação individual, configurar SMTP privado e instalar o worker apenas após autorização operacional. Nunca expor dados privados em `config.js`.
4. Testar duas contas, sessões antigas/atuais, recuperação real para endereço autorizado e diagnóstico administrativo. Conferir logs sem códigos/senhas/tokens.
5. Rollback: parar o agendamento do worker, desligar recuperação e voltar à imagem anterior compatível. Preservar tabelas aditivas e dados; não apagar volumes nem executar down migrations. Nunca deixar a API anterior aceitando202 com um worker novo sem homologar o conjunto.

O ensaio release usa a cadeia001–026, preservação de dados/ledger, replay, falha transacional e dump/restore. Fixtures incluem sessões antigas com UUIDs, códigos usados/pendentes e estados da fila. Isso não substitui backup ou teste de restauração da VPS real.

## Próxima etapa Instagram/n8n

A ponte viva permanece `pending_live_contract`. Antes de desenvolver um adaptador específico, inspecionar em leitura os workflows do colega e definir origem dos eventos, identidade do canal/workspace, autorização das consultas, idempotência, status/erros e responsável por cada envio. Não transformar o token administrativo n8n nem as rotas legadas de workspace fixo em credencial compartilhada de todos os MEIs.

As filas existentes de Instagram/outbox e o receptor WAHA continuam desabilitados por padrão. O alinhamento GOWS/WEBJS, número WhatsApp e configuração de contas/permissões Meta exigem homologação externa. Não criar um segundo remetente automático para os mesmos eventos.

## Verificações desta rodada

425 testes backend passaram em PostgreSQL16 descartável, sem skips na suíte completa. Os casos novos cobrem sessões, autorização administrativa, schema ausente, concorrência de workers e confirmação de senha, pedidos substituídos durante envio, expiração e resultado incerto. 332 testes frontend passaram; nenhum arquivo visual foi modificado nesta rodada. Compose validado com valores sintéticos e sem iniciar serviços reais. Revisão independente de segurança: achados corrigidos com regressões. CI remoto deve ser conferido no último HEAD; testes locais não autorizam produção.
