# Checkpoint SocialMEI-IA

- Branch: `fix/channel-recovery-20261111`; último código: `59ee647`.
- Produção: API `994a103` saudável; worker WhatsApp `a66b885` contínuo, um contato autorizado; Bella Store recebe Direct real no workspace 1.
- Homologação WhatsApp: uma mensagem, tentativa, decisão e recibo únicos. Menus 0, 1 e 5 testados anteriormente. WEBJS preservado; listas nativas não homologadas.
- API `1a0e528` exibe respostas confirmadas do menu; sofreu rollback por incompatibilidade do compositor manual. Gateway `59ee647` corrige a origem da resposta manual, ignorando mensagens enviadas.
- Testes: sete casos com PostgreSQL descartável; Caixa em desktop/celular; regressão manual reproduzida e corrigida nas duas larguras, sem envios externos.
- Próxima ação: publicar gateway `59ee647`, verificar, reaplicar API `1a0e528`. GO concedido para ambos e para publicações incrementais das integrações descritas pelo usuário.
- Depois: liberar WhatsApp somente para mensagens recebidas voluntariamente, preservando remetente único, limites, deduplicação e atendimento humano; concluir Instagram manual/automático e identidade oficial dos contatos. Não recriar sessões nem migrar destrutivamente para GOWS.
- Artefatos privados e rollback AWS: `/home/ubuntu/.socialmei-inbox-1a0e528/`; comandos JSON `gateway-candidate.command.json`, `gateway-rollback.command.json`, `candidate.command.json`, `rollback.command.json`. API alvo já construída; gateway altera apenas um JS.
- Worker e rollback: `/home/ubuntu/.socialmei-continuous-a66b885/`; estado persistente, trava exclusiva e pausa em envio incerto. Não reutilizar pilotos expirados.
- Prisma oficial preservado. Sem migrations, merge, restauração de dados ou alteração de credenciais. Janela gratuita limitada; não contratar serviços automaticamente.
- Retomada: `git status --short`, `git log -5 --oneline`; consultar este arquivo e os recibos privados. SSH por `ubuntu@54.94.213.7`, chave local `~/.ssh/socialmei-aws-inspecao.pem`, com `BatchMode=yes` e `StrictHostKeyChecking=yes`. Não imprimir configurações privadas.
