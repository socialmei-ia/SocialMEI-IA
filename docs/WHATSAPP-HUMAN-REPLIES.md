# Resposta humana WhatsApp pela Caixa

Implementação local após `0054a04`, ainda sem implantação ou envio real homologado.

- Migration incremental `035_whatsapp_human_outbox.sql`; nenhuma migration anterior alterada.
- `POST /api/v1/whatsapp/replies`: `{operation_id, source_message_id, text}`. O UUID identifica o registro imutável; repetir o mesmo conteúdo recupera a operação.
- `GET /api/v1/whatsapp/replies?conversation_id=...` consulta até 100 respostas recentes; `GET /{id}` consulta uma operação.
- `POST /api/v1/whatsapp/replies/{id}/send`, `{}`, exige confirmação pela interface e configuração privada habilitada.
- Workspace vem da sessão; destino e sessão WAHA vêm da mensagem recebida e do canal verificado. Texto não é enviado durante a preparação.
- Preparar uma resposta pausa o bot. Tentativas humanas iniciadas/incertas impedem novas tentativas e retomada automática. Operações do bot já reservadas também bloqueiam o envio humano.
- O claim é persistido antes da rede. Falhas ou recibos inválidos exigem conciliação, sem retry automático. Um ID aceito pelo WAHA não comprova entrega/leitura.
- A Caixa recupera rascunhos, protege o UUID pendente após falha/reload e apresenta as respostas confirmadas no histórico.

## Configuração privada para uma futura ativação autorizada

O envio permanece desativado por padrão. Configurar somente no servidor:

- `SOCIALMEI_WHATSAPP_HUMAN_SEND_ENABLED=true` e `SOCIALMEI_WHATSAPP_HUMAN_OWNER=dashboard`.
- `SOCIALMEI_WHATSAPP_HUMAN_WORKSPACE_ID`, `..._INSTANCE`, `..._SESSION`, `..._ACCOUNT_ID`.
- `SOCIALMEI_WHATSAPP_HUMAN_CONTACTS`: JSON com 1–20 contatos autorizados, `@c.us` ou `@lid`.
- `SOCIALMEI_WAHA_PRIVATE_BASE_URL`: exclusivamente `http://waha:3000` ou `http://socialmei-waha:3000`.
- `SOCIALMEI_WAHA_PRIVATE_API_KEY`: credencial privada; nunca informar na interface, Git ou chat.

Autenticação, dados compartilhados e ingresso verificado precisam estar habilitados. Não alterar `crm_canais.envio_habilitado`: o ingresso existente depende de seu estado atual. O transporte verifica sessão `WORKING`/conta antes de um único envio; redirecionamentos e proxies estão desativados. Contratos oficiais: [sessões](https://waha.devlike.pro/docs/how-to/sessions/) e [envio de texto](https://waha.devlike.pro/docs/how-to/send-messages/).

## Pendências operacionais

A AWS inspecionada continua com API/gateway antigos e migrations até 033. Antes de ativar: preparar release compatível com 034/035, backup/restauração verificados, rollback por serviço, ingresso assinado e respondedor único. Os gates v33 continuam recusando migrations adicionais; não foram relaxados para publicar esta implementação.

O webhook WAHA atual aponta ao workflow n8n legado publicado. Reconciliar essa ligação e a rede n8n/API sem criar outro respondedor. Nenhuma configuração, webhook ou workflow real foi modificado por esta entrega.

Depois da autorização operacional: receber uma mensagem do contato permitido, abrir a Caixa, preparar/revisar/enviar, consultar o ID do provedor e recarregar o histórico. Rollback desativa o transporte e volta apenas os serviços afetados, preservando dados e tentativas incertas.
