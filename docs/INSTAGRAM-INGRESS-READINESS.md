# Instagram: preparação do recebimento

## Escopo desta entrega

Preparar e testar o caminho conta fictícia → negócio → conversa → mensagem, reutilizando o laboratório de análise existente. Não conectar conta Meta, ativar n8n, publicar ou responder mensagens reais. A atualização visual ocorre em trabalho separado; esta extensão não exige alterações de frontend.

O responsável Alessandro relatou que uma conta já está ligada a uma automação e responde mensagens, com configuração no Meta Developers. Isso é **relato aguardando verificação**, não evidência de que o dashboard recebe esses eventos ou de que a automação está homologada para vários negócios. O cadastro manual de participantes também precisa ser conferido no aplicativo correto; não concluir o modo ou as permissões apenas pelo relato.

## O que já existe e será reutilizado

- `python-service/instagram_simulation.py`: contas fictícias com UUID gerado no servidor; `GET/POST /api/v1/instagram/simulation/accounts`. Owner/admin cria; a sessão determina o negócio. Essas contas pertencem ao simulador de postagem e **não representam vínculo autorizado com a Meta**.
- `python-service/channel_ingress.py`: recepção de fixtures assinadas, validação estrita, prazo de assinatura, limite de corpo e rejeição de JSON com campos duplicados. O ingresso WAHA-shaped existente permanece separado.
- `python-service/message_enrichment.py`: `persist_incoming` grava em `me_conversations`, `me_messages` e `me_external_messages`. Deduplicação, transação, lock por negócio, quota, heurística sintética, fontes lexicais e revisão já existem.
- `/api/v1/message-enrichment/conversations`: consulta autenticada das mensagens do próprio negócio; o laboratório da Caixa pode apresentar esses registros sem um segundo painel.

Não há criação automática de cliente CRM. O laboratório persiste identidade de contato e conversa; vincular isso a `crm_clientes` exige uma decisão explícita e não pode ocorrer por nome de exibição. `crm_canais` e as tabelas operacionais relacionadas da migration009 ainda restringem canal/provedor a WhatsApp/WAHA. Não escrever mensagens Instagram diretamente nessas tabelas.

## Contrato de laboratório

O ingresso `POST /internal/channel-ingress/instagram-fixture` recebe um envelope normalizado de teste. **Não é webhook Meta**, não valida uma assinatura Meta e não deve ser fornecido como callback público para o Instagram.

A entrada utiliza estes campos; o modelo executável em `channel_ingress.py` é a fonte dos limites completos. Campos extras, incluindo `workspace_id`, são rejeitados. O produtor de fixture é interno e nunca entrega a chave ao navegador.

| Campo            | Contrato                                                                       |
| ---------------- | ------------------------------------------------------------------------------ |
| `schema_version` | Inteiro estrito `1`.                                                           |
| `event_id`       | UUID como string canônica; identifica a operação.                              |
| `timestamp`      | Inteiro estrito, segundos de epoch; validade ±120 segundos.                    |
| `account_id`     | UUID canônico da conta fictícia existente, gerado pelo servidor.               |
| `kind`           | Somente `incoming_text`.                                                       |
| `sender_ref`     | Referência fictícia com prefixo `fixture-`, por exemplo `fixture-participant`. |
| `sender_name`    | Nome de exibição fictício, por exemplo `Pessoa fictícia`; não é identidade.    |
| `message_id`     | Identidade externa fictícia, 1–120 caracteres.                                 |
| `text`           | Texto recebido, até 8192 bytes.                                                |
| `signature`      | HMAC-SHA256 em 64 caracteres hexadecimais minúsculos.                          |

A assinatura HMAC-SHA256 usa JSON canônico sem o campo de assinatura (`sort_keys=True`, `separators=(',', ':')`, `ensure_ascii=True`), com a mesma função de teste existente. O corpo total é limitado a 16 KiB. A validação de esquema, assinatura, tamanho e janela temporal de ±120 segundos antecede acesso ao banco. A chave é exclusiva de teste; não é token Meta nem credencial n8n.

O servidor procura o UUID da conta em `instagram_sim_accounts` e exige **exatamente um proprietário global**. Embora a API gere UUIDs aleatórios, a chave do banco é composta por negócio/UUID: zero linhas retorna conta desconhecida e mais de uma linha é ambiguidade e deve falhar sem gravar. Não escolher a primeira linha, aceitar seletor de negócio do produtor ou inferir propriedade pelo rótulo da conta.

