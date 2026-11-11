# Menu WhatsApp

- O transporte principal é WEBJS. O perfil preparado mantém `/api/sendText`, sem mudar para GOWS.
- Alternativa funcional: menu textual numerado; 1 produtos, 2 preço/disponibilidade, 3 serviços, 4 orçamento/atendimento humano, 5 ou 9 atendente e 0 menu.
- Respostas de listas/botões recebidas usam o ID autenticado da seleção, sem interpretar o título como comando. Histórico e deduplicação permanecem no mesmo fluxo da Caixa.
- Botões nativos estão [depreciados pelo WAHA](https://waha.devlike.pro/docs/how-to/send-messages/#send-buttons). Listas nativas não estão habilitadas nem homologadas neste perfil. Não apresentar fallback textual como botão/lista nativa.
- Worker: retry apenas na leitura inicial; falha após claim ou resultado incerto mantém pausa, sem repetir envio.
- Execução contínua restrita a um contato autorizado: guard `a66b885`, sobre a imagem homologada `994a103`. Ativação com corte novo de mensagens; não reutiliza a janela do piloto.
- Um remetente com trava exclusiva e estado persistente. Limite móvel de 5 respostas por 45 minutos; tentativas anteriores ainda nessa faixa contam para o limite. Falha incerta exige conciliação e não é reenviada.
- O piloto anterior confirmou os comandos 0, 1 e 5. A homologação de listas e botões nativos continua pendente; ampliar contatos exige autorização específica.
