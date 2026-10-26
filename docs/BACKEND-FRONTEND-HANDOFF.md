# Backend para o próximo frontend

Base de desenvolvimento: #110 + #102, preservadas por merge na branch `feat/backend-provider-readiness`. A interface será fornecida pelo proprietário: não houve redesign ou substituição do HTML/CSS nesta rodada. Código preparado/testado não comprova instalação na AWS.

## Fontes únicas

- FastAPI e PostgreSQL existentes; candidata atual com migrations001–026. As migrations024–026 acrescentam recuperação, identificadores públicos de sessões e fila de e-mail; foram ensaiadas somente em ambiente descartável.
- Contas e negócio são resolvidos pela sessão no servidor. Nunca aceitar workspace escolhido no navegador como autorização.
- O frontend atual usa scripts clássicos/stores existentes. Um novo frontend pode reutilizá-los ou consumir os mesmos contratos, sem criar autenticação/banco paralelo.
- Servir frontend e API na mesma origem HTTPS, com cookie de sessão Secure/HttpOnly. Não guardar tokens de Meta/n8n em localStorage, HTML ou config.js.

## Contratos de gestão disponíveis

| Necessidade                     | API                                                       | Observação                                                                                                                                        |
| ------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Política do cadastro            | GET `/api/v1/auth/registration`                           | Informa aberto/convite; não presumir cadastro aberto                                                                                              |
| Cadastro/login                  | POST `/api/v1/auth/register`, `/api/v1/auth/login`        | JSON e cabeçalhos Origin e X-SocialMEI-Client: browser; senha nova8–128, sem composição obrigatória e com bloqueio de padrões extremamente comuns |
| Sessão/identidade               | GET `/api/v1/auth/session`, `/api/v1/auth/me`             | Session pode retornar200/null; me sem sessão retorna401                                                                                           |
| Trocar senha/sair               | POST `/api/v1/auth/password`, `/api/v1/auth/logout`       | Cookie, Origin e X-SocialMEI-CSRF; troca revoga sessões anteriores                                                                                |
| Perfil/configurações essenciais | `/api/v1/workspace-profile`, PATCH `/api/v1/auth/profile` | Reutilizar revisão, papéis e confirmação de importação locais                                                                                     |
| Clientes                        | `/api/v1/clientes`                                        | CRUD por negócio, versões e importações existentes                                                                                                |
| Produtos/serviços               | `/api/v1/produtos`                                        | Produto e Serviço têm contratos distintos de estoque; nunca inventar preço/quantidade                                                             |
| Vendas/estoque                  | `/api/v1/vendas`                                          | Ações idempotentes e estoque atômico; pagar venda não duplica lançamento financeiro                                                               |
| Financeiro                      | `/api/v1/financeiro`                                      | Receita/despesa e quitação pelos contratos existentes                                                                                             |
| Oportunidades                   | `/api/v1/opportunities`                                   | Ciclo e planejamento compartilhado da #109, revisão esperada, undo escopado e importação legada explícita                                         |
| Capacidades de backend          | GET `/api/v1/integrations/readiness`                      | Autenticado; não retorna segredos nem afirma conexão externa inexistente                                                                          |

Consultar `/openapi.json` no ambiente descartável e `docs/API-ENDPOINTS.md` para os modelos completos. Os modelos Python são a autoridade. Produtos usam `expected_version`; Oportunidades usa `expected_revision`. Reutilizar a mesma operação em repetição de resposta perdida; uma nova intenção recebe novo identificador.

## Regras da interface nova

- Listar dados reais somente após sessão e carregamento confirmados; apresentar401/403/409/422/503 de forma honesta.
- Em erro remoto não salvar silenciosamente no navegador. Manter formulário preenchido e permitir recuperação/revisão.
- Sugestões de onboarding não são produtos: salvar apenas após confirmação com preço/estoque definidos pelo empreendedor.
- Distinguir registros locais, demonstração e servidor. Não mesclar amostras com cadastros reais.
- Não tratar autenticação do SocialMEI como autorização automática de Instagram/WhatsApp.
- Não rotular preparação, fila ou confirmação de recebimento de provedor como mensagem entregue ou post publicado.

## Instagram e n8n da equipe

O proprietário confirmou que o atendimento com IA e a publicação já funcionam em `socialmei.54-94-213-7.sslip.io`. A intenção é reutilizar esses workflows. A presente conversa não possui acesso de rede/segredo para auditá-los ao vivo; nenhum workflow foi executado, ativado, exportado ou alterado.

