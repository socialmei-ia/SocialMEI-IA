# Instagram — ingresso durável preparado, sem ativação externa

## Escopo e fonte

Esta unidade continua a OAuth/vault preparados. Reutiliza a verificação Meta da
PR #103, os vínculos de conta da migration019 e as mesmas tabelas da Caixa
`me_conversations/me_messages/me_external_messages`. Não cria outra Caixa nem
cliente pelo nome. Não instala credenciais, conta Meta, provedor HTTP ou worker.

Fontes primárias indexadas consultadas via Context7:

- https://developers.facebook.com/documentation/instagram-platform/webhooks/examples
- https://developers.facebook.com/documentation/instagram-platform/webhooks

Essas fontes confirmam o envelope Instagram Login, sender/recipient IDs,
timestamp, message.mid/text, is_echo e o recibo messaging_seen/read.mid.
A leitura direta completa do site Meta estava indisponível no ambiente; conteúdo
indexado não é App Review nem homologação de uma conta. Não misturar exemplos da
Messenger Platform/Facebook Login. O limite de **1024 bytes ASCII por MID** é
uma escolha interna de ingresso/índice, não um máximo documentado pela Meta.

## Contrato e segurança

Rota preparada: `GET|POST /internal/instagram/meta/webhooks` (também aceita a
variante com barra final, sem redirecionar segredos). A dependência
`ingress_service` responde 503 até injeção explícita de `InstagramIngressService`
com App Secret e verify token exclusivos do teste. Não há chave gerada/lida
implicitamente. Também exige as flags simultâneas:

- `SOCIALMEI_INSTAGRAM_INGRESS_MODE=isolated`
- `SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT=isolated`
- Autenticação configurada e dados compartilhados ativos.

Webhook não requer sessão humana; somente o contrato de assinatura valida o
remetente. Ler mensagens na API/conta continua exigindo a sessão autorizada.
GET aceita exatamente hub.mode/hub.verify_token/hub.challenge, sem duplicatas;
responde texto puro ao challenge válido. POST exige application/json sem query,
exatamente um header X-Hub-Signature-256 e corpo de até64KiB. HMAC-SHA256 é
verificado sobre bytes brutos antes de parse ou DB; JSON duplicado, constantes
não finitas, identidades inválidas, campos de roteamento inesperados e lotes
excessivos são recusados. O máximo de200 eventos normalizados e50 entradas do
contrato anterior continua valendo.

O middleware ASGI remove query_string antes de dependências/roteamento, inclusive
em503/403/barra final, e fornece no-store/nosniff. O handler recebe o challenge
por estado interno, sem devolvê-lo em erros. **Isso não protege logs do Caddy ou
outro proxy anterior à API**: auditar/restringir/redigir access logs e traces
antes de qualquer autorização de endpoint real. Não registrar URL bruta,
headers, parâmetros, assinatura, tokens ou corpo de eventos.

Conta/workspace são resolvidos somente em `ig_meta_connections`: vínculo conectado,
não expirado e com instagram_business_basic+instagram_business_manage_messages.
Entry ID e destinatário devem corresponder à conta; sender ID identifica o contato.
Não há workspace, client_id ou connection_id aceito livremente no payload.
Locks são compatíveis com o mutex da OAuth; a conexão é revalidada depois do lock.
Desconexão que vencer a corrida impede gravação; se o ingresso vencer, o commit
precede a desconexão. Não há busca de nome/perfil: o contato usa nome genérico.

## Mensagens, recibos e deduplicação

O perfil implementado processa Direct de texto simples e preserva texto UTF-8
original, espaços, quebras e horário em milissegundos. Rejeita texto vazio,
controles inválidos e mais de8192bytes. Echo nunca vira entrada de cliente;
mensagens com anexos/variantes não suportadas são registradas como ignored,
sem baixar mídia ou reter o objeto bruto. Read receipt com mid estável é ignored;
nenhum estado de entrega/leitura é inventado. Outros envelopes/changes/edits,
receipts sem identidade estável e delivery de contrato não confirmado são
recusados. Não tratar message_edit como mensagem nova.

