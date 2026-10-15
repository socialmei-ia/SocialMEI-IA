# Workflows n8n

| Grupo           | Arquivos                                                   | Uso                                                                                                                   |
| --------------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `equipe/`       | `01-conferir-conexao.json`                                 | [OPS] Leitura técnica do CRM team; exige credencial Bearer configurada privadamente. Não escreve nem envia mensagens. |
| `producao/`     | `01-caixa-unificada-api-postgresql.json`                   | LEGADO de entrada/leitura de histórico, export inativo e sem credenciais. O nome da pasta não comprova deploy.        |
| `examples/`     | `hello-world.json`, `process-text.json`                    | Exercícios HTTP e chamada da API Python interna.                                                                      |
| `examples/`     | `python-native-check.json`                                 | Teste manual do executor Python nativo, sem HTTP, planilha ou CRM. Requer runner compatível.                          |
| `experimental/` | `instagram-agent.json`, `instagram-webhook-challenge.json` | Experimentos Meta/Gemini. Selecionar credenciais Gemini e HTTP Header Auth após importar.                             |
| `experimental/` | `scheduled-request-draft.json`                             | Possível legado — revisar manualmente. Requisição agendada sem destino configurado; preservada sem ativação.          |

Os antigos arquivos `error.json`, `my-workflow.json`, `integracao-n8n-insta.json` e `teste-python.json` foram movidos para nomes descritivos. Seus grafos úteis foram preservados; metadados da instância, dados fixados e autenticação literal foram retirados.

## Workflows recentes — 15/10/2026

O [catálogo atual](../docs/N8N-WORKFLOW-CATALOG.md) registra os 33 workflows observados na AWS, candidatos a export e a aplicação confirmada de tags aos oito recentes, preservando conteúdo e estados. Renomeação continua pendente. O histórico de sete exports nas seções abaixo descreve a rodada anterior; agora são oito arquivos JSON. A organização no Git e a operação no painel são etapas distintas.

`examples/process-text.json` foi atualizado com o template recente `[TEST] Python API — conferência`, preservando o POST `/processar`, com timeout de 15 segundos e nomes de nós descritivos. Não foi criado outro exemplo HTTP duplicado. `examples/python-native-check.json` contém `[TEST] Python Native — conferir executor`: retorna `status: ok` e `resultado: 4`, usando `pythonNative`. Ambos têm trigger manual e export inativo; não enviam mensagens.

O responsável confirmou os dois testes na AWS antes desta coleta. Os arquivos são os templates fornecidos naquela etapa; equivalência integral com o documento salvo na instância não foi comprovada. Python HTTP e Python nativo são caminhos diferentes: o primeiro precisa alcançar `python-api:8000`; o segundo depende do task runner, não daquela API. `/mensagem` e `/estoque` não fazem parte desses testes.

## Entrada e leitura PostgreSQL

Credencial técnica: `socialmei_app`, host `postgres`, porta 5432, banco configurado no ambiente. Selecione a credencial nos dois nós PostgreSQL. O schema deve existir antes da execução.

POST aceita campos como:

```json
{
  "cliente": "Cliente de teste",
  "cliente_id": "customer-test-1",
  "conversa_id": "conversation-test-1",
  "canal": "whatsapp",
  "mensagem": "Olá",
  "horario": "2026-10-10T12:00:00Z"
}
```

O caminho POST versionado é `6404b870-1c8c-4633-b487-6c3971775934`; GET usa `5f82c1c2-99de-43f4-9578-42f3aa901fcf`, também configurado no frontend. Use as URLs de teste/produção fornecidas pelo seu n8n. Não envie essa amostra à VPS compartilhada durante testes locais.

GET retorna `status`, `total` e `mensagens` com `id`, `cliente`, `canal`, `mensagem`, `horario`. Retorna apenas as últimas 50 mensagens de entrada. `since` não é implementado. Reenvios não são deduplicados por identificador de mensagem; autenticação, CORS restrito e IDs estáveis são pendências P0.

## Instagram

Os grafos experimentais não são uma integração completa. O fluxo de challenge tem componentes de agente desconectados; o agente Instagram tem um nó de resposta separado do caminho de mensagens. Modelos, permissões Meta, versões de API e payload precisam ser validados antes de uso. Não ative exports automaticamente.

