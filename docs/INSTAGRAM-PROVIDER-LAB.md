# Instagram: laboratório de provedor falso

Implementação exclusivamente para testes isolados, sem chamadas de rede, Meta,
n8n, tokens reais ou publicação. Não é uma integração Instagram homologada.
Os contratos anteriores `/instagram/simulation` permanecem intactos.

## Habilitação explícita

Desabilitado por padrão. Exige simultaneamente:

- `SOCIALMEI_INSTAGRAM_PROVIDER=fake`
- `SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT=isolated`
- Autenticação e dados compartilhados já configurados no ambiente descartável.
- Para receber mensagens: `SOCIALMEI_MESSAGE_ENRICHMENT_MODE=stub` e
  `SOCIALMEI_INSTAGRAM_LAB_TEST_KEY` com pelo menos 32 caracteres, gerada somente
  para testes. Não reutilizar segredos Meta/n8n.

A migration incremental `018_instagram_provider_lab.sql` adiciona apenas tabelas
novas. Foi executada somente em PostgreSQL descartável. Instalação em qualquer
ambiente real exige revisão/aprovação própria; a publicação da demo estática não
precisa nem autoriza essa migration. Não altera schemas ou contratos anteriores.

## API autenticada

Prefixo: `/api/v1/instagram/provider-lab`.
Todas as escritas exigem sessão, Origin e CSRF existentes. Gestão exige owner ou
admin; member/viewer só consultam status e fila. Sem endpoint público da Meta.
Respostas autenticadas usam `Cache-Control: no-store`.

| Método e caminho                  | Comportamento                                                                                         |
| --------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `GET /status`                     | connected/disconnected/expired/revoked, sem segredos                                                  |
| `POST /oauth/start`               | State aleatório; hash vinculado a usuário/workspace/sessão, prazo de 5 minutos                        |
| `POST /oauth/callback`            | `{state, code: "fake-authorization-code"}`; consumo único e conexão fictícia com validade de uma hora |
| `POST /connection/disconnect`     | Desconecta, invalida states e cancela aprovação de jobs não concluídos                                |
| `DELETE /connection`              | Revoga com a mesma proteção; nenhuma revogação externa é feita                                        |
| `POST /webhook`                   | Evento JSON fictício autenticado e assinado; não é callback público Meta                              |
| `POST /publications`              | Contrato de mídia de instagram_simulation, idempotência por conta/workspace                           |
| `GET /publications`               | Últimos 100 jobs do negócio autenticado                                                               |
| `POST /publications/{id}/approve` | Aprovação humana explícita de job pending                                                             |
| `POST /publications/{id}/run`     | `{outcome: "success" ou "failure"}`; execução local fictícia, até três tentativas                     |

Não há URLs de autorização externas, PKCE, troca de códigos, refresh tokens ou
armazenamento de credenciais. O código fixo é uma fixture, não credencial.

## Eventos e Caixa existente

O corpo bruto (até 16 KiB, JSON sem chaves duplicadas ou parâmetros na URL) exige
`X-Hub-Signature-256: sha256=<HMAC-SHA256 do corpo bruto com a chave de teste>`.
Campos obrigatórios: event_id UUID, account_id UUID, contact_id começando por
`synthetic:`, contact_name, message_id, text e occurred_at ISO com fuso explícito.

O servidor resolve a conexão pertencente ao workspace autenticado. Não aceita
workspace no payload. A conexão deve estar válida. Ledger durável por evento,
fingerprint do conteúdo validado e deduplicação transacional de mensagem rejeitam replays
conflitantes. Mesma identidade de evento/conteúdo retorna o resultado anterior.

Reutiliza `message_enrichment.persist_incoming`, `me_conversations`, `me_messages`
e `me_external_messages`: nenhuma segunda Caixa. occurred_at preserva o horário
de origem, mesmo quando mensagens chegam fora de ordem. Nenhuma mensagem é enviada
nem uma análise/ação externa é disparada automaticamente.

## Fila e resiliência

Somente metadados de mídia; sem upload, URL pública ou validação real de bytes.
A validação de formatos/tamanho/nome reutiliza PublicationInput. Aprovação não
altera conteúdo. A execução faz claim condicional pending/failed → processing e
conclusão simulated-published/failed na mesma transação: concorrentes não processam
duas vezes e falha de processo reverte o claim. Jobs agendados futuros não rodam.
Após três tentativas, não há retry automático. Desconexão/revogação remove aprovação
dos jobs não concluídos, que não voltam a executar ao reconectar.

Todo resultado mantém `published: false`, `transport: none`, `provider: fake` e
`provider_result.fictional: true`. simulated-published significa apenas conclusão
fictícia, nunca confirmação de publicação no Instagram. Não existe worker externo.

## Verificação e limites

`test_instagram_provider_lab.py` cobre flags fechadas, autenticação, roles,
Origin/CSRF, state expirado/reutilizado/sessão diferente/workspace diferente,
assinatura sobre corpo bruto, limites, escopo, conflitos, mensagens fora de ordem,
revogação/expiração/desconexão, aprovação, falha/retry/idempotência e concorrência.

Não homologa OAuth Meta, App Review, scopes, Stories elegíveis, recebimento externo,
criptografia de tokens, upload real, quotas, worker ou n8n. Habilitar qualquer
operação real exige nova autorização e contratos próprios. Não instalar em produção.