`readiness.n8n.workflow_review=pending_live_contract` significa contrato ainda não conferido pelo aplicativo; não significa falha do workflow do colega. A chave N8N_API_KEY é administrativa, para auditoria read-only, e não deve virar credencial do navegador nem credencial genérica de todos os negócios.

Antes da ponte efetiva, confirmar com o responsável:

1. IDs/versões publicadas e entradas/saídas de atendimento e publicação; o export histórico de formulário não é automaticamente uma API autenticada.
2. Como a conta Instagram é vinculada ao negócio e se existe destino fixo. O backend autoriza a conta; não o campo enviado pelo navegador.
3. Autenticação de serviço/assinatura, idempotência, consulta/callback de status e tratamento de resultado incerto.
4. Contrato de mídia/armazenamento, formatos e agendamento. Confirmação de publicação deve incluir identificador externo válido.
5. Quem responde ao Direct: não ativar simultaneamente automação n8n e outbox do SocialMEI sem política de responsabilidade e deduplicação.
6. Como o agente consulta o catálogo do negócio correto. As rotas técnicas legadas de leitura de workspace fixo não se tornam multi-MEI apenas reutilizando um token.

O adaptador Meta opcional desta entrega não recria o agente de IA nem o workflow de posts. Ele conecta os componentes já existentes a configuração de servidor e serve de alternativa/controlador de autorização após homologação. Não é prova de integração com os workflows vivos; pode permanecer desligado enquanto a ponte n8n for definida.

## WhatsApp

A #110 já contém recepção durável, assinada e isolada no contrato WEBJS. Sem número dedicado, não iniciar sessão nem exibir QR fictício. Faltam número/conta aprovados, verificação da versão/engine/HMAC real do WAHA, registry e chave de servidor, roteamento e homologação. Mídia/grupos e envio não são afirmados como disponíveis. Os testes usam identificadores sintéticos e banco descartável.

## Publicação e próximos portões

Preservar landing para anônimos e gateway sem Basic da #102. Não reconstruir o gateway público pela configuração privada antiga. A referência de webhook no Caddyfile.public é apenas código: alteração do proxy vivo, segredos, migrations reais, contas de teste, pareamento, envio e publicação exigem autorização específica. Manter backups/rollback equivalentes aos hotfixes do servidor.

Esta candidata não é o pacote password-only da PR #102: contém os módulos de backend herdados até a #110 e o runtime opcional. Uma futura implantação exige imagem completa compatível da API, dependências e migrations001–026 verificadas, sob autorização específica; não copiar um único arquivo para uma API antiga. O frontend visual novo continua fora desta rodada e o pipeline n8n vivo não foi alterado.

## Consulta do catálogo por negócio

GET `/api/v1/produtos` mantém o retorno original (lista de itens e mesma ordenação) quando não há filtros. Agora aceita filtros opcionais combináveis:

- `q`: trecho literal do nome, sem diferenciar maiúsculas/minúsculas, até160 caracteres. `%` e `_` não são curingas SQL; não há promessa de busca sem acentos.
- `tipo`: `Produto` ou `Serviço`.
- `status`: valor exato cadastrado, entre1 e30 caracteres.
- `estoque_baixo=true`: apenas produtos físicos com estoque menor ou igual ao mínimo, inclusive zero. Não trata serviços como estoque; não filtra por situação automaticamente.

Exemplo: `/api/v1/produtos?q=perfume&tipo=Produto&status=Ativo&estoque_baixo=true`.

A consulta usa a identidade da sessão e parâmetros SQL; não aceita escolher outro negócio por query. Não grava dados nem altera preço/estoque. Estes filtros são contratos de frontend autenticado, não uma nova autorização para workflows n8n: acesso de serviço por negócio continua exigindo o contrato/vínculo que será homologado com a equipe.

## Ponto de continuidade: novo frontend

O proprietário enviará um ZIP com o novo visual. Antes de integrá-lo, seguir [o checklist de recebimento e as pendências preservadas](NEXT-FRONTEND-INTEGRATION.md). O frontend atual permanece intacto até receber o pacote.

Contratos adicionais preparados: `GET /api/v1/auth/sessions`, `POST /api/v1/auth/sessions/{id}/revoke`, `POST /api/v1/auth/sessions/revoke-others`, `POST /api/v1/auth/recovery/request`, `POST /api/v1/auth/recovery/confirm` e diagnóstico exclusivo de administrador `GET /api/v1/admin/diagnostics`. Modelos/cabeçalhos/estados estão em [operação do backend](BACKEND-OPERATIONS-READINESS.md). A configuração SMTP e o worker não estão homologados na AWS.
