# Ciclo de vida WhatsApp — preparado, não publicado

O contrato privado `python-service/whatsapp_channel_handover.py` prepara a aposentadoria de um vínculo e a reserva de outro para a mesma sessão física. Não oferece rota pública, não envia mensagens, não modifica Docker/registry/n8n e não emite credenciais. A API produtiva continua em CRM233/schema040.

## Integridade e compatibilidade

A migration incremental 041 mantém `workspace_id`, IDs, instância, sessão, conta e todas as FKs históricas. Acrescenta `retired_at`, exige vínculo aposentado inativo e troca a unicidade incondicional por unicidade das gerações não aposentadas. Uma reserva desativada continua exclusiva; desligar um canal não libera sua sessão. O ledger de transições registra origem, destino, administrador, proprietário autorizado, estado anterior e rascunhos revisados.

O ingresso de fixtures usa `ON CONFLICT DO NOTHING`, compatível com schema040 e 041. O contrato privado recusa schema040 antes de qualquer escrita. Nenhuma migration antiga foi alterada. A aplicação 041 exige autorização específica, backup consistente e revisão das constraints/índices no destino. Não remover 041 depois de haver gerações históricas com a mesma sessão: a unicidade anterior não pode ser restaurada sem perder esse histórico.

## Corte coordenado ainda sujeito a aprovação

1. Confirmar IDs, proprietário ativo do destino, revisão, identidade física e backup. Inspecionar filas e revisar explicitamente os UUIDs dos rascunhos humanos que permanecerão sem envio na origem. Qualquer envio planejado, em curso ou incerto bloqueia o corte.
2. Pausar efetivamente ingresso e todos os respondedores, inclusive n8n, conciliando envios já iniciados. A prova privada de pausa tem escopo exato e validade máxima de 90 segundos: é uma declaração do operador, **não verifica nem pausa processos**. O futuro coordenador operacional deve medir essa pausa antes de produzi-la.
3. `inspect_handover` produz o hash do estado esperado. `reserve` exige esse hash, UUID idempotente, administrador ativo e recibo privado durável. Em uma transação aposenta a origem e reserva o destino inativo. Se a gravação do recibo falhar, toda a reserva é revertida. Em resultado transacional incerto, consultar o ledger pelo UUID antes de repetir; um arquivo sozinho não comprova commit.
4. Com os processos ainda pausados, gerar o candidato com `whatsapp_handover_runtime_plan.prepare_runtime_plan(request, receipt, registry)`, usando recibo reconciliado com o ledger e registry privado de origem. A função não escreve arquivos nem modifica processos: deriva o novo workspace/canal, revisão2, hash de autorização e corte arredondado para o próximo segundo; preserva sessão, conta e HMAC. **O resultado contém HMAC: não imprimir nem versionar.** Instalar o candidato somente após conferir a pausa real, a autorização e a nova credencial do worker. Não iniciar segundo respondedor.
5. O piloto fora do workspace1 exige `SOCIALMEI_WAHA_PILOT_WORKSPACE_ID` e `SOCIALMEI_WAHA_PILOT_BINDING_SHA256`, calculado por `settings.waha_pilot_binding_digest` sobre workspace, canal, instância, sessão, conta, revisão e engine. Não são configurações do navegador. Sem essa revisão exata, o ingresso, token e listas nativas recusam o novo escopo. O padrão instalado do workspace1 permanece compatível; nenhum número adicional é autorizado automaticamente.
6. `activate` valida a reserva, registry exclusivo, revisão e corte temporal. Por padrão exige também autorização de bot e configuração humana GOWS no mesmo destino. O modo privado `require_replies=False` serve apenas à homologação de recebimento e não comprova jornada de atendimento. A ativação não inicia responders nem emite tokens.
7. Antes de liberar o ingresso, comprovar exclusividade do processo, credencial/revisão e ausência de sender n8n concorrente. Só então homologar com contato autorizado: recebimento, associação CRM, menu e reserva na Agenda. Não mover eventos antigos; a deduplicação global por conta/evento continua vigente.

## Reversão restrita

Antes de qualquer evento no destino, `rollback` preserva ambas as linhas, aposenta o destino e reativa a origem com revisão monotônica. Registry e credenciais anteriores tornam-se obsoletos: precisam de revalidação explícita antes de retomar. A função não restaura arquivos nem processos. Depois de tráfico no destino, a reversão simples é recusada; exige transferência inversa aprovada, mantendo cada histórico na empresa em que foi recebido.

## Evidência e limites

`test_whatsapp_channel_handover.py` exige opt-in, PostgreSQL loopback porta55491 e database descartável autorizado. Cobre atomicidade, replay, concorrência, rascunho preservado, bloqueio de envio incerto, registry, corte temporal, deduplicação e reversão. `test_waha_pilot_scope.py` verifica o escopo exato sem provedores reais. O coordenador operacional de pausa/registry/credenciais e a homologação GOWS real permanecem pendentes; esse código não autoriza corte produtivo.

O corte usa `clock_timestamp()` depois dos locks e da validação do plano, com o mesmo instante na aposentadoria e no recibo. `NOW()` no início da transação poderia anteceder uma espera por lock. A regressão insere trabalho transacional antes do corte e verifica que esse período não é aceito como ingresso da nova geração. O gerador privado também é testado contra a ativação real no banco descartável.
