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

## Recebimento isolado e atendimento humano

`tools/team-whatsapp-persistence-only.py --legacy-backup DIRETORIO_PRIVADO` inspeciona
a sessão sem imprimir URLs, telefone ou chaves. O backup original deve conter
`waha-session.before.json` e seu checksum em `SHA256SUMS.private.json`, ambos
verificados antes de comparar o destino legado exato. Com
`--apply --confirm TEAM-1 --expected-config-sha256 HASH`,
retira somente o webhook legado e preserva o webhook HMAC direto. Exige a API
saudável com bot desligado e o hash exato da configuração inspecionada. Salva
snapshot privado com checksum e restaura em caso de falha de configuração/saúde.
O workflow n8n continua intacto; sua execução manual deve permanecer suspensa.
A atualização da configuração pode reconectar WEBJS sem recriar container/volume.

Para restauração explícita, inspecionar o hash atual e usar
`--restore /var/lib/socialmei-wa-pilot/persistence-only-TIMESTAMP --confirm TEAM-1
--expected-config-sha256 HASH`. Isso restaura o webhook antigo e pode retomar suas
respostas; nunca executar ao mesmo tempo que o novo remetente. Não restaura banco.

A Caixa V22 passa a oferecer **Assumir atendimento** e **Retomar bot** aos
proprietários/administradores em conversas WAHA persistidas. A pausa funciona
mesmo antes da primeira decisão ou com bot desligado. Invalida decisões ainda
não reservadas; um claim já adquirido pode estar em andamento e precisa de
conciliação, sem repetição automática.

O template `n8n-workflows/experimental/whatsapp-bot-persisted-inputs.json` consulta
até 50 referências recentes do canal e chama o planner separadamente por mensagem.
Decisões planejadas podem ser recuperadas antes do claim, dentro de seu prazo;
claimed/uncertain/confirmed/skipped nunca voltam para envio. O template permanece
inativo, sem credenciais e com trava de execução e ID do planner a configurar.
O polling usa rede privada; não requer expor rotas internas ou alterar migrations.

Fora do ambiente isolado, `SOCIALMEI_WHATSAPP_BOT_ALLOWED_CONTACTS` precisa conter
JSON com até 20 contatos expressamente autorizados. Ausência, lista vazia ou
valor inválido bloqueiam planejamento e claims para todos os contatos; ingressos
continuam sendo persistidos. A autorização é conferida novamente no claim.
Não preencher com contatos presumidos nem ativar o sender antes da homologação.
