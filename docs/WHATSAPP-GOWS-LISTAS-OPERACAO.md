# WhatsApp: GOWS e menu por listas — implantação opt-in

## Estado de referência (09/11/2026)

A AWS confirmou WAHA `devlikeapro/waha:latest` com engine padrão `WEBJS`, volume persistente em `/app/.sessions`, `WAHA_NAMESPACE` configurado e `WAHA_SESSION_NAMESPACE` não configurado. A API exige `WEBJS` no webhook, e a opção de enviar listas não estava ativa no claim. Há duas sessões observadas, uma `WORKING` e uma `STOPPED`; a consulta anterior não revelou o engine por sessão.

A produção inclui Prisma e um container de bot independente da imagem do repositório, com catálogo de texto já testado. **Esta branch não altera a produção nem troca as sessões.**

## Mudanças nesta branch

- `SOCIALMEI_WAHA_WEBHOOK_ENGINE`: ausente ou `WEBJS` preserva o comportamento atual. Somente `GOWS` ou `WEBJS,GOWS` com piloto `team-pilot` habilitado aceita(m) eventos assinados do(s) engine(s) correspondente(s). Configuração desconhecida falha fechada.
- `SOCIALMEI_WHATSAPP_LISTS_VERIFIED=true`: junto com o engine `GOWS` e o piloto válido, ativa `/api/sendList` para decisões do bot que possuem opções. Sem isso, permanece `/api/sendText`.
- Resposta de lista assinada aceita somente IDs de opções conhecidos (0–5), com campos de seleção reconhecidos, e rejeita resposta não reconhecida como conteúdo de menu. Não altera o identificador do contato, o escopo do negócio, a idempotência nem a lista permitida.

## Janela de recepção dupla (sem troca de remetente)

- Primeiro: configurar o receptor em modo WEBJS,GOWS, restrito ao piloto autenticado. O worker continua enviando somente para WEBJS, e as listas ficam desligadas.
- Dois engines conectados à mesma conta podem receber o mesmo evento em paralelo. Antes do pareamento GOWS, retirar provisoriamente seu webhook e manter somente o WEBJS produzindo ingresso. Não confiar na deduplicação entre engines.
- Na janela de corte, pausar o worker, parar a sessão WEBJS, ativar o webhook GOWS, direcionar o único worker ao novo host e validar o tráfego real. Só depois homologar a exibição/seleção de listas, restringir o receptor a GOWS e ativar a flag de listas.
- Em rollback, restabelecer um único caminho WEBJS para recepção e envio. Não reenviar automaticamente mensagens com recibo incerto.
- Testes sintéticos HMAC não comprovam a forma real de eventos GOWS: validar sua estrutura sem imprimir telefones nem mensagens.

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


## Falha de pareamento GOWS — triagem segura (09/11/2026)

### Observações do piloto

- A sessão WEBJS permanecia `WORKING`; o worker continuava enviando para `socialmei-waha`.
- A sessão GOWS isolada passou a `FAILED`, com zero webhooks e sem pareamento confirmado.
- A triagem resumida apontou timeout nos logs, mas **não recuperou a razão estruturada do evento de falha**. Timeout isolado não prova QR expirado.
- A primeira tentativa de `restart` de sessão não resolveu o pareamento, segundo o teste no celular.
- A configuração HMAC do webhook GOWS e o volume WEBJS foram copiados em backups privados na AWS. Um backup online que passa na leitura de `tar` não equivale a snapshot consistente do banco/sessão.

### Próxima janela com acesso à AWS e ao aparelho principal

1. **Antes de iniciar outro QR**, inspecionar versão/imagem exatas do container GOWS, código de saída e último `session.status` (inclusive `payload.data.reason.event` e `reason.Reason`) **sem registrar telefones, conteúdo de mensagens, QR ou segredos**. A consulta anterior capturou apenas `s.data` / `s.statusData`, por isso `NAO_INFORMADO` não comprova ausência de motivo no evento.
2. Correlacionar eventos e horários de logs da tentativa: `ClientOutdated` (405), `ConnectFailure`, `LoggedOut`, `TemporaryBan`, `StreamReplaced` ou problemas de rede/timeouts. Evitar tirar conclusão com simples busca de palavras nos últimos logs.
3. Reconhecer os novos estados `PASSKEY_REQUIRED` e `PASSKEY_CONFIRMATION_REQUIRED`: desde WAHA 2026.7 há contas que exigem autenticação WebAuthn/confirmação extra; **não interpretar esses estados como simples QR vencido**. Seguir o fluxo oficial da Dashboard/extensão se ocorrer.
4. Se versão desatualizada for comprovada, avaliar atualização **somente do piloto**, preservando seu volume e mantendo WEBJS intacto. Nunca atualizar tags flutuantes de produção por tentativa e erro.
5. Na próxima tentativa de QR, exibir o código **atualizado** em interface privada para escaneamento imediato. QR salvo em PNG estático pode expirar enquanto a sessão renova o código; não reutilizar imagens antigas.
6. No telefone principal: confirmar WhatsApp atualizado, horário automático, conectividade e disponibilidade de vínculo. **Não remover aparelhos existentes, limpar dados, reinstalar o WhatsApp ou enviar QR/senha no chat.**
7. Manter GOWS sem webhook e sem worker remetente até estar em `WORKING` e passar validação controlada. Se continuar `FAILED`, interromper tentativas e preservar WEBJS.

Fontes: https://waha.devlike.pro/docs/engines/gows/ ; https://waha.devlike.pro/docs/how-to/sessions/ ; https://waha.devlike.pro/blog/waha-2026-7/ .
