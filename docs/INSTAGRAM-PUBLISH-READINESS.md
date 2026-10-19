# Instagram — prontidão de publicação

Revisão estática em 18/10/2026, com a Skill `n8n-workflow-review`. Nenhum acesso à VPS, chamada Meta, execução ou alteração de workflow. Os documentos versionados não comprovam o estado atual nem a versão publicada do n8n.

## Parecer

**Publicação real bloqueada por falta de contrato e evidência funcional.** Há trabalho histórico de publicação e grafos de atendimento Direct, mas não há um export de publicação de posts homologado no Git. A Central de Divulgação pode preparar conteúdo e demonstrar a interface; não deve anunciar conexão, agendamento remoto ou publicação concluída.

## Evidências disponíveis

| Evidência                                                                                | O que permite afirmar                                                                                                                                                                       | Limite                                                                                                                                                                              |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Catálogo n8n](N8N-WORKFLOW-CATALOG.md), ID `A0EcNxcRvfWnMwKI`                           | Documento histórico “Publicar post no Instagram”, atualizado em 14/10/2026; inativo e não arquivado na coleta. Recebeu classificação experimental.                                          | Candidato a export, não exportado entre os arquivos atuais. Trigger, nós, parâmetros, credenciais, formatos, resultado e equivalência com versão publicada não foram coletados.     |
| [Agente experimental](../n8n-workflows/experimental/instagram-agent.json)                | Export inativo, sete nós: Webhook POST → Switch → agente → HTTP; Gemini e memória alimentam o agente. O HTTP envia `recipient.id` e `message.text` ao endpoint Instagram Graph `/messages`. | É atendimento Direct, não publicação de feed. Nó de resposta HTTP sem conexão ao caminho principal. Não comprova entrega.                                                           |
| [Challenge experimental](../n8n-workflows/experimental/instagram-webhook-challenge.json) | Export inativo, sete nós. Webhook GET → resposta; cadeia de agente/Gemini/memória/Switch/HTTP separada do trigger.                                                                          | Verificação de webhook não homologa assinatura de eventos nem publicação. O HTTP preservado aponta `/messages` e não declara POST; não reutilizar esse ramo como integração pronta. |
| [Estrutura Instagram](../n8n-workflows/structure/03-instagram.json)                      | Oito nós com topologia semelhante ao agente, mais ferramenta Sheets. Export inativo, todos os nós desabilitados, parâmetros privados removidos.                                             | Corresponde ao conjunto “Integração Instagram” descrito no catálogo, distinto do ID de publicação. Não contém contrato executável nem credenciais.                                  |

Os templates estruturais foram versionados no commit `3105444bace9cb8d8c6ccc634d637216366b672d`. O [README dos workflows](../n8n-workflows/README.md) e o [README estrutural](../n8n-workflows/structure/README.md) registram a separação entre templates, exports completos e runtime. Nenhum JSON atual contém o ID do workflow de publicação ou operação `media_publish`.

## Formatos e dependências

- **Comprovado apenas no código experimental:** preparação de mensagem de texto para Direct. O código não comprova envio bem-sucedido.
- **Não comprovados:** imagem única no feed, carrossel, vídeo, Reel, Story, publicação imediata, agendamento, métricas ou remoção de posts. O nome do workflow de publicação não demonstra esses recursos.
- **Credenciais declaradas:** HTTP Header Auth (`httpHeaderAuth`) no HTTP de Direct; credencial do modelo Gemini precisa ser selecionada após importar. O template estrutural inclui uma ferramenta Google Sheets, sem configuração ou referência de credencial. Nomes e IDs privados não estão disponíveis e não são necessários nesta revisão; valores não foram lidos.
- **Para publicar futuramente:** app Meta, conta profissional elegível, autorização do titular, vínculo da conta ao workspace, token gerenciado no backend, versão de API suportada e permissões de publicação adequadas à modalidade de login escolhida. Os escopos exatos, revisão do app e requisitos de conta devem ser validados nessa modalidade; não há evidência deles nestes exports. Gemini e Sheets não são requisitos para publicação determinística de conteúdo aprovado. Sheets permanece pausado.

## Lacunas que impedem ativação

1. **Identidade e autorização:** os exports não implementam contrato multi-workspace de publicação. O agente usa remetente da mensagem como chave de memória, sem composição explícita por workspace/canal. O webhook experimental não declara autenticação ou validação de assinatura nos parâmetros exportados. Isso não descreve as proteções eventualmente existentes fora do Git.
2. **Publicação:** faltam entrada validada, limites de mídia/legenda, armazenamento e acesso à mídia, criação/consulta de container, confirmação de publicação e retorno de identificador externo. Não há evidência de operações de feed nem de suporte por formato.
3. **Confiabilidade:** não há contrato de idempotência, deduplicação, timeout, reconciliação após resposta incerta, retry seguro, tratamento de expiração/permissões ou erro apresentado ao usuário para posts.
4. **Versionamento e homologação:** é necessário comparar privadamente documento salvo e versão publicada de `A0EcNxcRvfWnMwKI`, preservar backup e produzir cópia sanitizada/inativa para revisão. O catálogo histórico não autoriza ativar, substituir ou executar esse workflow.

