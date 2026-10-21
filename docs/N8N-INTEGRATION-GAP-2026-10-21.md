# N8N e SocialMEI.IA — confronto de recursos (21/10/2026)

## Fonte e confiabilidade

Inspeção **somente leitura** no painel `socialmei.54-94-213-7.sslip.io`, sessão autorizada, em 21/10/2026. A inspeção foi visual, não um export completo. Pastas, publicação e nomes de nós vistos não provam que o fluxo publicado está homologado, nem que a versão publicada corresponde ao rascunho. A coleta gerada pelo navegador apresentou contagem de pastas inconsistente; **não usar contagem agregada como inventário definitivo**. As integrações de terceiros e a instância n8n Cloud mencionada em `docs/INSTAGRAM-N8N-PROTOCOL.md` **não foram inspecionadas**. Credenciais, payloads privados e dados de clientes não foram lidos.

## Mapa de integração por funcionalidade

| Requisito da equipe | Evidência visual no n8n AWS | SocialMEI.IA na candidata #83 | Situação / trabalho restante |
| --- | --- | --- | --- |
| Interesse dos clientes: frio, morno, quente | Análise de sentimentos em workflow de revisão inativo; não equivale a lead scoring | Oportunidades já tem heurística e três níveis | **Nesta branch:** ordem solicitada Frio → Morno → Quente e destaque persistente de Em análise; classificação ainda experimental |
| Gerar legenda por IA | **Não localizado por nome na AWS**; pode estar em outra instância | Editor manual, CTA, hashtags, rascunhos | Requer identificar workflow/instância real da equipe, contrato de entrada/saída, autorização e isolamento de dados |
| Gerar imagens por IA | **Não localizado por nome na AWS** | Prévia de mídia enviada localmente, sem gerar arquivos | Requer workflow verificado, provedor, custo, limites de mídia, armazenamento e validação de direitos |
| Montar Feed, Story, Reel | `Publicar post no Instagram` aparece publicado em pasta Revisar; Form Trigger com rotas Feed/Story/Reel | Editor, prévia e exportação; piloto/simulação desconectados por padrão | Workflow foi desenhado para entrada por formulário, não comprovado multi-MEI; não tratar como API do CRM |
| Escolher dia e hora | Grupo de preparar mídia/horário no workflow de publicação | **Nesta branch:** data/hora de intenção de publicação persistida em rascunho local do respectivo usuário/workspace | **Ainda não é agendamento real**; backend de jobs, worker autenticado, storage de mídia, recibo e fuso devem ser entregues separadamente |
| Instagram Direct / atendimento | `[PROD] Instagram — integração` e `[PROD] Atendimento — assistente` aparecem publicados, com Webhook, agente IA e HTTP Graph API | Caixa com simulador/sentimento heurístico, sem conector real | Requer revisão de permissões Meta, conta vinculada por workspace, assinatura dos eventos, antirreplay e política de resposta |
| WhatsApp e sentimentos | Workflows WAHA/Groq e WAHA/Gemini experimentais inativos; análise de sentimentos em Revisar inativa | Mensagens fictícias e rascunhos revisáveis, sem envio | Conector WAHA de teste separado; não trocar nome/ID de cliente sem resolver identidade e isolamento |
| Produto/pedido/estoque | Produtos consultar / Pedidos registrar e confirmar aparecem publicados; Estoque em Revisar | Clientes, produtos, vendas e financeiro via API atual | Não vincular workflows que ainda dependam de Sheets às tabelas de produção sem contratos e migração própria |

## Trabalho implantado nesta branch

- Oportunidades: filtros de interesse e ordenação **Frio → Morno → Quente**, preservando a prioridade separada de suporte/urgência. **Em análise** ficou visualmente identificável em temas claro/escuro e com foco por teclado.
- Divulgação: edição de **dia e hora pretendidos**, conversão explícita de hora local do navegador para ISO UTC, persistência exclusivamente no mesmo escopo local já usado pelos rascunhos, prévia/arquivo exportado e sinalização inequívoca **não enviado/não agendado automaticamente**.
- Os dados antigos de rascunhos sem data continuam legíveis; nem mídia nem credenciais são armazenadas. Sem endpoints externos, sem publicação e sem migração de banco.

## Ordem técnica restante, sem inventar integração

1. **Identificação**: export de estrutura sanitizado + contrato dos workflows geradores de legenda/imagem no n8n da equipe, confirmar propriedade/instância e versão publicada. Não pedir nem versionar tokens.
2. **Base multi-MEI**: modelo e autorização de contas Meta por negócio; registro de mídia privada, formatos, volume, expiração, revisão humana, job persistido/idempotente e estados agendado/processando/publicado/incerto/falha. Agendador confiável não depende do navegador ficar aberto.
3. **Bridge n8n seguro**: callback de servidor assinado, webhook privado específico e chave de serviço isolada; nunca usar o Form Trigger público do workflow como se fosse um endpoint multi-tenant autenticado.
4. **Homologação sem efeito externo**: testes com dois negócios, duas contas, timestamps/fuso, upload e cancelamento, reenvio/retry, rate limit, destino certo, falhas/timeout e publicação desabilitada em todas as defaults.
5. **Teste autorizado com conta Meta de teste**: apenas após revisão de permissões, credenciais, segurança e consentimento. Publicação real ou resposta automática exige autorização separada.

A [PR #83](https://github.com/socialmei-ia/SocialMEI-IA/pull/83) continua candidata a integração, sem merge/deploy nesta etapa. A investigação da Issue #73 permanece separada. Este documento **não comprova** operação real de nenhum canal.
