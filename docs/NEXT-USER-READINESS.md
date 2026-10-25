# Próxima etapa e pendências para os usuários

25/10/2026. Sem publicação nesta rodada. A candidata #111 concentra o backend; a #101 é referência separada para Instagram. As PRs encerradas não foram mescladas.

## Organização GitHub

HEADs comprovadamente ancestrais da candidata: #110,#109,#108,#107,#106,#105,#104,#103,#102,#100,#95,#94,#92,#91,#90,#89,#83,#82,#79,#77,#75,#74,#71,#70,#69. Encerradas sem merge; branches preservadas.

Arquivadas com diferenças não incorporadas por ancestralidade: #99,#98,#97,#96,#93,#88,#86,#84,#72,#56,#55,#54,#48,#45,#44,#43. O encerramento organiza a revisão; não afirma que seus patches foram aplicados. Reabrir/reaproveitar diferenças somente após comparação. #101 permanece aberta porque a próxima fase foi explicitamente solicitada. #111 permanece Draft para a revisão da candidata e CI. Nenhuma main modificada.

## Antes de liberar usuários reais

1. Confirmar API, gateway, banco/migrations e hotfixes efetivos da AWS por inspeção somente leitura. Não confundir os containers auxiliares locais com a API CRM.
2. Homologar backup/restauração e rollback das imagens e arquivos efetivos, incluindo landing primeiro e gateway público sem Basic.
3. Conferir CI no último commit e preview autenticado completo. Aprovação de merge/deploy/migrations é separada.
4. Configurar Gmail/SMTP privado e testar entrega para uma conta autorizada. Código pronto não significa conta Google conectada.
5. Conferir privilégio mínimo do banco e isolamento entre negócios no runtime real, sem reutilizar workspace fixo para todos.

## Instagram — próxima entrega

- Inspecionar em leitura os workflows do n8n da equipe; contrato vivo ainda não confirmado.
- Escolher um responsável por atendimento/publicação para não haver dois remetentes automáticos.
- Mapear contas, canais, mensagens e consultas de catálogo ao workspace autenticado; identificar operações e retorno de status.
- Homologar OAuth/escopos/callback, webhooks assinados, deduplicação, expiração e revogação de tokens, com conta de teste autorizada.
- Recepção, aprovação humana e outbox são bases existentes; publicação de mídia e agendamento real ainda precisam de contrato/worker/mídia segura.
- Não habilitar transporte ou IA de produção antes desses gates. Nenhuma conexão Meta real foi feita.

## WhatsApp

Alinhar engine GOWS dos Composes com receptor testado WEBJS, confirmar edição/HMAC e depois homologar número e registry por negócio. Sem número não se deve prometer sessão conectada. Envio, mídia e grupos continuam fora desta entrega.

## Melhorias de experiência recomendadas

- Recuperação por e-mail agora implementada, mas verificação de e-mail, troca segura de e-mail e MFA ainda precisam de etapas próprias.
- Sessões/dispositivos visíveis, sair de todos os dispositivos e notificações de acesso/troca de senha.
- Estados claros de offline, erro de gravação e sincronização, sem fallback silencioso para dados locais.
- Status de canais, filas com falha e recibos distintos de aceitação, entrega e leitura.
- Política de privacidade, termos, retenção/exclusão/exportação LGPD e consentimento para IA, com revisão jurídica.
- Onboarding com primeira ação útil, ajuda de campos e acessibilidade do frontend novo a ser entregue pelo proprietário.
- Explicar quais históricos/rascunhos são locais e quais sincronizam entre dispositivos.
- Agenda operacional, encomendas/entregas e equipe devem ser homologadas individualmente; não confundir agenda de posts com agenda de atendimentos.
- Monitoramento, alertas, métricas agregadas de e-mail e fila durável para recuperação antes de escala.

Não implementar todas essas frentes simultaneamente. Primeiro habilitar e homologar a base existente; depois Instagram e frontend novo.
