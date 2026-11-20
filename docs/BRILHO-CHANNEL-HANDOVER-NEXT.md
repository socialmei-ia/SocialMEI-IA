# Próximo incremento dos canais — contrato ainda necessário

Estado de 20/11/2026, leitura dirigida após concluir a conta34 e os dry-runs. Não houve alteração de canal, worker, Meta ou n8n.

## WhatsApp: preservar o GOWS atual

Registry e banco concordam: workspace1/canal1, sessão01, engine GOWS, canal ativo/provisionado, revisão3. Há42 decisões automáticas confirmadas e2 ignoradas; respostas humanas:3 confirmadas e1 rascunho. O rascunho precisa de decisão do responsável no negócio anterior antes de qualquer corte; não apagar, mover ou enviar automaticamente.

Bloqueios comprovados no código e no catálogo de constraints produtivo:

- `009_shared_channel_foundation.sql`: `UNIQUE(provedor,instancia,sessao)` inclui canais inativos. Desativar o antigo não permite reservar a mesma sessão no Brilho.
- As FKs compostas das conversas/eventos preservam workspace/canal históricos; mudar o `workspace_id` do canal com histórico viola essas referências.
- `waha_ingress.py` restringe `team-pilot` ao workspace1; `workspace-inbox` aceita outros negócios, mas permanece deliberadamente sem bot/sender. A lista nativa GOWS também tem binding revisado próprio em `whatsapp_bot.native_list_canary`.
- `/whatsapp/connection/requests` registra intenção, não executa transferência. Nenhum contrato existente cobre essa mudança preservando histórico e respondedor único.

Portanto, antes de pedir aprovação para o corte real, preparar e testar um lifecycle explícito de aposentadoria histórica e nova reserva da **mesma identidade real** da sessão, junto da autorização do piloto no destino. Se exigir migration incremental, ela deve ser preparada/testada somente em PostgreSQL descartável, com compatibilidade e rollback revisados. Não renomear instância/sessão/conta para escapar da unicidade, nem ampliar o piloto para números não autorizados.

Critérios: histórico permanece no workspace1; deduplicação global por conta/evento continua; eventos anteriores ao corte são recusados por `ingress_after`; tentativas incertas bloqueiam retomada; registry, canal, token de worker e sender apontam para um único binding; receber, persistir, associar CRM e reservar no Brilho são homologados com contato autorizado. Banco e configuração privada precisam de transição coordenada — um lock SQL não serializa arquivo de registry nem envio externo.

## Instagram: dois OAuth independentes

Os status autenticados de60 e61 retornam `not_connected`, sem credencial; a única conexão existente continua no workspace1, expiração27/12/2026. Nenhuma credencial foi reutilizada ou exposta.

O worker Instagram legado continua com `DATABASE_URL` em `db.prisma.io`; não foi reiniciado. A API usa o PostgreSQL realocado. O inventário anterior identificou dois workflows n8n com nós de envio Meta; ainda não foi comprovada exclusividade por conta. Não habilitar outro sender antes dessa conciliação.

Preparação operacional seguinte: obter autorização OAuth de `@brilholimpeza.me` no60 e `@bellastore.me8` no61, confirmar identidade profissional/escopos/subscrição e chave de criptografia; preparar imagem/comando/configuração do worker compatíveis com a API e o banco correto; definir um respondedor por conta. Somente depois da aprovação de Meta/worker/n8n executar os testes reais de Direct recebido, persistência e resposta entregue sem duplicação.

O backend já possui unicidade de conta profissional ativa e conexão ativa por workspace, tokens vinculados à conexão/workspace e teste de eventos assinados para duas contas em um payload. Esses testes anteriores não substituem homologação com as duas contas reais.

## Professor

O preview da #236 comprova conta individual `report_viewer` nos dois negócios, revogação e troca sem retorno indevido ao login. Para produção falta e-mail autorizado e aprovação da concessão. Esse papel consulta indicadores agregados e não permite ler clientes nem editar registros. Se o professor precisar visualizar a agenda individual/CRM, definir e testar o papel de leitura apropriado antes da concessão; não prometer essa navegação com `report_viewer`.
