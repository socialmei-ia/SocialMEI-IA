# Respostas humanas do Instagram na Caixa

**Implementado, não implantado.** O fluxo usa a outbox021 existente e a conversa ingressada com assinatura da Meta. Não altera webhooks nem workflows ativos.

Na conversa Instagram real, o operador prepara um rascunho no servidor. A lista permite consultar as respostas registradas e abrir uma revisão com o destinatário e o texto. Preparar/revisar não envia. A confirmação final é separada e exige owner/admin, conta conectada e permissão de envio do servidor; a API revalida sessão, papel, conta, destino proveniente do evento e janela normal24h.

Cada aprovação/execução usa o contrato durável existente. O botão fica bloqueado durante a requisição; resultado incerto ou envio em andamento não gera nova tentativa automática. A consulta da lista é GET. Perda de confirmação exige consultar o registro antes de qualquer outra resposta. O histórico incorpora apenas saídas `confirmed` com identificador do provedor e indica confirmação pela Meta; rascunhos não viram mensagens enviadas.

A revisão captura uma cópia imutável do texto e da revisão mostrados no modal. A aprovação usa essa revisão, e o envio nativo também informa `expected_revision`, conferido sob bloqueio no servidor antes de registrar uma tentativa. Alteração/reaprovação concorrente exige nova revisão humana e não envia o texto modificado. O campo é opcional somente para preservar os clientes anteriores da API.

Limitação herdada: a consulta atual retorna até100 respostas recentes do negócio, filtradas por conversa na interface; não representa um arquivo completo das respostas antigas. Paginação por conversa fica pendente antes de uso com alto volume. Não interpretar ausência na lista como prova de que uma tentativa antiga não existiu.

## Remetente único

`SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=true` sozinho não habilita mais dispatch. Também são exigidos ingresso ativo e `SOCIALMEI_INSTAGRAM_DIRECT_OWNER=dashboard`. Padrão: `unassigned`, envio desligado. `n8n` ou valor não reconhecido mantém o transporte de saída bloqueado, preservando OAuth e preparação.

A variável é uma declaração operacional de responsabilidade, **não** um mecanismo que desliga automaticamente o workflow n8n. Antes de configurá-la, confirmar a conta destino dos workflowsLHlqroY2xzvpYAmD/A0EcNxcRvfWnMwKI e definir fan-out/cutover sem consumidor/resposta concorrente. Preservar o corpo bruto e assinatura do webhook. Sem esse acesso, não ativar o novo sender.

## Verificação

Testes do runtime comprovam bloqueio para `unassigned`/`n8n`. A suíte da outbox usa PostgreSQL descartável, concorrência, janela/permissões/isolamento, confirmação e estado incerto. O navegador usa o shell real e API controlada para preparar, revisar, confirmar e consultar sem repetir, nos temas claro/escuro e1440/390px.

Não houve Direct real, acesso Meta, n8n ou alteração AWS. O aceite real continua: mensagem externa recebida, persistida e visível na Caixa, uma resposta humana confirmada e recebida pelo remetente.

Referência oficial consultada: [coleção Meta — Instagram Login](https://www.postman.com/meta/instagram/folder/6raa77c/instagram-api-with-instagram-login). A versão Graph e as permissões efetivas da conta ainda dependem de inspeção/homologação operacional.
