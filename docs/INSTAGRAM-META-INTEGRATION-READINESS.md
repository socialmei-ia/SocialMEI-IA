# Instagram — preparação técnica, sem credenciais e sem envio

**Escopo:** somente arquitetura e contratos propostos para uma futura fase. Nenhum endpoint Meta foi chamado, nenhum webhook foi publicado e nenhum recurso de publicação foi habilitado. A Divulgação V4 e a Caixa Unificada continuam com controles demonstrativos.

## Fontes Meta consultadas (22/10/2026)

- [Meta Instagram API — coleção oficial](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)
- [Meta — Instagram API with Instagram Login](https://www.postman.com/meta/instagram/folder/6raa77c/instagram-api-with-instagram-login)
- [Business Login — documentação oficial](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login)
- [Instagram Content Publishing](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing)
- [Webhooks de Instagram](https://developers.facebook.com/docs/instagram-platform/webhooks)

Consultar novamente os requisitos e o processo de **App Review / Advanced Access** no painel da Meta antes de solicitar permissões: capacidades e disponibilidade podem variar por produto/versão/região. Nomes de scopes abaixo são da API *with Instagram Login*; não misturá-los com Facebook Login.

## Abordagem proposta

Priorizar **Instagram API with Instagram Login**, sem exigir vínculo com Página do Facebook quando adequado ao caso de uso. Suporta contas **profissionais** (Business/Creator); contas pessoais não devem ser apresentadas como conectáveis. Para quem escolher Instagram API with Facebook Login, criar outro adaptador e uma matriz própria de permissões/Page, sem reaproveitar tokens de um fluxo no outro.

Scopes a solicitar de forma progressiva e justificada:

| Recurso | Permissão |
| --- | --- |
| Identificar a conta profissional | `instagram_business_basic` |
| Receber e responder mensagens admitidas pela plataforma | `instagram_business_manage_messages` |
| Publicar mídia orgânica, após aprovação humana | `instagram_business_content_publish` |
| Gerenciar comentários, somente se produto usar | `instagram_business_manage_comments` |

Não usar os scopes antigos `business_*` (substituídos pelos `instagram_business_*` em 2025). A integração de mensagens não permite iniciar conversas arbitrárias: observar os gatilhos e a janela de atendimento vigentes, conforme a documentação Meta.

## Fronteiras do sistema

```text
MEI autenticado → FastAPI (workspace, autorização) → conexão Meta por workspace
                                     ↓
Meta webhook HTTPS → validação de assinatura/identidade → caixa de entrada durable
                                     ↓
                     deduplicação → conversa/mensagem no PostgreSQL
                                     ↓
                             Caixa Unificada
                                     ↓
                          revisão humana de resposta
                                     ↓
                       outbox (desabilitada no piloto)
                                     ↓
                 worker Meta com limites, retries e auditoria
```

n8n poderá receber **somente eventos filtrados e idempotentes** do backend, sem token Meta, segredo de assinatura ou payload pessoal irrestrito. n8n não deve ser a fonte principal da autorização nem escrever diretamente na tabela de outro negócio.

## Contratos a desenhar e testar em ambiente descartável

1. `POST /api/v1/integrations/instagram/oauth/start` — requer sessão/CSRF, role de administrador do negócio; inicia state de uso único vinculado ao workspace, usuário, nonce e PKCE quando previsto pelo provedor; redirecionamento previamente permitido.
2. `GET /api/v1/integrations/instagram/oauth/callback` — valida state, expiração, vínculo e escopos concedidos; troca código apenas no backend; armazena token criptografado por chave gerenciada fora do banco.
3. `GET /api/v1/integrations/instagram/status` — status sanitizado, scopes e vencimento, **sem tokens**.
4. `DELETE /api/v1/integrations/instagram/connection` — revoga conexão de modo auditável, cancela jobs e mantém histórico conforme política.
5. `GET /meta/instagram/webhooks` — desafio de verificação sem expor segredo.
6. `POST /meta/instagram/webhooks` — valida assinatura sobre o **corpo bruto** com comparação constante, tamanho máximo, versão de payload e origem; rejeita inválidos antes de qualquer gravação.
7. Mensagens: usar os contratos de canal já existentes; proibir dupla criação para `(workspace,channel_account,external_message_id)`. Eventos sem ID confiável exigem política explícita, não adivinhação por nome.
8. Divulgação: preparação → aprovação humana → job com chave idempotente → contêiner de mídia → publicação → confirmação por ID remoto, estados e auditoria. **Não habilitar até homologação.**

Os caminhos são **propostas**, não endpoints existentes no produto. Conferir compatibilidade com API e migrações atuais antes de implementar.

## PostgreSQL e isolamento

Propor tabelas por negócio: `social_connections` (workspace, provider, conta externa, status, scopes, expiry, secret_ref); `social_ingress_events` (workspace, provider, event_id, hash, recebido_em, estado); `social_outbox` (workspace, operation_id único, aprovação, status, tentativa, próximo retry); `social_media_jobs` (workspace, rascunho, mídia, status, remote_container_id, remote_media_id). Não criar estas tabelas antes de revisar as migrations 001–017 e reutilizar a fundação `crm_canais`, `crm_conversas_canal` e `crm_mensagens_canal` quando atender aos contratos.

Cada query e atualização deve autorizar o workspace via sessão/autorização; FKs por workspace; transações para inserção idempotente; vínculos externos exclusivos por conta; token nunca no HTML, URL pública, logs, exports ou n8n.

## Resiliência e segurança

- OAuth state de uso único, checagem de redirect, proteção anti-CSRF e revogação; tokens criptografados, acesso mínimo, renovação antecipada, alertas de revogação e backoff em 429/5xx.
- Webhook recebe e confirma rapidamente, processamento assíncrono no backend; `event_id`/ID de mensagem tratado em transação para **replay seguro** e eventos fora de ordem.
- Envio/publicação **desligados por configuração no servidor**, separados do modo demonstração; nenhum job é criado a partir de clique fictício.
- Isolar upload de mídia: antivírus/validação de MIME e tamanho, URL de curto prazo quando Meta exigir, remoção conforme política; não servir mídia de um negócio a outro.
- Observabilidade: trace sem dados sensíveis, contadores de 4xx/5xx, tokens próximos da expiração, fila atrasada, duplicatas e rejeições de assinatura; LGPD, retenção e exclusão.
- Testes de dois workspaces, replay de webhook, assinatura inválida, contas desativadas, revogação, expiração e job duplicado. Pré-requisito: resolver identificação/isolamento/idempotência A12/A13.
- Conferir versões exatas da Meta Graph API, quotas, regras de janela de mensagens e disponibilidade de Story/Reel/Feed **antes de implementar cada endpoint**.

## Ordem de execução posterior (depende de autorização de conexão real)

1. Definir provedor/login e escopos mínimos junto ao responsável.
2. Aprovar schema/isolamento + threat model; implementar com fixtures e servidor Meta falso.
3. Homologar OAuth, webhook e inbox em staging isolado, com dados fictícios e contas de teste autorizadas.
4. Homologar criação/publicação de conteúdo **somente após revisão humana** e App Review da Meta, quando aplicável.
5. Habilitar por feature flag por negócio, após backup, rollback e avaliação de impacto.

**Gate:** não configurar app Meta, tokens, DNS, webhooks públicos, WAHA, n8n ou publicações nesta PR.