Migration020 é incremental e não reescreve migrations anteriores. Acrescenta
origin às três tabelas da Caixa, com default synthetic. Constraints condicionais
preservam referências synthetic e limite120 dos registros sintéticos; Instagram
usa `instagram:<ID numérico>` e MID opaco ASCII de até1024bytes. As FKs compostas
impedem encadear origens ou workspaces incompatíveis. Ampliar VARCHAR para o perfil
Instagram não amplia o modelo público Incoming nem a API /synthetic-messages.

`ig_meta_ingress_events` contém somente metadados, hashes, estado e vínculo à
mensagem; texto fica apenas em me_messages. Não contém token, assinatura ou raw
payload. A FK composta vincula workspace/conexão/conta externa, e outra vincula
workspace/mensagem/origem. Message/echo/unsupported compartilham a identidade
global conta+MID: mudar o tipo não contorna um tombstone. Recibos têm identidade
separada de mensagem. Fingerprint canônico exclui entry.time/ordem/whitespace JSON
mas inclui conteúdo semântico e horário original.

Locks por conta + ledger + append na Caixa ocorrem na mesma transação. Mesmo
MID/conteúdo retorna duplicates sem nova mensagem. Conteúdo conflitante falha409.
Lote com falha/conta desconhecida não confirma parcialmente. HTTP200 somente após
commit. Reenvio com conta transferida para outro workspace consulta o ledger global
e não copia a mensagem antiga. Reconectar a mesma conta no mesmo negócio mantém
thread por conta/contato, sem usar UUID transitório da conexão como identidade.

Não há expurgo de ledger nesta entrega. A exclusão física de um workspace pode
remover seus tombstones por CASCADE; uma política futura de exclusão/retomada deve
tratar replay histórico antes de habilitar esse fluxo real. Não afirmar proteção
eterna após destruição explícita dos registros de dedupe.

## Caixa existente e envio fechado

O persister SQL privado é compartilhado, mas quota, operações e validação pública
sintética permanecem separados. Ingresso Meta não consome a quota sintética e não
cria análise heurística, documento, cliente, venda, outbox ou mensagem de saída.
A API recusa análise sintética de mensagem com origin Instagram.

Capabilities adiciona instagram_inbox somente sob o gate isolado. Conversas são
lidas pela sessão/workspace; não misturam dados locais nem fazem fallback de escrita.
A normalização funcional reconhece a origem Instagram explicitamente, mantém IDs
estáveis e preserva o fluxo sintético anterior. Conversas Instagram não recebem
prefixo synthetic ou rótulo fictício. Compositor/envio/ações de laboratório ficam
fechados para essa origem; nenhum HTML/CSS/layout/animação foi redesenhado.
A atualização de leitura usa o controle/refresh já existente; não há polling,
websocket ou configuração de produção novos nesta unidade.

## Verificação e gates posteriores

`test_instagram_meta_ingress.py` usa fixtures assinadas e PostgreSQL descartável.
Cobre assinatura/rawbody/JSON/limites/headers duplicados antes do DB, privacidade
ASGI até quando503, conta/escopos/expiração/desconexão, concorrência/dedupe/conflito,
rollback de lote, origem/FKs, chegada fora de ordem, reconexão, transferência e
strictness da API sintética. Testes Node e browser cobrem leitura na Caixa existente,
identidade/origem e compositor/envio desabilitados, sem mudar assertivas anteriores.
O ensaio PostgreSQL16 inclui replay020, fixtures/dump/restore e preservação dos
valores antigos. Sem PostgreSQL local, skips não são passes; aguardar CI final.

Ativação real exige aprovação própria, App Review/permissões/conta de teste,
credenciais privadas, assinatura de subscriptions, proxy HTTPS e redaction de logs.
Nenhuma conta Meta, webhook público, n8n, WAHA, AWS, migration real ou envio foi
alterado. Não há suporte homologado de anexos, comentários, publicação ou Direct de
saída nesta entrega. A operação externa permanece desabilitada.
