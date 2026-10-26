# SocialMEI — Consulta de catálogo pelo WhatsApp (preparação)

**Estado:** código implementado, mas não implantado nem conectado a fluxos WAHA/n8n ativos. O código **não envia mensagens** por conta própria.

## Contrato do menu

Depois de provisionar e ativar um canal WAHA no banco do workspace, um usuário `owner/admin` autenticado pode criar uma credencial técnica de leitura via:

`POST /api/v1/whatsapp/catalog/access` com JSON `{"channel_id": 123}`.

A resposta contém um token **uma única vez**. Armazene-o apenas nas credenciais privadas do n8n; a API grava somente SHA-256. Renovar esse token invalida imediatamente o anterior. `DELETE /api/v1/whatsapp/catalog/access/{channel_id}` revoga.

O fluxo WAHA existente deve extrair a seleção digitada pelo cliente, identificar a instância confiável e usar uma requisição **GET** para a API:

`/api/v1/integracoes/whatsapp/menu?instancia=canal-existente&opcao=2&produto=arroz`

Cabeçalho: `Authorization: Bearer <SEGREDO_PRIVADO_NO_N8N>`.

Resposta limitada a no máximo 10 itens do catálogo **real**, somente no workspace vinculado ao token e à instância WAHA. Opções: 0 menu, 1 produtos, 2 preço/estoque, 3 serviços, 4 solicitar orçamento humano, 5 atendimento humano. A opção 2 sem nome pede esclarecimento. Sem produto em estoque, retorna `indisponivel`; serviços não inventam estoque. A busca é somente leitura e não altera inventário.

## Antes de habilitar

1. Conferir backup, migração `030_whatsapp_catalog_access.sql` e papel/autorização.
2. Configurar flag privada `SOCIALMEI_WA_CATALOG_ENABLED=true` na API.
3. Confirmar proxy Caddy encaminha o Bearer apenas para rota exata do menu.
4. Inspecionar workflows n8n/WAHA atuais antes de introduzir qualquer sender, pois alguns fluxos podem responder automaticamente. **Não ativar dois emissores.**
5. Fazer testes com duas contas e dois workspaces para confirmar ausência de vazamento, e com mensagem real após autorização.

Esta implementação não acrescenta conexão automática ao n8n, não acessa sua instância por conta própria e não publica nada.
