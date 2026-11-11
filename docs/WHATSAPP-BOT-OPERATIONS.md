# WhatsApp: menu e atendimento por negócio

Para a implementação local posterior de resposta humana e seu estado de implantação, consultar [WHATSAPP-HUMAN-REPLIES.md](WHATSAPP-HUMAN-REPLIES.md). O histórico abaixo descreve a etapa original do planner.

Código preparado em28/10/2026. Não implantado. Nenhum número, QR, webhook ou
workflow ativo foi alterado. A primeira versão responde com catálogo estruturado;
não há LLM inventando preços, disponibilidade ou orçamento.

## O que está implementado

- Menu: produtos, preço/disponibilidade, serviços, orçamento e atendente.
- Estado durável por workspace/canal/conversa. A opção2 solicita o nome e a
  próxima mensagem pesquisa o catálogo ativo. Até10 itens por resposta.
- Produto com estoque positivo informa a quantidade registrada; zero solicita
  confirmação. Serviços não possuem estoque. A consulta não altera inventário.
- A solicitação de orçamento/atendente permanece na conversa da Caixa e suspende
  respostas do bot. O responsável precisa retomar explicitamente; não é garantia
  de disponibilidade imediata de um atendente nem de orçamento aprovado.
- No máximo20 decisões com resposta por minuto/conversa; pedir humano continua
  possível. Mensagens antigas, futuras ou fora de ordem não disparam respostas.
- Reservar uma operação autoriza **uma tentativa**. Timeout ou reserva perdida
  exige conciliação humana; não criar outra operação nem trocar para texto após
  uma tentativa de lista incerta. Não existe garantia de entrega exatamente uma vez.

## Contratos

Migration032 cria tabelas novas sem modificar dados anteriores. Rotas humanas:

- `GET/POST /api/v1/whatsapp/bot/access`; POST com `{channel_id}` gera uma
  credencial exclusiva, apresentada uma vez. A credencial anterior é invalidada.
- `DELETE /api/v1/whatsapp/bot/access/{channel_id}` revoga esse acesso.
- `GET /api/v1/whatsapp/bot/conversations` lista até100 estados recentes.
- `GET /api/v1/whatsapp/bot/decisions` lista até100 decisões/recibos recentes.
- `POST /api/v1/whatsapp/bot/conversations/{id}/resume`, `{channel_id}`, retoma o bot.

Exigem sessão do proprietário/administrador; mutações preservam Origin/CSRF.
Não há nova tela nem distribuição de credencial pública. Guardar o segredo no
cofre do n8n; nunca no frontend, localStorage, Git ou chat.

Rotas **internas**, com Bearer específico do bot:

1. `POST /internal/whatsapp/bot/decisions` com
   `{instance,external_message_id}`. A mensagem precisa estar previamente
   persistida pelo ingresso WAHA com HMAC válido. Texto, telefone e workspace
   enviados pelo caller não são aceitos. Repetir recupera a mesma operação.
2. `POST /internal/whatsapp/bot/decisions/{operation_id}/claim`, `{}`. Só quando
   `dispatch_allowed=true`, usar o destino/sessão/texto retornados. Reservas
   concorrentes ou repetidas recebemfalse. A reserva expira para novas tentativas
   após2min; uma reserva já adquirida nunca é reaberta automaticamente.
3. `POST /internal/whatsapp/bot/decisions/{operation_id}/receipt` com
   `{status:"confirmed",provider_message_id:"ID real"}` ou `{status:"uncertain"}`.
   Recibo divergente é conflito. `confirmed` comprova aceite/ID do WAHA, não leitura
   pelo cliente. Mensagens de saída não são acrescentadas à Caixa nesta etapa;
   o histórico de decisões registra o estado separado.

Credenciais de catálogo, sessão humana ou token técnico antigo não substituem o
Bearer do bot. Credencial e decisão guardam fingerprint do vínculo: troca de
instância/sessão/conta/versão exige rotação e recusa operações antigas.

## Botões e listas

