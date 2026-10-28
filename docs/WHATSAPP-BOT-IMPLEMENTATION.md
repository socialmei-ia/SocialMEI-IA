# Atendimento WhatsApp — implementação de 28/10/2026

Escolha técnica: reutilizar o ingresso HMAC e o catálogo existentes, com planejador
de conversa persistente e n8n como único remetente futuro. Não reutilizar a
credencial de catálogo (somente leitura) para escrita. Não instalar outro bot
concorrente nem iniciar sessões/envios nesta entrega.

Unidades de execução:

1. Carregar o registro WAHA de arquivo privado explícito; manter o ingresso fechado
   sem configuração. Preservar assinatura, vínculo de canal e parser WEBJS atual.
2. Migration032 aditiva para credenciais específicas, estado por conversa e decisões
   idempotentes vinculadas exclusivamente a mensagens já autenticadas/persistidas.
3. Menu, catálogo/preço/serviço e encaminhamento humano; nenhum preço inventado.
   Atendimento humano suspende o bot até retomada explícita pelo responsável.
4. Planejamento, claim único e recibo separados. Claim perdido ou envio incerto não
   autoriza repetição automática. O backend não chama WAHA nem abre sockets de envio.
5. Renderização texto por padrão; lista interativa apenas com engine GOWS/NOWEB e
   suporte verificado pelo operador. Não presumir botões funcionais em WEBJS.
6. Testes de transação, concorrência, duas empresas, revogação, replay, idade e
   encaminhamento; regressão de autenticação e frontend. PR separada sobre136.

O contrato de mensagens WAHA mantém ingresso WEBJS nesta etapa. Renderização de
listas para outras engines é preparação e depende também de homologar o respectivo
payload de entrada. Não migrar engine/sessão real para habilitar um controle visual.

Fora do corte: AWS, banco real, QR, número, webhooks/workflows ativos, envios e
publicações. A implantação precisará de backup atual, ensaio032 isolado, revisão dos
overlays/flags e comprovação do remetente único. Ferramentas V25 fixadas em001–031
continuam específicas daquela versão e devem recusar esta nova cadeia.
