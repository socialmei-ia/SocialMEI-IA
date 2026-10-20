# Contrato futuro — FastAPI → n8n → Meta (sem ativação)

## Origem desta especificação

Esta especificação foi mapeada do export recebido **Publicar post no Instagram**, com 40 nós. O fluxo contém Form Trigger em duas etapas, `tipo_publicacao`, `legenda`, `modo_varias`, `quando_publicar`, `data_agendamento`, `hora_agendamento` em `America/Sao_Paulo`, ImgBB/Cloudinary, Wait e rotas Feed/Carrossel/Reels/Story. O export referencia uma instância diferente (`facepe2027.app.n8n.cloud`). Não há confirmação de ativação atual ou de permissões de conta Meta.

**O Form Trigger público não substitui um webhook autenticado.** O export também usa um ID de conta Meta fixo, incompatível com múltiplos MEIs sem adaptar as rotas de publicação. O JSON original não foi commitado.

## Biblioteca disponível

`python-service/instagram_n8n_protocol.py` é uma **biblioteca offline** para preparar um eventual job, serializar JSON estável, assinar o corpo UTF-8 usando HMAC-SHA256 e validar a assinatura com timestamp dentro de cinco minutos. **Ela não cria endpoints, solicitações HTTP, workers, credenciais ou publicações.**

O esquema `socialmei.instagram.publish.v1` contém somente estes campos:

- `publication_id` e `operation_id`: UUIDs do registro e do comando idempotente.
- `workspace_id`: número do negócio, resolvido pelo servidor a partir da sessão, nunca recebido livremente do navegador.
- `linked_account_id`: UUID interno de uma conta vinculada e autorizada; não é ID público da conta Meta.
- `format`: `feed`, `story` ou `reel`.
- `feed_mode`: `single`, `carousel` ou `separate` no Feed; `null` para Story/Reel.
- `caption`: texto com até 2.200 caracteres.
- `media`: 1 a 10 registros `{asset_id, mime}` com UUIDs internos, sem bytes ou URLs externas.
- `scheduled_for`: ISO 8601 em UTC ou `null`; o contrato preparado aceita intervalo futuro de 1 minuto a 60 dias.

Os formatos provisórios são JPG/PNG para Feed, JPG/PNG/MP4 para Story e MP4 para Reel. Eles precisam de homologação de codec, duração, tamanho, assinatura binária e regras atuais da Meta antes de qualquer envio. O simulador existente mantém suas próprias validações.

## Mudanças necessárias no n8n

1. Criar um **webhook interno novo** e privado, separado do Form Trigger, com autenticação de serviço, limite de tamanho e conferência da assinatura HMAC do corpo bruto antes de executar outros nós.
2. Resolver `linked_account_id` no backend seguro, garantindo autorização e permissão do negócio; **não** continuar usando o destino Meta fixo do workflow original.
3. Resolver `asset_id` via armazenamento privado e acesso temporário limitado; nunca buscar URLs arbitrárias de mídia enviadas pelo navegador.
4. Persistir e deduplicar `operation_id`; além do timestamp, exigir controle de replay e idempotência durável antes do primeiro envio Meta.
5. Implementar recibo com estados `queued`, `processing`, `published`, `failed` e `uncertain`; o callback precisa ser autenticado e falhas de timeout exigem reconciliação com a Meta.
6. Agendar de forma recuperável após reinício, com timezone explícito, validação de data passada e limites reais da Meta.
7. Homologar Feed simples, carrossel de 2 e 10 imagens, posts separados, Story e Reel com conta Meta de testes autorizada, incluindo mídia inválida, reenvio e falhas de processamento.

## Portões de ativação

- Confirmar quem controla o n8n Cloud da FACEPE e a instância AWS do SocialMEI, onde o fluxo ficará e qual conta será usada no teste.
- Criar vínculo de conta verificado por workspace e revogável, sem segredos no frontend.
- Implementar armazenamento privado, registro de job, worker autenticado e mecanismo antirreplay.
- Configurar URL interna permitida, HTTPS, segredo de serviço protegido, observabilidade sem tokens e limites de taxa.
- Revisar e testar o workflow modificado antes de ativar ou executar publicações reais.

**Estado:** apenas protocolo e testes offline em uma PR de desenvolvimento. Nenhum upload, webhook, n8n, Meta, merge ou deploy foi executado.
