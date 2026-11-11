# Menu WhatsApp

- O transporte principal é WEBJS. O perfil preparado mantém `/api/sendText`, sem mudar para GOWS.
- Alternativa funcional: menu textual numerado; 1 produtos, 2 preço/disponibilidade, 3 serviços, 4 orçamento/atendimento humano, 5 ou 9 atendente e 0 menu.
- Respostas de listas/botões recebidas usam o ID autenticado da seleção, sem interpretar o título como comando. Histórico e deduplicação permanecem no mesmo fluxo da Caixa.
- Botões nativos estão [depreciados pelo WAHA](https://waha.devlike.pro/docs/how-to/send-messages/#send-buttons). Listas nativas não estão habilitadas nem homologadas neste perfil. Não apresentar fallback textual como botão/lista nativa.
- Worker: retry apenas na leitura inicial; falha após claim ou resultado incerto mantém pausa, sem repetir envio.
- Piloto preparado: `--continuous --window-seconds 600`. Ao encerrar a janela, permanece pausado; uma operação já iniciada termina com seu recibo.
- Retomada, envio real e homologação nativa exigem autorização específica. Nenhum envio foi ativado por esta preparação.
