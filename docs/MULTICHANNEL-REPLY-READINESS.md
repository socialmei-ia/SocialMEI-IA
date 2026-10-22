# Preparação de respostas multicanal — manutenção

## Base e dependências

Base: PR #92, `c2a0dfcf4c4caf86df9aac54eafeab33bdbd4daa`.
Main conferida: `4336181fc9156d386cc46158ced708b6efda7be5`.
As PRs #83 → #89 → #90 → #91 → #92 continuam abertas em Draft.
A #93 (`bbf305dc36217215677c9d3401e7dcc74a585d25`) é irmã da #92: ambas
partem de #91 (`83129ce`). Seu ingresso Instagram fictício foi lido, mas **não
incorporado**. Nenhum merge, rebase ou cherry-pick é necessário nesta manutenção.

## Reutilização, sem um segundo motor

O núcleo permanece em `python-service/message_enrichment.py`, com contratos em
[MESSAGE-ENRICHMENT-CONTRACT.md](MESSAGE-ENRICHMENT-CONTRACT.md) e protocolo de
laboratório em [MESSAGE-ENRICHMENT-ADAPTER.md](MESSAGE-ENRICHMENT-ADAPTER.md).
A Caixa usa `message-enrichment-store.js`/`message-enrichment.js`; o Assistente
continua preparando textos locais e inserindo apenas no composer revisável.
Não foi criado outro cadastro, fila de envio, máquina de estados ou tabela.

| Informação              | Fronteira atual                                                                                        |
| ----------------------- | ------------------------------------------------------------------------------------------------------ |
| Negócio, usuário, papel | Sessão autenticada no servidor; nunca um workspace declarado no JSON                                   |
| Canal                   | `whatsapp` ou `instagram`; somente no laboratório sintético                                            |
| Conta e remetente       | `account_ref`/`contact_ref`, referências `synthetic:` declaradas; não comprovam posse de conta externa |
| Identidade da conversa  | Workspace + canal + conta + contato; `id` interno estável, sem unir pessoas por nome                   |
| Identidade da mensagem  | `id` interno e `external_message_id`; deduplicação por workspace/canal/conta                           |
| Direção e conteúdo      | Entrada de texto somente; não há contrato de saída, mídia ou recibos de entrega                        |
| Hora                    | `occurred_at` opcional com fuso explícito; detalhes abaixo                                             |
| Cliente CRM             | Nenhum vínculo inferido por nome; exige vínculo comprovado e contrato próprio                          |
| Revisão/rastreamento    | `operation_id`, revisões da conversa/mensagem/job, ID do job e eventos internos                        |

Não existe identificador dedicado de thread/grupo externo neste modelo sintético.
Não se deve tratar `contact_ref` como contrato homologado para threads de provedores.

## Horário e ordem, sem alterar o esquema

`Incoming` agora aceita `occurred_at` opcional em ISO 8601 restrito, por exemplo
`2026-10-21T10:00:00-03:00` ou `2026-10-21T13:00:00Z`. Segundos e fuso são
obrigatórios; fração de até seis casas é suportada. Offset inválido, data impossível,
horário sem fuso e conversão que ultrapasse o intervalo de datetime retornam422,
sem gravação. Instantes equivalentes normalizam em UTC antes da deduplicação.

A coluna existente da migration014 é reutilizada. Sem o campo, continua valendo o
horário de registro do servidor, preservando chamadas anteriores. **A API não
registra uma marca separada da origem desse horário:** não use mensagens antigas
como prova do horário original no provedor, nem como base de SLA homologado.

A leitura retorna as 100 mensagens mais recentes por `(occurred_at,id)`, em ordem
crescente para apresentação. IDs e revisões continuam estáveis e incrementam por
chegada; hora de origem não prova causalidade. Empates usam ID, sem inventar ordem
do provedor. O horário do corpo não autoriza uma operação nem controla prazo de
sessão, assinatura ou expiração de job; estes usam verificações do servidor.