O `account_ref` persistido usa `synthetic:instagram-fixture:<uuid>`. A identidade fictícia do remetente recebe hash e passa para o namespace sintético de contato. Nomes iguais não unem contatos diferentes. O horário armazenado é o de recepção; não afirmar que representa o horário original do provedor.

Reenvio com os mesmos dados devolve a mensagem existente. Mesmo ID externo com dados diferentes retorna conflito. Outra operação UUID com o mesmo ID externo e dados iguais também não duplica mensagem. O escopo da identidade externa inclui negócio, canal e conta.

O resultado permanece `mode: fixture`, `transport: none`, `sent: false`. O status autenticado `/api/v1/channel-lab/instagram/status` devolve `workspace_id`, `mode: fixture|disabled`, `account_source: instagram_simulation`, `fixture_ingress_available`, `connected: false`, `can_receive_real: false`, `can_send: false`, `can_publish: false`, `transport: none`, `readiness_state: not_connected` e `blockers`. Não existem endpoints OAuth, conectar ou desconectar nesta extensão. Habilitar o laboratório não autoriza receber, enviar ou publicar pela Meta. O proxy do preview continua recusando `/internal/*`; o produtor de teste acessa somente a API interna no ambiente descartável.

## Inventário dos exports Git

Leitura estática em 21/10/2026: 16 arquivos JSON, todos declarando `active: false`. Isso descreve os arquivos, não a instância viva. Os oito arquivos `structure/` são templates sanitizados com parâmetros removidos e nós desabilitados; não são workflows prontos para executar.

| Arquivo em `n8n-workflows/`                       | Nós | Evidência e uso possível                                                                       |
| ------------------------------------------------- | --: | ---------------------------------------------------------------------------------------------- |
| `structure/00-caixa-local.json`                   |   6 | Webhooks, código e respostas; referência de caixa legada.                                      |
| `structure/01-caixa-postgresql.json`              |   8 | Webhooks/PostgreSQL; não promover a ingresso multiempresa sem contrato.                        |
| `structure/02-atendimento.json`                   |   7 | Agente Groq, memória e ferramentas de subworkflow; revisar conjunto de dependências.           |
| `structure/02a-consultar-produtos.json`           |   2 | Subworkflow/Sheets; Sheets permanece pausado.                                                  |
| `structure/02b-registrar-pedido.json`             |   2 | Subworkflow/Sheets; não ligar escrita legada ao CRM.                                           |
| `structure/02c-confirmar-pedido.json`             |   9 | Subworkflow/Sheets e condições; não ativado nesta entrega.                                     |
| `structure/03-instagram.json`                     |   8 | Webhook, agente Gemini, memória, Sheets Tool e HTTP; parâmetros reais precisam de conferência. |
| `structure/04-conferir-conexao.json`              |   2 | Trigger manual/HTTP; não chamado nesta revisão.                                                |
| `equipe/01-conferir-conexao.json`                 |   2 | Conferência HTTP; destino e autorização precisam ser validados antes de execução.              |
| `experimental/instagram-agent.json`               |   7 | Protótipo de webhook/agente Gemini/memória/HTTP; sem homologação.                              |
| `experimental/instagram-webhook-challenge.json`   |   7 | Outro protótipo; nome não comprova handshake ou autenticação real.                             |
| `experimental/scheduled-request-draft.json`       |   3 | Schedule Trigger e HTTP; destino pendente, sem uso como scheduler.                             |
| `examples/hello-world.json`                       |   3 | Webhook/Set/resposta; exemplo técnico.                                                         |
| `examples/process-text.json`                      |   2 | Trigger manual/HTTP; exemplo da API auxiliar, distinto da API CRM.                             |
| `examples/python-native-check.json`               |   2 | Trigger manual/Code; conferência de executor.                                                  |
| `producao/01-caixa-unificada-api-postgresql.json` |   8 | Legado GET/POST/PostgreSQL; pasta não comprova produção ou isolamento atual.                   |

Não foi identificado nesses exports um gerador funcional de legendas, imagens ou um contrato vivo de sentimento/RAG. As declarações da equipe continuam como pendências de conferência. A auditoria anterior do formulário de publicação veio de outra origem n8n Cloud; não confundir com a instância AWS. Nesta entrega nenhum webhook vivo é chamado, workflow executado ou credencial consultada.

