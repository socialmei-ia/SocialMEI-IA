# Piloto WhatsApp da equipe

Alvo: workspace 1, sessão WEBJS existente, conta validada no WAHA com sufixo 5976. Nenhum teste automatizado nesta entrega representa uma mensagem real.

## Sequência operacional

1. Backup da equipe verificado; confirmar API saudável, Compose efetivo e sessão
   WAHA WORKING sem recriar a sessão.
2. `sudo python3 tools/team-whatsapp-private-mount.py` inspeciona; `--apply`
   adiciona somente o bind read-only `/run/socialmei/private` à API existente.
   O segredo fica em `/var/lib/socialmei-wa-pilot/registry`, fora do bind do gateway.
   A ferramenta guarda o override e reverte com checagem de saúde em caso de falha.
3. `sudo python3 tools/team-whatsapp-pilot.py --prepare-channel --confirm TEAM-1`
   provisiona canal e HMAC independente. Não configura webhook nem habilita bot.
   Não repetir se houver canal reservado parcialmente: conferir antes de reparar.
4. Implantar API contendo o modo `team-pilot`. Configurar, no override privado
   efetivo, `SOCIALMEI_WAHA_INGRESS_MODE=team-pilot`,
   `SOCIALMEI_WAHA_LAB_ENVIRONMENT=team-pilot` e
   `SOCIALMEI_WAHA_REGISTRY_FILE=/run/socialmei/private/waha-registry.json`.
   Autenticação e dados compartilhados devem continuar ativos. Não usar `isolated`
   como atalho para o servidor da equipe.
5. Preservar egress e rede do banco; adicionar comunicação privada somente onde
   necessária. Não publicar `/internal/*` no Caddy.
6. Conferir a configuração WAHA e a versão ativa do workflow n8n antes de anexar
   webhook adicional com o novo HMAC. Preservar assinatura dos bytes originais.
7. Uma mensagem do contato autorizado deve ser salva e aparecer na Caixa sem
   recarregar; conferir deduplicação e isolamento por negócio.

## Bot e remetente único

O webhook direto persiste mensagens, mas não dispara o subworkflow do bot.
O planner existente consome apenas `{instance, external_message_id}` de evento
já persistido e usa decisão, claim, envio único e recibo. Antes de ativá-lo, falta
ligar essa referência ao planner e transferir a responsabilidade de resposta do
workflow antigo sem sobreposição. Handoff precisa suspender todos os remetentes.

Manter bot/envios desativados até essa homologação. WEBJS usa menu numerado;
listas nativas continuam não homologadas. Recibo de envio significa aceite do
WAHA, não entrega ou leitura. Não compartilhar registry, .env, QR ou dumps.