Payloads sem horário mantêm seus fingerprints existentes: o campo ausente/nulo é
omitido da representação canônica. Mesmo UUID/ID externo com conteúdo ou horário
normalizado diferente conflita409; reenvio não reescreve a mensagem. Não acrescente
horário a um evento legado já aceito tentando convertê-lo em atualização.

## Preparar, revisar e cancelar

O mesmo endpoint de análise localiza a mensagem no workspace autenticado, consulta
somente documentos autorizados desse negócio e produz um resultado determinístico
identificado como heurístico. Não há IA externa nem busca de URLs privadas.

Estados legados preservados: `pending` → `pending_review` → `approved` ou `rejected`;
expiração/invalidação/substituição continuam existentes. `rejected` é o descarte da
sugestão; não foi introduzido outro estado `cancelled`. Aprovação persiste apenas o
texto revisado e sempre retorna `transport:none`. Não existem `sent`/`delivered`.
CAS impede revisão concorrente ou repetida de uma versão já decidida. Uma nova
análise não ressuscita resultados descartados nem sobrescreve decisões humanas.

No Assistente, reinserir uma sugestão exata que já esteja no composer não a duplica,
mesmo com texto humano antes/depois. O texto existente permanece integralmente.
Se a sugestão foi editada e já não aparece integralmente, a ação pode acrescentar
uma nova alternativa; não há comparação semântica nem deduplicação de mensagens
externas nesse comportamento local. Inserção não executa envio.

## Contrato exigido de um adaptador futuro

1. Validar autenticação/assinatura real da origem, corpo limitado, validade e
   revogação. A assinatura HMAC de fixture **não** é assinatura Meta/WAHA homologada.
2. Resolver a conta e o negócio no servidor por vínculo autorizado, sem workspace
   fornecido pelo navegador/provedor como prova de acesso.
3. Normalizar identidade estável de conta/conversa/mensagem/remetente, direção,
   tipo e horário; recusar formato não suportado, ambiguidade e conta revogada.
4. Deduplicar de modo persistente; reutilizar a operação em respostas perdidas,
   recusar mudança sob o mesmo ID e rastrear operação/job sem registrar segredos.
5. Preservar horário de origem e de recebimento como conceitos distintos em um
   contrato futuro versionado; não usar o timestamp da assinatura como hora da mensagem.
6. Preparar e revisar pelo núcleo atual. Um adaptador de saída exigirá autorização
   específica, conta habilitada, revisão/revalidação, idempotência, transporte,
   confirmação do provedor e reconciliação. Até lá, **não há método de envio**.

A #93 já resolve o dono de contas Instagram fictícias e reutiliza `Incoming` sem
horário opcional; sua compatibilidade de payload é preservada, mas a combinação
não foi executada nem homologada nesta branch. Ela deve ser revisada separadamente.
Não foi criado webhook público ou habilitado ingresso externo.

## Evidências e riscos

- Teste vermelho: repetir inserção duplicava texto; repetição com fecho humano
  também reproduzida. Verde: texto preservado, homônimas WhatsApp/Instagram
  separadas, nenhuma mensagem adicionada, cinco larguras e dois temas.
- Testes de contrato: horário opcional, UTC equivalente, offset/datas inválidas,
  extremos sem500, ordem de origem, empate determinístico, reenvio e hashes legados.
- PostgreSQL descartável: dois negócios e dois canais com mesmo nome/IDs externos;
  identidades separadas, revisão/descarte, texto humano preservado, acesso cruzado404,
  workspace arbitrário422 e `transport:none`.
- A Issue #73 permanece aberta. Suítes verdes não determinam a causa do timeout
  histórico do Financeiro; não foi declarada resolvida.

Resultados finais de testes e CI constam na PR desta branch. Provedores reais,
mídia, grupos, leitor de tela físico, desempenho em celular físico e homologação
operacional continuam fora da evidência desta rodada. Nenhum dado real, credencial,
workflow ativo, banco real, AWS, envio ou publicação foi usado/modificado.