## Contrato futuro recomendado — ainda não implementado

A aplicação autenticada envia uma solicitação ao **backend do SocialMEI**, nunca diretamente ao webhook n8n ou à Meta. Contrato proposto, sem promessa de endpoint disponível:

- Entrada: `connected_account_id`, `draft_id`, `draft_version`, `media_type`, referências de mídia aprovadas, `caption` e `idempotency_key`. O workspace e o usuário vêm da sessão autenticada; o servidor valida propriedade, permissão e confirmação do conteúdo. Tokens e identificadores de workflow não vêm do navegador.
- Começar com **um único formato**, após homologação. Agendamento e demais formatos só aparecem como funcionais quando houver suporte validado. URLs de mídia exigem validação e proteção contra acesso a destinos internos; o conteúdo não pode mudar silenciosamente depois da confirmação.
- Resposta de aceitação: `publication_id` e estado `queued`/`processing`, sem afirmar que publicou. O servidor persiste a solicitação e autoriza a chamada interna ao orquestrador. Restrição idempotente por workspace/conta/chave; mesma chave com conteúdo diferente retorna conflito.
- Resultado: estado `published` apenas após confirmação Meta e persistência de `external_media_id`; incluir `published_at` e URL externa quando disponíveis. Falha retorna código seguro e possibilidade de nova tentativa. Timeout após possível publicação entra em reconciliação, sem repetir cegamente a criação/publicação.
- Consulta de status e eventos internos autenticados verificam workspace, conta e solicitação. Registrar transições e ator, sem tokens ou conteúdo sensível nos logs. Revogação de conexão impede novas publicações. Testes cobrem autorização, isolamento, duplicatas, retorno atrasado, expiração, mídia inválida e confirmação incerta.

Até esse contrato ser implementado e homologado, o frontend deve limitar-se a rascunhos/preparação e ações locais explicitamente identificadas. Copiar texto não equivale a enviar; marcar uma demonstração como concluída não equivale a publicar.

## Verificação desta rodada

Foram lidos os dois exports experimentais, o template estrutural e os documentos citados; conferidos tipos/versões de nós, conexões, métodos HTTP, nomes dos campos de entrada e ausência dos contratos de publicação nos JSONs atuais. Revisão documental, sem testes externos ou alteração de execução. Nenhum segredo foi copiado para este relatório.

## Preparação do piloto nativo — 19/10/2026

A página pública `/form/instagram-post` foi observada **somente em leitura**; a etapa inicial do formulário declara formatos Feed, Story e Reel, escolha de momento e, para Feed, fotos múltiplas com opção de carrossel ou posts separados. Não houve submissão nem autenticação no editor n8n; o workflow de publicação real **continua sem export versionado**.

A nova seção **Divulgação → Instagram · Piloto** usa a identidade visual do app e explica o caminho editor → conferência → formulário da equipe. O fluxo é um **handoff externo**, não upload nativo: o usuário copia a legenda pelo controle existente e seleciona a mídia novamente no n8n. Não há endpoint de publicação nem confirmação de sucesso a partir do SocialMEI.

A ativação depende de configuração pública do ambiente em `SOCIALMEI_CONFIG.instagramPublisher`:

```js
instagramPublisher: { mode: "external-pilot", formPath: "/form/instagram-post" }
```

O padrão no repositório é `mode: "disabled"`. Mesmo quando habilitado, o cliente só aceita caminho `/form/...` na **mesma origem HTTPS** e sessão de negócio disponível, abre uma confirmação e então uma nova aba. Isso **não é autorização de servidor**: só habilitar em ambiente restrito de equipe e com conta Instagram de teste/empresa explicitamente permitida. Não habilitar no Pages, nem para vários MEIs, nem em produção pública sem autenticação e isolamento verificáveis.

**Atualização de 19/10/2026:** recebemos um export do formulário de publicação (40 nós, fluxo de Feed, Reels, Story e agendamento). A análise está em [Auditoria do workflow Instagram](INSTAGRAM-WORKFLOW-AUDIT.md). Isso substitui a afirmação anterior de que não tínhamos export para análise, mas **não comprova versão ativa, credenciais funcionais ou conta autorizada no n8n da AWS**. O arquivo recebido declara outro ID e referencia outro domínio n8n, portanto não é equivalente ao workflow inventariado na AWS.

O piloto também aceita, **somente com opt-in explícito**, URL externa HTTPS de formulário e `approvedOrigin` exatamente correspondente; nenhum domínio externo foi ativado por padrão. A autorização da origem no cliente evita redirecionamento acidental, mas não autentica nem isola a conta Instagram. Não ativar até conferir proprietário da instância e a conta conectada.
