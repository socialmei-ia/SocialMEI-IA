# Menu WhatsApp

- Produção: WEBJS WORKING; menu/worker público `837079e`, API `86cdd5b` e gateway `8159c17`. Apenas mensagens novas iniciadas pelo contato, persistidas e autenticadas. Sem IA ou disparos.
- Menu textual: 0 menu, 1 produtos, 2 preço/disponibilidade, 3 serviços, 4 orçamento/humano e 5 ou 9 atendente. Catálogo do workspace; atendimento humano e rascunhos suspendem o bot.
- Um remetente, estado persistente e deduplicação; 10 respostas por contato e 60 globais por 15 minutos. Só leitura anterior ao claim tem retry. Envio incerto exige conciliação e nunca é reenviado automaticamente.
- Respostas confirmadas aparecem uma vez na Caixa. O compositor manual usa a última mensagem recebida, ignorando respostas enviadas. Transporte manual aceita somente origens validadas do workspace/conta autorizados.
- Evidência real pública: um contato fora do antigo piloto, duas mensagens, duas decisões confirmadas e dois recibos distintos. Cada entrada/resposta aparece uma vez na Caixa; sem duplicação. Aceite do WAHA comprovado, sem afirmar entrega/leitura no telefone. Comandos 0/1/5 e contínuo restrito homologados anteriormente.
- Listas e botões recebidos usam o ID autenticado da seleção. Listas nativas não homologadas; manter alternativa textual. CORE 2026.9.2 não habilita listas Plus. GOWS não substituiu a sessão WEBJS.
- Operação, bloqueios, testes e rollback: [CODEX-CHECKPOINT.md](CODEX-CHECKPOINT.md).
