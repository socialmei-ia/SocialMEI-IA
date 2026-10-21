# Integrações n8n e prioridades da equipe — auditoria 21/10/2026

> Evidência da navegação somente leitura na instância AWS `socialmei.54-94-213-7.sslip.io`. Não houve execução, teste com mensagem, publicação, edição ou acesso a segredos. A publicação de um workflow no painel **não comprova conexão à UI SocialMEI.IA** ou sucesso dos últimos envios.

## Pedidos após a apresentação

- **Oportunidades**: classificação qualitativa **Frio / Morno / Quente** e etapa **Em análise** mais evidente. Existiam no produto, mas a ordem dos filtros e o destaque visual foram refinados nesta PR. Não são probabilidades comerciais calculadas por IA.
- **Divulgação**: escolher Feed, Story ou Reel e dia/hora. O editor já prepara legenda, CTA, hashtags, prévia e rascunho local. Nesta PR foi acrescentado **planejamento local por negócio/navegador**, sem fila executora e sem promessa de publicação. Imagens e vídeos continuam requerendo seleção original.
- **Instagram real**: exigirá vinculação de conta autorizada ao workspace, permissões Meta, armazenamento seguro de mídias, job idempotente, estados observáveis, callback/recibos e agendamento confiável. O Form Trigger atual não constitui API autenticada multi-MEI.

## Workflows encontrados na instância AWS (leitura visual)

| Fluxo no n8n                                                                         | Estado visual        | Uso aparente                                                                  | Próxima integração necessária                                                                                                                    |
| ------------------------------------------------------------------------------------ | -------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Publicar post no Instagram` · 03 Revisar                                            | Publicado no painel  | Form Trigger, grupos Feed, Story, Reels, preparação de mídia/data             | **P0**: validar titular da conta, destino Meta fixo/variável, origem dos arquivos, permissões, sucesso/retry; não ligar diretamente ao navegador |
| `[PROD] Instagram — integração` · 01 Produção                                        | Publicado no painel  | Webhook, Gemini, Switch e chamada à Graph API de mensagens                    | **P0**: separar Direct de publicação; validar assinatura de origem, identidade de conta e workspace, resposta e opt-in                           |
| `[PROD] Atendimento — assistente` · 01 Produção                                      | Publicado no painel  | Assistente/chat e dependências de subworkflows                                | Mapear input/output e vínculos reais; não executar contra dados reais                                                                            |
| `[PROD] Produtos — consultar`, `Pedido — registrar`, `Pedido — confirmar`            | Publicados no painel | Atendimento comercial e pedido; documentação histórica menciona Google Sheets | Comparar modelo de dados com Postgres CRM antes de chamar; não misturar bancos/clientes                                                          |
| `[PROD] Caixa Unificada — PostgreSQL` e `[PROD][LEGACY] Caixa Unificada — API local` | Publicados no painel | Integração legada de mensagens por webhooks                                   | Aplicar contrato de canal por conta/workspace e deduplicação antes de integração real                                                            |
| `[DEV] WhatsApp — WAHA e Groq` e `[REVIEW] WhatsApp — WAHA e Gemini`                 | Não publicados       | Experimentos com WAHA/IA                                                      | Falta conta de teste, vínculo e isolamento por negócio; não ativar para clientes                                                                 |
| `[REVIEW] Análise de sentimentos`                                                    | Não publicado        | Experimento de classificação/IA                                               | Confirmar workflow/IDs reais. PR #82 tem laboratório heurístico desconectado                                                                     |
| `[DEV] Orçamentos — sugestões rápidas`                                               | Não publicado        | Ideias e respostas para orçamento                                             | Definir contratos e fonte de preços autorizada; sem envio real                                                                                   |
| `[OPS] SocialMEI — conferir conexão`                                                 | Não publicado        | Consulta técnica                                                              | Pode auxiliar homologação após autorização, sem gravar dados                                                                                     |

**Gerador de legendas da Alana e gerador de imagem IA do Pedro:** **não identificados por nome ou função explícita nos 31 workflows do projeto nessa instância**. Pode haver uma instância Cloud distinta; o export histórico de publicação menciona domínio externo. **Não confirmado** onde esses dois fluxos estão, se estão ativos ou seus contratos. Pedir ao responsável apenas links/IDs ou exports sanitizados, nunca tokens.

**Qualidade do inventário:** a navegação visual apresentou divergências entre lista na pasta raiz e 03 Revisar e entre IDs de alguns workflows. Portanto, nomes/status acima são pistas para revisão, não prova de equivalência Git ↔ runtime. Os nós de publicação ficaram parcialmente recolhidos; não há prova de conta Meta autorizada por MEI, de execução bem-sucedida, ou de isolamento de conversas.

## Implementação desta PR

1. **Oportunidades**: contexto “Em análise” visível, legenda de temperatura na ordem solicitada e filtros Frio → Morno → Quente, sem alterar pontuação/regras.
2. **Divulgação**: planejamento local de Feed/Story/Reel a partir dos campos do editor com data/hora futura, armazenamento isolado por escopo do navegador, limite de 30, remoção, validação e testes Node. **Nenhum agendamento foi enviado ao n8n, nenhum post foi publicado**. Não vender como recurso remoto.
3. **Não alterados**: FastAPI de canais, banco real, workflow vivo, Meta, WAHA, credenciais, URLs secretas ou flags de Instagram. PR #83 é a base exata.

## Próxima implantação em ambiente autorizado — ainda não executada

- Confirmar a instância que hospeda os workflows de legenda e imagem e receber **contratos não sensíveis**: trigger, campos, formatos, status, sample sintético, dono e versão.
- **Fase 1:** API de agendamento multi-MEI com idempotência, armazenamento privado de mídias, data/hora UTC e status consultável; execução externa **disabled**.
- **Fase 2:** adaptador FastAPI → n8n assinado e versão isolada do workflow de publicação, sem conta Meta fixa e com sandbox autorizado.
- **Fase 3:** conexão Meta por conta/workspace, homologação de Feed e Story com conta profissional de teste, retries, expiração, autorização e rollback. Reels/carrossel posteriormente segundo capacidades reais.
- **Fase 4:** portabilidade das legendas/imagens geradas pela equipe para os rascunhos, com consentimento, rastreio de autoria e revisão humana. Nunca usar prompt/URL arbitrária de usuário como endpoint HTTP interno.

**Antes de dados ou envios reais:** staging identificado, backups reais restauráveis, revisão de permissões da Meta/WAHA/n8n, aprovação de conta de teste e plano de rollback. A release #83 continua Draft e não foi publicada. A investigação CI #73 não está resolvida.
