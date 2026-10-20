# Contrato futuro — FastAPI → n8n → Meta (sem ativação)

## Origem desta especificação

Esta interface foi mapeada a partir do export recebido **Publicar post no Instagram**,
com 40 nós: `Form Trigger` em duas etapas; normalização dos campos
`tipo_publicacao`, `legenda`, `modo_varias`, `quando_publicar`,
`data_agendamento` e `hora_agendamento` em `America/Sao_Paulo`; upload
ImgBB/Cloudinary; Wait; rotas Feed/Carrossel/Reels/Story e respostas finais.
O export indica uma instância diferente (`facepe2027.app.n8n.cloud`).
O arquivo original não foi commitado, nem há confirmação de execução ativa.

**Não confundir formulário público com webhook autenticado.** O export usa
uma conta Meta fixa e não atende vários MEIs sem adaptar as rotas Meta.

## Disponível agora

`python-service/instagram_n8n_protocol.py` é **biblioteca pura offline**.
Ela constrói o corpo de um futuro pedido de trabalho, serializa JSON
deterministicamente e cria/verifica HMAC-SHA256 com timestamp (janela de
5 minutos). Não há chamada HTTP, endpoint, worker ou credencial configurada.

Formato: `socialmei.instagram.publish.v1`, com os campos:

- `publication_id` / `operation_id`: UUIDs do registro e do comando idempotente.
- `workspace_id`: definido no backend pela sessão, nunca pelo navegador.
- `linked_account_id`: UUID interno da **conta vinculada e autorizada**, nunca
  ID da conta Meta ou endereço escolhido pelo cliente.
- `format`: `feed`, `story` ou `reel`.
- `feed_mode`: `single`, `carousel` ou `separate` somente para Feed.
- `caption`: até 2.200 caracteres. Story pode desconsiderar a legenda.
- `media`: lista de 1 a 10 identificadores UUID internos `asset_id` e `mime`,
  não URLs públicas, bytes binários ou caminhos externos.
- `scheduled_for`: ISO 8601 UTC ou `null`; validação futura mínima de
  1 minuto e máxima de 60 dias na preparação.

**Limites deliberadamente conservadores deste contrato futuro:** JPEG/PNG
para Feed; JPEG/PNG/MP4 para Story; MP4 para Reels. Não significa que todo
arquivo desse tipo será aceito pela API Meta: formatos, duração, codec,
resoluções, assinatura binária e limites devem ser homologados posteriormente.
Isso não altera os formatos aceitos pelo *simulador* já existente.

## N8n: evolução necessária

1. Criar um **novo webhook interno**, separado do Form Trigger original, com
   autenticação de serviço, payload limitado e verificação HMAC do **corpo bruto**
   antes de processar qualquer dado. O template e o endpoint ainda não existem.
2. Deduplicar `operation_id` no banco persistente e rejeitar replays;
   timestamp sozinho **não** oferece proteção de replay. Não deixar uma
   execução duplicada publicar pela segunda vez.
3. Receber o `linked_account_id` mas resolver a titularidade no backend
   confiável, com credenciais armazenadas somente em secret store.
   **Nunca** usar o ID de Meta fixo presente no export.
4. Resolver `asset_id` com acesso temporário autorizado à mídia, validar MIME,
   assinatura e limites reais. Não permitir URL arbitrária/SSRF.
5. Implementar estados `queued`, `processing`, `published`, `failed`,
   `uncertain` com callback autenticado, recuperação após timeout e
   reconciliação pela Meta. Agendamento precisa ser durável após reinício.
6. Manter o workflow antigo isolado até haver testes de cada ramo com
   conta fictícia/conta Meta de teste devidamente autorizada.

## Gates de segurança antes de habilitar

- Confirmar local do workflow, titular da instância e permissão da conta Meta.
- Criar vínculo de conta verificado por workspace e revogável, sem token no JS.
- Criar armazenamento privado, registros de job e workers idempotentes.
- Testar Feed único, carrossel (2 e 10 fotos), Feed separado, Story,
  Reel, rejeições de mídia, timezone, erros Meta e reexecuções.
- Configurar allowlist de URL e TLS no servidor, rotação de segredo HMAC,
  resposta de recibo assinado e limite de tamanho/taxa.

**Estado atual:** apenas proposta de protocolo com testes offline,
em PR de desenvolvimento. **Nenhum envio externo foi habilitado.**