Detalhes e histórico: [matriz de capacidades](N8N-CAPABILITY-MATRIX.md), [catálogo por ID](N8N-WORKFLOW-CATALOG.md), [integrações prioritárias](PRIORITY-INTEGRATIONS.md), [auditoria de publicação](INSTAGRAM-WORKFLOW-AUDIT.md) e [protocolo futuro de postagem](INSTAGRAM-N8N-PROTOCOL.md).

## Matriz de testes

Todos os cenários automatizados usam PostgreSQL descartável, contas e conteúdo fictícios. Não usar `TEST_DATABASE_URL` de banco team, AWS ou de trabalho.

| Cenário                                                   | Resultado esperado                                                 |
| --------------------------------------------------------- | ------------------------------------------------------------------ |
| Conta fictícia conhecida e evento textual válido          | Uma conversa e uma mensagem no negócio proprietário; nenhum envio. |
| Segunda sessão do mesmo negócio                           | Consulta a mesma mensagem persistida.                              |
| Outro negócio e mesmos nomes de contato                   | Dados isolados; nenhuma união por nome.                            |
| UUID de conta desconhecido                                | Recusa sem criar conta/conversa/mensagem.                          |
| Mesmo UUID atribuído a dois negócios no banco de teste    | Conflito de ambiguidade, sem escolher proprietário.                |
| Mesmo evento repetido, inclusive simultaneamente          | Mesmo ID de mensagem; nenhuma duplicação.                          |
| Novo evento, mesma mensagem externa e mesmo conteúdo      | Replay da mensagem existente.                                      |
| Mesmo ID externo com texto ou remetente diferente         | Conflito; original preservado.                                     |
| Mesma mensagem externa em contas diferentes               | Registros independentes por conta/negócio.                         |
| Campo livre de workspace ou campo extra                   | Recusa antes de persistência.                                      |
| Assinatura inválida, corpo alterado ou evento expirado    | Recusa antes de acesso ao banco.                                   |
| Modo desabilitado ou flags inválidos                      | Falha fechada; nenhuma recepção habilitada implicitamente.         |
| Corpo excessivo, JSON duplicado, mídia ou evento de saída | Recusa; sem download ou transporte.                                |
| Enriquecer e aprovar resposta                             | Resultado sintético e rascunho revisado, nunca envio.              |

O status desta matriz é roteiro de aceitação; os resultados efetivamente executados devem ser registrados na PR/CI do HEAD correspondente. Não inferir aprovação de testes apenas pela existência do documento.

## O que conferir com Alessandro antes do Instagram real

1. Identificar a instância correta e o ID do workflow, a versão publicada e as dependências. Nome do fluxo sozinho não basta. Preservar export privado antes de eventual mudança; não enviar JSON bruto com parâmetros, URLs, código, pinData ou credenciais no chat.
2. Confirmar quem controla o aplicativo Meta, o tipo da conta profissional e quais participantes de teste estão autorizados. Registrar somente metadados necessários; senhas e tokens ficam no mecanismo privado apropriado.
3. Conferir o evento real sanitizado, assinatura oficial, IDs de conta/remetente/mensagem, direção, mídia, timestamp e reenvio. Adaptador real deve validar autenticidade antes de confiar nesses campos.
4. Projetar vínculo autorizado e revogável da conta real ao negócio. O UUID do simulador e o formulário de preparação não substituem esse vínculo.
5. Conferir consulta de produtos/preços/disponibilidade no backend correto. Uma resposta do agente não pode inventar estoque ou confirmar pagamento, pedido ou venda sem operação explícita.
6. Testar na conta autorizada perguntas de produto/preço, informação ausente, desistência, retomada, repetição, falha do agente e revisão humana. Conferir a resposta recebida no Instagram e seu registro no dashboard.
7. Somente então definir callback HTTPS real, autenticação de serviço, permissões, retenção, observabilidade, revogação e mecanismo de envio com idempotência e reconciliação. Integrações de postagem, legendas e imagem têm homologação própria.

Nenhuma dessas etapas autoriza alterar AWS, Caddy, banco produtivo ou workflows vivos nesta entrega. Deploy e migrations em produção continuam exigindo autorização específica, estado confirmado, backup/rollback e verificação posterior.
