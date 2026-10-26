# Divulgação: preparação compartilhada e agendamento de teste

Esta extensão utiliza o editor oficial. Não publica, envia arquivos, chama n8n/Meta ou usa IA paga. Legendas são alternativas de um **modelo de texto demonstrativo**, usando somente tema/serviço/nome fornecidos. Imagens não são geradas: o contrato retorna indisponibilidade e o editor mantém upload/prévia local.

## Ativação e identidade

Padrão desabilitado. Em testes descartáveis, ativar backend `SOCIALMEI_CONTENT_PREPARATION_MODE=simulation`, autenticação/CRM existentes e migration015; frontend `contentPreparation: {mode: "simulation"}`. Essa flag é independente de `instagramSimulation`. Nenhuma configuração de infraestrutura foi ativada nesta entrega.

O backend resolve o workspace pela sessão. Escritas exigem owner/admin/member, Origin e CSRF; criar conta fictícia exige owner/admin. Leitura aceita viewer. JSON estrito e parâmetros de consulta recusados; respostas sem cache e erros de banco sanitizados. Contadores persistidos limitam60 operações/min por usuário/workspace e20 novas preparações/min por negócio. O browser confere workspace da resposta, identidade, versão da leitura e operação em andamento; uma falha remota não salva localmente como fallback.

## API

Prefixo `/api/v1/content/preparation`:

| Método/rota              | Resultado                                                                                                         |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| GET `/status`            | Modo, ausência de transporte, adapters e escopo                                                                   |
| GET/POST `/accounts`     | Contas fictícias por workspace; POST `{label}`                                                                    |
| POST `/captions`         | `{topic,business?,offering?,objective?,tone?}` →3 alternativas/hashtags por modelo local, `generated_by_ai:false` |
| POST `/images`           | `{brief}` →503 explícito; sem arquivo ou chamada externa                                                          |
| GET/POST `/jobs`         | Histórico limitado a100 / criação idempotente                                                                     |
| GET `/jobs/{id}`         | Conteúdo, revisão e últimas30 transições                                                                          |
| PUT `/jobs/{id}`         | Substituição explícita com `revision` atual e mesma `idempotency_key`; conflito409                                |
| POST `/jobs/{id}/cancel` | `{revision}`; cancelamento com CAS                                                                                |
| POST `/run-due`          | `{}`; processa até10 testes vencidos do workspace autenticado                                                     |

Corpo de criação: `idempotency_key` UUID, `title`, `format` feed/story/reel, `caption`, lista `media` de `{name,mime,size}`, `account_id` opcional, `status` draft/pending_review/scheduled, `reviewed` booleano e `scheduled_for` com offset + `timezone` IANA. Agendar exige revisão, conta fictícia vinculada, mídia compatível e data futura (30s a365dias). Formatos reutilizam o contrato de simulação existente: Feed até10 imagens, Story/Reel uma mídia; o editor seleciona somente uma.

Repetir criação com mesma chave/conteúdo devolve o registro atual, inclusive após edição CAS; conteúdo diferente retorna409. A validação de horário futuro ocorre depois dessa verificação para permitir recuperar uma resposta perdida após o horário. Histórico/texto são compartilhados; mídia **somente metadados**, nunca bytes ou URL para publicação. Rascunhos locais existentes continuam separados e preservados.

## Worker recuperável, exclusivamente simulado

Estados: draft → pending_review → scheduled → processing → simulated; cancelled, failed e uncertain não se confundem com publicação. `published` é semprefalse e o banco não aceita estado published.

A execução manual da interface e o worker de uma passagem usam a mesma rotina. Exemplo **somente em banco descartável já configurado**:

```bash
python python-service/content_preparation.py --workspace ID_DO_TESTE --once
```

Não há daemon, cron ou agendamento operacional instalado. Jobs persistem após reinício e aguardam uma nova passagem. Claims usam `FOR UPDATE SKIP LOCKED`, lease de60s e token de execução; conclusão antiga não sobrescreve uma recuperação posterior. Neste adapter sem efeitos externos, lease expirada pode ser recuperada. Falha transitória tenta no máximo3 vezes, com30s/60s de espera persistida; resultado desconhecido torna-se uncertain e não é repetido automaticamente. Processamento/cancelamento usam revisão; um job em processamento não pode ser editado/cancelado.

Essa política **não autoriza** ligar transporte real: resultado incerto de uma publicação externa exigirá reconciliação com o provedor, sem repetir publicações por expiração de lease. Geração de mídia, armazenamento privado, OAuth Meta, callbacks assinados, homologação de formatos/API e transporte n8n continuam contratos externos pendentes.