Referências oficiais consultadas via Context7:
[matriz de engines](https://waha.devlike.pro/docs/how-to/send-messages/features/)
e [envio](https://waha.devlike.pro/docs/how-to/send-messages/).

`render_waha` gera texto por padrão. Lista com botão “Ver opções” só é preparada
paraGOWS/NOWEB quando `list_verified=true` é informado pelo integrador. Não há
fallback automático depois de tentar enviar. `sendButtons` aparece na documentação,
mas sua compatibilidade não deve ser presumida pela existência do endpoint.

**O receptor atual éWEBJS/texto.** O claim e o workflow desta entrega usam somente
`sendText`; respostas nativas de botões/listas e outras engines ainda precisam de
payload real homologado. A lista está preparada como renderer, não habilitada no
telefone. Não trocar a engine da sessão real nem prometer botões no aparelho antes
desse teste. As opções numeradas permitem iniciar o piloto sem essa dependência.

## n8n e corte futuro

`n8n-workflows/experimental/whatsapp-bot-planner.json` é um subworkflow inativo,
sem webhook público ou credenciais. A trava `ENABLED=false` também impede executar
manualmente por acidente. Foi validado por contratos/code nodes isolados, **não
executado/importado no n8n real**.

Após inspecionar os fluxos ativos e aprovar um único remetente:

1. Backup atualizado/restaurável; ensaiar032 em cópia isolada. As ferramentas de
   publicaçãoV25 fixadas em001–031 recusam esta candidata; não contornar a trava.
2. Preparar imagemAPI e overlay privado preservando gateway, OAuth, egress e env.
   Montar o [registry privado](WHATSAPP-INGRESS-REGISTRY.md) explicitamente.
3. Conferir engine, sessão, número e vínculo do canal no banco. Manter
   `envio_habilitado=false`: esse campo protege o remetenteCRM não implementado;
   o futuro sendern8n é configuração separada a homologar.
4. Configurar `SOCIALMEI_WHATSAPP_BOT_ENABLED=true` apenas no overlay aprovado,
   junto às flags do ingresso já documentadas. A API não inicia o worker/sender.
5. Encaminhar o **corpo bruto e HMAC** ao ingresso por rede privada. Somente após
   o commit de recepção, executar o subworkflow para o mesmo ID externo.
6. Selecionar uma credencialHeaderAuth do bot nos três nósAPI e uma credencialWAHA
   no nó de envio. Conferir URLs internas e conectividade privada. Não expor
   `/internal/*` no Caddy público nem conectar o PostgreSQL a uma rede pública.
7. Revisar a trava de ativação; testar mensagem real autorizada, catálogo com dois
   negócios, handoff e falha de rede. Sem retry nos nós de envio.

Histórico de execução do workflow está desabilitado para não gravar mensagens;
usar monitoramento por IDs/estados sanitizados. No n8n, desativar qualquer salvamento
adicional externo que viole essa configuração. TokenHMAC e Bearer são distintos.

Rollback: desabilitar a nova orquestração, desligar a flag do bot e revogar sua
credencial. Preservar tabelas/decisões/ingresso existente; voltar apenas a imagemAPI
e configuração anteriores se necessário. Não restaurar banco automaticamente,
apagar volumes ou reativar tentativas claimed/uncertain.

## Recuperação da fila e falhas do remetente

O endpoint `/internal/whatsapp/bot/sources` reoferece uma decisão `planned` recente
somente enquanto seu fingerprint de canal e sua revisão de conversa continuam
vigentes. Pausar/retomar a conversa, preparar uma mensagem posterior ou alterar o
vínculo do canal invalida esse replay. A consulta não modifica nem apaga decisões;
o histórico permanece disponível. Mensagens recebidas ainda não planejadas
continuam na fila, com os mesmos limites de idade, canal, workspace e contatos
permitidos. O claim continua sendo a autorização final, inclusive se a revisão
mudar depois da consulta.

No template existente `whatsapp-bot-planner.json`, somente **Enviar uma vez WAHA**
usa `onError: continueRegularOutput`. Timeout ou erro HTTP segue para o validador,
que descarta os detalhes do erro e produz exclusivamente `{status: "uncertain"}`.
O recibo é gravado na mesma operação já reservada. Não há retry de envio, outro
sender, fallback de rota ou confirmação inferida de um ID dentro de um erro.
Falhas nos nós de planejamento, claim, guarda de destino e gravação do recibo
continuam interrompendo a execução.

Essa semântica foi conferida na implementação oficial do
[HTTP Request 4.2 do n8n 2.40.5](https://github.com/n8n-io/n8n/blob/a331d3858797b161e4acba288396be3835425d8e/packages/nodes-base/nodes/HttpRequest/V3/HttpRequestV3.node.ts#L877)
e no [contexto de execução](https://github.com/n8n-io/n8n/blob/a331d3858797b161e4acba288396be3835425d8e/packages/core/src/execution-engine/node-execution-context/base-execute-context.ts#L111).
Reconfirmar a versão instalada antes de promover o template. Ele permanece
`active:false`, com `ENABLED=false`, sem credenciais e sem salvar execuções.

Se o n8n parar, perder a resposta do claim ou falhar antes de persistir o recibo,
a decisão ainda pode permanecer `claimed`. Não reabrir essa tentativa: conciliar
manualmente com o provedor. `uncertain` também exige conciliação e nunca autoriza
novo envio automático, mesmo que a requisição possa ter sido aceita pelo WAHA.

Verificação: `test_whatsapp_bot.py` cobre fila invalidada, vínculo alterado,
persistência/idempotência de recibo incerto e recusa de novo claim em PostgreSQL
descartável. `tests/whatsapp-bot-workflow.test.cjs` cobre o roteamento declarado e
os Code nodes com erros sintéticos de timeout/HTTP. Esses testes não equivalem à
execução do workflow no n8n vivo nem ao envio real no WhatsApp.