Os cabeçalhos Authorization literais antigos foram removidos. Configure credencial **HTTP Header Auth** no n8n; segredos permanecem no gerenciador de credenciais, não nos JSONs. Se os valores antigos eram válidos, o responsável deve revogá-los: limpar o arquivo atual não remove histórico Git.

## Alterar e testar

Importe em ambiente isolado, selecione credenciais, confira nós e queries, teste com dados fictícios e só depois publique. Exporte novamente com `active: false`, sem dados fixados e sem referências de credenciais da instância. Rode `npm test` para validar JSON e normalização; isso não executa SQL nem serviços remotos.

## Estabilização — 13/10/2026

Os sete nomes dos exports foram classificados como `[OPS]`, `[TEST]`, `[DEV]`, `[LEGACY]` ou `[ARCHIVE]`. Todos continuam inativos; grafos, nodes, caminhos de webhook e parâmetros foram preservados. O rascunho agendado sem URL e os ramos desconectados do Instagram permanecem conhecidos/incompletos: sua intenção não autoriza inventar lógica.

O inventário histórico da VPS registra 24 workflows, oito ativos e três arquivados, com detalhes em [LIVE-ENVIRONMENT-INVENTORY.md](../docs/LIVE-ENVIRONMENT-INVENTORY.md). Essa coleta é anterior; nomes, versão publicada, última execução e autorização não foram reconfirmados nesta rodada. Nenhum workflow vivo foi renomeado, publicado ou chamado. A organização no Git não organiza automaticamente a instância.

## Contratos e promoção de workflows

| Export                 | Trigger / entrada                                        | Saída / dependência                                            | Estado                                      |
| ---------------------- | -------------------------------------------------------- | -------------------------------------------------------------- | ------------------------------------------- |
| Conferir conexão team  | Manual; URL e Bearer de leitura cadastrados privadamente | Resumo de leitura da API team, sem escrita                     | OPS; export inativo                         |
| Atendimento PostgreSQL | Webhook POST normalizado ou GET de histórico             | Confirmação de gravação ou `mensagens`; PostgreSQL legado      | LEGACY; bloqueado para uso real até A12/A13 |
| Hello World            | Webhook de exemplo                                       | Resposta HTTP de exercício                                     | TEST; isolado                               |
| Processar texto        | Manual; texto de exemplo                                 | `/processar` → original/maiúsculo/contagem                     | TEST; API auxiliar, não CRM                 |
| Agente Instagram       | Webhook experimental / payload Meta                      | Agente/HTTP com ramos incompletos; Meta e Gemini               | DEV; não homologado                         |
| Challenge Instagram    | Webhook de verificação                                   | Resposta do challenge; agente separado sem integração completa | DEV; não homologado                         |
| Rotina agendada        | Agenda; destino ainda ausente                            | Requisição sem URL definida                                    | ARCHIVE; intenção pendente                  |

Para uma nova automação, definir objetivo, trigger, input/output, timeout/retry, identidade/negócio, chave idempotente e credenciais por finalidade antes de montar o canvas. Usar nomes de nós que descrevam ações; manter paths e referências de conexões ao renomear nós. Uma nota curta pode explicar uma decisão, sem copiar o guia inteiro para o workflow.

Fluxo de promoção: desenvolver em instância/projeto isolado → testar dados fictícios e falhas/reenvio → exportar sem credenciais/pinData e com `active: false` → revisar diff e contratos no PR → registrar versão do export e do n8n → importar/configurar privadamente no alvo aprovado → homologar antes de ativar. Se não houver staging instalado, não chamar o piloto de staging por conveniência.

Antes de alterar um workflow vivo, preservar export da versão publicada, estado ativo/inativo, configuração relevante e backup conjunto de banco/volume/chave. Rollback restaura a versão do workflow e suas referências de credenciais aprovadas; não reverte mensagens enviadas ou escritas de negócio automaticamente. Nunca usar restore de banco de produção como teste de rollback.

`npm test` valida exports/normalização estáticos; não comprova consultas no banco vivo, funcionamento de credenciais, autenticação do webhook ou entrega de mensagem. [Mapa dos ambientes e limites](../docs/ENVIRONMENTS.md).

A12/A13 continuam P0 antes de atendimento real: autorização, tenant/canal, IDs externos e deduplicação. Não ligar o legado ao modelo multi-MEI pela troca de nomes. Backup da instância deve preservar seu banco, volume e chave de criptografia originais antes de qualquer alteração viva. Google Sheets permanece pausado.
