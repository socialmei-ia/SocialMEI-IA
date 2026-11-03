# Prévia segura do bot WhatsApp no site

**Estado:** implementado em código para a tela **Configurações → Integrações → WhatsApp**, aguardando homologação/deploy. É uma prévia de **somente leitura** com catálogo real do negócio autenticado. Não é uma conversa WhatsApp, não envia mensagens, não ativa os workflows n8n e não indica que o WAHA está funcionando.

## O que o responsável pode conferir

Na seção **Prévia do menu do WhatsApp**, o responsável escolhe:

- **0 — Menu inicial**: texto formatado com as cinco opções do bot para WAHA WEBJS.
- **1 — Ver produtos**: produtos cadastrados como ativos para aquele negócio, preço e disponibilidade baseada no estoque registrado.
- **2 — Consultar preço e disponibilidade**: pergunta o nome; se informado, pesquisa o produto usando o mesmo planejador Python do atendimento.
- **3 — Conhecer serviços**: lista serviços ativos, sem anunciar estoque de serviço.
- **4 — Solicitar orçamento** e **5 — Falar com atendente**: mostram o texto que seria oferecido, sem abrir ou alterar uma conversa.

O endpoint `GET /api/v1/whatsapp/bot/preview` exige sessão autenticada com papel `owner` ou `admin`; não aceita `workspace_id` de fora e usa exclusivamente `current()['workspace_id']` por meio de `require_owner()`. A consulta inicia uma transação PostgreSQL `READ ONLY`, limita o tempo de execução e utiliza o mesmo `answer()` + `render_waha()` que o planejador real. Não emite credenciais, tokens de canal, números ou ID do contato. Retorna `preview_only=true` e `send_enabled=false`; resposta é renderizada com `textContent`, evitando injeção de HTML.

A prévia fica disponível **mesmo com** `SOCIALMEI_WHATSAPP_BOT_ENABLED=false` e sem canal WAHA cadastrado. Isso permite demonstrar o projeto sem causar envio externo. **Não** habilitar o bot real para visualizar a prévia.

## Limites honestos

- O estado de conversa não é persistido; consultar um produto equivale à etapa após selecionar a opção 2. Nenhuma revisão de conversa, decisão, claim ou handoff é criada.
- Se o workspace está sem itens ativos, a prévia informa que não há produtos/serviços disponíveis e não fabrica preços ou estoque.
- A prévia **não verifica** HMAC, número/sessão WAHA, n8n, execução do agente, entrega de mensagem, autorização de envio ou atualização de estoque pela mensagem do WhatsApp.
- Estoque registrado e disponibilidade comercial são coisas diferentes. Produto com estoque zero continua exibindo “disponibilidade a confirmar”; o responsável deve manter cadastro e preços atualizados.
- A tela é exclusiva dos administradores do próprio negócio; usuários convidados sem papel de administração não podem inspecionar dados internos do catálogo via prévia.

## Verificações

`python-service/test_whatsapp_bot_preview.py` valida resposta do menu WEBJS, preços de um catálogo real simulado, consulta vazia, isolamento por workspace, autenticação, leitura sem SQL de escrita e ausência de decisões do bot em PostgreSQL descartável. O teste `tests/v22-whatsapp-catalog-browser.cjs` exerce a nova prévia em 1440 e 390 pixels, temas claro/escuro, com API sintética e sem solicitações ao WAHA.

**Próximo passo operacional:** aplicar a candidata validada na API/frontend com backup e rollback, cadastrar produtos reais no workspace 1, autenticar como responsável e verificar a prévia no próprio site. Ativação de envio/automação é uma decisão separada, dependente de credenciais, único respondedor, destinatário permitido e homologação.
