# WhatsApp: GOWS e menu por listas — implantação opt-in

## Estado de referência (09/11/2026)

A AWS confirmou WAHA `devlikeapro/waha:latest` com engine padrão `WEBJS`, volume persistente em `/app/.sessions`, `WAHA_NAMESPACE` configurado e `WAHA_SESSION_NAMESPACE` não configurado. A API exige `WEBJS` no webhook, e a opção de enviar listas não estava ativa no claim. Há duas sessões observadas, uma `WORKING` e uma `STOPPED`; a consulta anterior não revelou o engine por sessão.

A produção inclui Prisma e um container de bot independente da imagem do repositório, com catálogo de texto já testado. **Esta branch não altera a produção nem troca as sessões.**

## Mudanças nesta branch

- `SOCIALMEI_WAHA_WEBHOOK_ENGINE`: ausente ou `WEBJS` preserva o comportamento atual. Somente `GOWS` com piloto `team-pilot` habilitado aceita evento assinado desse engine. Configuração desconhecida falha fechada.
- `SOCIALMEI_WHATSAPP_LISTS_VERIFIED=true`: junto com o engine `GOWS` e o piloto válido, ativa `/api/sendList` para decisões do bot que possuem opções. Sem isso, permanece `/api/sendText`.
- Resposta de lista assinada aceita somente IDs de opções conhecidos (0–5), com campos de seleção reconhecidos, e rejeita resposta não reconhecida como conteúdo de menu. Não altera o identificador do contato, o escopo do negócio, a idempotência nem a lista permitida.

## Ordem para implantação

1. Criar backup do volume de sessão WAHA, da configuração privada do Compose, do registry HMAC e da definição do fluxo n8n; preservar a imagem atual e um plano testado de retorno ao `WEBJS`.
2. Preparar GOWS em ambiente isolado, com armazenamento próprio para a nova engine e sem acionar o envio real. O namespace de autenticação é específico da engine; **não** apontar o GOWS para os arquivos de autenticação do WEBJS. Evitar `docker pull` ou trocar tags flutuantes indiscriminadamente.
3. Construir/testar a aplicação desta branch, publicar seletivamente o receptor de API e atualizar **o bot customizado em uso** com as duas funções de configuração e o claim. Não supor que um merge GitHub substitui a imagem Docker.
4. Parar o único worker/remetente antes de trocar a sessão ativa. Conectar a conta autorizada no GOWS por QR/código no novo armazenamento; confirmar `WORKING` antes de usar. O receptor WEBJS e os vínculos prévios devem permanecer preservados para reversão.
5. Atualizar canal/registry/assinatura e os dois ambientes para `SOCIALMEI_WAHA_WEBHOOK_ENGINE=GOWS`. Revalidar o formato *real* dos webhooks recebidos (identificador, timestamp, remetente, body e ID de lista), o ingress HMAC, o vínculo por negócio e a lista de contatos autorizados. Eventos incompatíveis devem falhar, não ser descartados silenciosamente.
6. Confirmar uma mensagem de texto real recebida na Caixa e sua resposta pelo único worker. Verificar no WAHA a compatibilidade de `/api/sendList` e da resposta de lista usando **um contato de teste permitido**, antes de definir `SOCIALMEI_WHATSAPP_LISTS_VERIFIED=true` no bot. Fazer a opção 1 e retorno 0.
7. Se a entrega de lista falhar, desativar a flag e manter texto numerado em mensagens **novas**. Não repetir automaticamente tentativas já reivindicadas/incertas ou enviar outra mensagem em substituição sem reconciliação. Se o motor GOWS não funcionar, parar o novo remetente, restaurar somente os containers/configurações anteriores e reativar o WEBJS com seu armazenamento original.

## Condições de saída

- Um único remetente ativo e sessão WAHA `WORKING`.
- Ingresso autenticado com HMAC e contato permitido, com mensagem persistida exatamente uma vez no negócio certo.
- Lista aparece no aparelho do contato de teste, seleção de produtos/serviços gera uma única decisão, catálogo exibe preços/estoque reais, e retorno `0` funciona.
- Registro de recibo/entrega confirmado. Suporte do endpoint por documentação ou HTTP 200 não é, sozinho, prova de exibição da lista no WhatsApp.

Fontes oficiais: https://waha.devlike.pro/docs/how-to/engines/ , https://waha.devlike.pro/docs/how-to/send-messages/ e https://waha.devlike.pro/docs/how-to/storages/ .
