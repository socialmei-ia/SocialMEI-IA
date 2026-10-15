# Catálogo de workflows — 15/10/2026

## Evidência e limites

Inventário fornecido pelo responsável após consulta PostgreSQL em transação READ ONLY na AWS. n8n 2.40.5, 33 workflows, oito ativos e cinco arquivados. A coleta contém somente metadados e tipos de nós do documento salvo; não inclui parâmetros, credenciais, payloads ou execuções. Não comprova equivalência entre rascunho e versão publicada, homologação ou entrega de mensagens.

O inventário anterior de 24 workflows permanece histórico em [LIVE-ENVIRONMENT-INVENTORY.md](LIVE-ENVIRONMENT-INVENTORY.md). A coleta inicial foi somente leitura; a aplicação posterior de tags está registrada abaixo, com evidência fornecida pelo responsável.

## Recentes e seleção para o Git

| Workflow / ID                                                             | Decisão                                                                                                                     | Evidência restante                                                                         |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Python API / `jy3rLjOc0x8wKAW6`                                           | Atualizar `examples/process-text.json` com o template recente já fornecido e testado pelo responsável; não duplicar arquivo | Equivalência integral com documento salvo NÃO CONFIRMADA                                   |
| Python Native / `VEe2EgdvfW07Nuvt`                                        | Adicionar `examples/python-native-check.json`; template fornecido e execução confirmada pelo responsável                    | Equivalência integral com documento salvo NÃO CONFIRMADA                                   |
| Gerador de Relatórios / `7Q80LJFtLrhr8Sml`                                | Candidato a export experimental separado do Atendimento ativo                                                               | Revisar grafo, contratos, acesso a Sheets e autenticação                                   |
| Sugestões de respostas Rápidas Orçamentos / `lGY3GniUcMxfI2W9`            | Candidato a export experimental                                                                                             | Revisar webhook, credenciais, Sheets, tenant e dados de exemplo                            |
| Publicar post no Instagram / `A0EcNxcRvfWnMwKI`                           | Candidato a export experimental                                                                                             | Revisar permissões e parâmetros; publicar post tem efeito externo, não executar como teste |
| whatsapp / `kUVSGWkh2m7wpj2x` e whatsapp API oficial / `UtqOv1i2iXMOcCBz` | Preservar separados até comparar; ambos declaram WAHA                                                                       | Nome “oficial” não comprova Meta Cloud API; não promover nem parear                        |
| Agendamento de lembretes / `fgtdxZBfieU23JqZ`                             | Planejado, sem nós; não exportar template vazio                                                                             | Objetivo e contrato pendentes                                                              |
| Whatzapp oficial / `09EFgeadwFN5Y3kR`, My workflow 2 / `AVopngwBE4aT3I4E` | Já arquivados; preservar na instância                                                                                       | Não excluir por nome ou ausência de nós                                                    |

Os três subworkflows de pedidos e o Atendimento ativo devem ser revisados em conjunto. Consultar/registrar/confirmar pedido dependem de Sheets; nenhuma mudança de ID, ativação, conexão ou webhook está incluída. O documento antes chamado Gerador de Relatórios (`DDrphANXE8QdxoWy`) agora se chama Atendimento: sua identidade é o ID, não o nome.

## Organização proposta no painel

### Dependências confirmadas na coleta seguinte

Consulta READ ONLY fornecida pelo responsável confirmou que `DDrphANXE8QdxoWy` (Atendimento) referencia por `toolWorkflow` os IDs `AUpqr0ko77jQJ6DW` (consultar produtos), `LV2rsbXIb3eE0Pb3` (registrar pedido) e `QAcfeKiXA6ZQQ4Mz` (confirmar pedido). Preservar esse conjunto e seus IDs; a consulta descreve o documento salvo, não comprova a versão publicada. Nenhuma outra referência estática foi retornada para os tipos executeWorkflow/toolWorkflow consultados; chamadas dinâmicas ou por HTTP não estão excluídas.

Foram encontrados 20 vínculos workflow/tipo de credencial. Atendimento usa Groq; os três subworkflows de pedidos usam Google; os dois grafos WhatsApp recentes usam WAHA (o chamado “API oficial” também referencia Gemini). Isso descreve configuração declarada: validade das credenciais e funcionamento ponta a ponta NÃO CONFIRMADOS. Nenhum valor, nome ou ID de credencial foi coletado.

Tags aplicadas aos oito workflows recentes: `socialmei/teste`, `socialmei/experimental` e `socialmei/planejado`. `socialmei/operacao` e `socialmei/legado` continuam propostas para uma etapa posterior. Preservar tags de terceiros. Não mover propriedade/projeto de workflows, não republicar versões e não editar banco diretamente para organizar.

### Aplicação confirmada pelo responsável

Backup privado informado: `/home/ubuntu/socialmei-backups/n8n-organizacao-34797ecc29a6`, com dump de 3.047.473 bytes e volume de 1.303.272 bytes. Índice do dump conferido; volume copiado em execução e restauração completa não ensaiada. Configuração do runner também preservada; seu override efetivo está em `/home/ubuntu/.config/socialmei/n8n-python/compose.python-runners.json`, fora da pasta legada do projeto. Backup, chave administrativa e exports privados não são arquivos para o Git.

A API administrativa foi acessada pelo responsável via terminal AWS. O plano privado preservou oito documentos salvos antes da operação. A saída da aplicação confirmou os dois testes Python com `socialmei/teste`, Relatórios/Orçamentos/publicação Instagram e os dois WhatsApp com `socialmei/experimental`, e Lembretes com `socialmei/planejado`.

A conferência comparou nomes, IDs, grafos, configurações, versões e estados antes/depois e preservou tags anteriores. Os oito continuaram inativos. Nenhum workflow foi executado, ativado ou desativado; nenhum serviço foi reiniciado. Os nomes sugeridos não foram aplicados: o contrato para regravar o workflow não foi confirmado na distribuição instalada. A organização usou somente o endpoint específico de tags. Isso não comprova homologação dos fluxos nem publica seus grafos no Git.

### Organização nas pastas existentes

Em seguida, o responsável confirmou a organização dos 33 workflows dentro da pasta raiz `SocialMEI.IA`: oito em `01 · Produção`, cinco em `02 · Testes` e vinte em `03 · Revisar`. Vinte e dois workflows antes soltos foram movidos; nenhum permaneceu fora das três pastas. O recibo privado informado está em `n8n-organizacao-34797ecc29a6/folder-organization-20261015-160646` no diretório de backups da AWS.

A conferência antes/depois preservou IDs, nomes, estados ativo/arquivado e datas de atualização. Produção ficou com sete ativos, Testes com um ativo e Revisar com cinco arquivados e nenhum ativo. Nenhum workflow foi executado, ativado, desativado ou excluído; nenhum serviço foi reiniciado. A movimentação de pasta organiza o painel, mas não promove nem homologa os fluxos. Em especial, o Hello World ainda está ativo em Testes e os dois fluxos Caixa Unificada continuam ativos em Produção; revisar essas ativações exige uma decisão separada.

### Padronização de nomes e remoção de vazios

Após a análise de uso, o responsável confirmou a execução da limpeza preparada. Vinte e nove workflows receberam nomes únicos com os prefixos `[PROD]`, `[OPS]`, `[TEST]`, `[DEV]`, `[REVIEW]`, `[PLAN]`, `[LEGACY]` ou `[ARCHIVE]`; os dois testes Python recentes já padronizados mantiveram os nomes. IDs, grafos, referências de credenciais, estados, pastas e datas de atualização foram preservados pelo roteiro de conferência.

Dois workflows arquivados, sem nós, execuções ou referências foram excluídos: `KevuuJgU5iXC9SfV` (`Validar CPF e CNPJ com Python`) e `09EFgeadwFN5Y3kR` (`Whatzapp oficial`). Cópias privadas foram preservadas antes da exclusão. O rascunho vazio de lembretes foi mantido como `[PLAN] Lembretes — rascunho vazio`, pois representa intenção ainda não decidida. Permanecem 31 workflows: oito em Produção, cinco em Testes e dezoito em Revisar; oito ativos e três arquivados. Nenhum workflow foi executado, ativado ou desativado e nenhum serviço foi reiniciado.

Os dois testes Python já têm nomes descritivos. Novos nomes candidatos: `[DEV] Relatórios — Google Sheets`, `[DEV] Orçamentos — sugestões`, `[DEV] Instagram — publicar post`, `[PLAN] Lembretes`. Antes de aplicar, preservar documento/versão publicada/estado e conferir dependências por ID; usar interface ou API administrativa suportada, com acesso privado. Fluxos ativos e versões de orçamento semelhantes aguardam comparação, sem excluir cópias.

## Inventário histórico anterior à renomeação e exclusão

| ID                 | Nome salvo                                 | Ativo | Arquivado | Atualizado em UTC             |
| ------------------ | ------------------------------------------ | ----- | --------- | ----------------------------- |
| `kUVSGWkh2m7wpj2x` | whatsapp                                   | não   | não       | 2026-10-15T15:00:34.15+00:00  |
| `VEe2EgdvfW07Nuvt` | [TEST] Python Native — conferir executor   | não   | não       | 2026-10-15T13:49:16.605+00:00 |
| `jy3rLjOc0x8wKAW6` | [TEST] Python API — conferência            | não   | não       | 2026-10-15T13:46:28.337+00:00 |
| `09EFgeadwFN5Y3kR` | Whatzapp oficial                           | não   | sim       | 2026-10-15T00:31:58.575+00:00 |
| `A0EcNxcRvfWnMwKI` | Publicar post no Instagram                 | não   | não       | 2026-10-14T21:36:32.82+00:00  |
| `7Q80LJFtLrhr8Sml` | Gerador de Relatórios                      | não   | não       | 2026-10-14T21:11:23.697+00:00 |
| `lGY3GniUcMxfI2W9` | Sugestões de respostas Rápidas Orçamentos  | não   | não       | 2026-10-14T20:58:32.546+00:00 |
| `AVopngwBE4aT3I4E` | My workflow 2                              | não   | sim       | 2026-10-14T20:54:03.623+00:00 |
| `SAlmjUPuAjyMdLAn` | Integração Whatsapp                        | não   | não       | 2026-10-14T20:50:54.829+00:00 |
| `fgtdxZBfieU23JqZ` | Agendamento de lembretes                   | não   | não       | 2026-10-14T20:50:18.181+00:00 |
| `UtqOv1i2iXMOcCBz` | whatsapp API oficial                       | não   | não       | 2026-10-14T20:12:42.009+00:00 |
| `DDrphANXE8QdxoWy` | 02 · Atendimento                           | sim   | não       | 2026-10-14T01:52:02.305+00:00 |
| `NDNF5doo9pLtj6sb` | 03 · Integração Instagram                  | sim   | não       | 2026-10-13T23:51:14.8+00:00   |
| `QAcfeKiXA6ZQQ4Mz` | confirmar_pedido                           | sim   | não       | 2026-10-13T01:59:36.993+00:00 |
| `LV2rsbXIb3eE0Pb3` | registrar_pedido                           | sim   | não       | 2026-10-13T01:23:01.255+00:00 |
| `AUpqr0ko77jQJ6DW` | consultar_produtos                         | sim   | não       | 2026-10-13T00:23:15.202+00:00 |
| `8hSF0mABWNYJqWQB` | Resposta Orçamento copy 2                  | não   | não       | 2026-10-12T17:02:31.914+00:00 |
| `M9BN1KgXN0cqxmXi` | Validação de CPF e CNPJ com Python         | não   | não       | 2026-10-12T16:39:03.674+00:00 |
| `EGXHkPjqt0Wiaxl4` | SocialMEI equipe — conferir conexão        | não   | não       | 2026-10-12T15:53:29.978+00:00 |
| `es8Q46avtvZzK1EX` | SocialMEI - Pedidos e relatório de estoque | não   | não       | 2026-10-12T14:12:59.925+00:00 |
| `RnXngR3SvhSxaC32` | Resposta Orçamento                         | não   | não       | 2026-10-11T22:57:03.352+00:00 |
| `UJFfcnE7PC6oOBd7` | Resposta Orçamento copy                    | não   | sim       | 2026-10-11T22:55:55.653+00:00 |
| `e324ZPdcKLcHQAPF` | Resposta Orçamento                         | não   | não       | 2026-10-11T21:52:01.082+00:00 |
| `K8Z9SVLEsR0yKVPc` | Analise de Semtimentos                     | não   | não       | 2026-10-09T00:25:28.29+00:00  |
| `KevuuJgU5iXC9SfV` | Validar CPF e CNPJ com Python              | não   | sim       | 2026-10-08T21:30:32.149+00:00 |
| `uPbpfBbSB3q1efO7` | My workflow                                | não   | não       | 2026-10-08T20:51:09.415+00:00 |
| `BtvlHv4mt90tn70z` | 01 · Caixa Unificada API — PostgreSQL      | sim   | não       | 2026-10-07T00:03:01.934+00:00 |
| `QDlfkKxesQEWfyLp` | Teste · Python                             | não   | não       | 2026-10-06T21:31:13.941+00:00 |
| `vF3jcCJrElfoQTH6` | Revisar · Workflow Antigo                  | não   | não       | 2026-10-06T21:16:50.706+00:00 |
| `6BczTaFNOl24jr4X` | Teste · Hello World                        | sim   | não       | 2026-10-06T21:15:45.642+00:00 |
| `Sasq0PBhdzlHV7Ds` | Teste · Caixa Unificada                    | não   | não       | 2026-10-06T21:14:51.766+00:00 |
| `WWzhvmdPh9LrpuYy` | 01 · Caixa Unificada API                   | sim   | não       | 2026-10-06T21:14:14.641+00:00 |
| `JVPPxXa0cQbE62C2` | error                                      | não   | sim       | 2026-09-28T00:08:57.053+00:00 |

## Coleta privada posterior à organização

O responsável confirmou oito documentos salvos na coleta `github-coleta-lml2t3jj`, dentro do backup privado de organização na AWS. Sete estavam ativos e a conferência operacional estava inativa. A coleta não executou workflows nem alterou serviços. A equivalência com as versões publicadas continua NÃO CONFIRMADA.

| Grupo                | Nós | Evidência do resumo técnico                                            |
| -------------------- | --- | ---------------------------------------------------------------------- |
| Caixa local — legado | 6   | Dois Code, dois webhooks e duas respostas                              |
| Caixa PostgreSQL     | 8   | Um Code, dois PostgreSQL, dois webhooks, duas respostas e uma nota     |
| Atendimento          | 7   | Chat, agente, Groq, memória e três chamadas de subworkflow             |
| Consultar produtos   | 2   | Trigger de subworkflow e Google Sheets                                 |
| Registrar pedido     | 2   | Trigger de subworkflow e Google Sheets                                 |
| Confirmar pedido     | 9   | Trigger, quatro Google Sheets, uma condição e três Set                 |
| Instagram            | 8   | Webhook, agente, Gemini, memória, Sheets Tool, HTTP, Switch e resposta |
| Conferir conexão     | 2   | Trigger manual e HTTP; inativo                                         |

O Atendimento referencia consultar produtos, registrar pedido e confirmar pedido pelos IDs documentados anteriormente. Templates importados recebem novos IDs: essas três chamadas precisam ser configuradas privadamente no ambiente de destino. A presença de Google Sheets nos três subworkflows não comprova operação homologada nem retira a decisão de adiar essa integração.

O PR inclui um exportador de **templates estruturais**, testado com documentos fictícios que contêm segredos em código, parâmetros, nomes, configurações e dados fixados. Esses campos não são copiados. O export completo permanece privado. Nenhum template estrutural deve substituir automaticamente os exports existentes, ser ativado ou ser chamado como teste.

O responsável confirmou a geração na AWS e o envio dos oito templates em `n8n-workflows/structure/`, no commit `3105444bace9cb8d8c6ccc634d637216366b672d`. Foram preservadas as quantidades de nós e as conexões dos documentos salvos, com nomes reconstruídos. Todos os workflows ficaram inativos e seus nós desabilitados. Três testes Python passaram na AWS; a revisão local dos arquivos publicados confirmou a projeção permitida pelo exportador e os 72 testes JavaScript passaram. Isso não valida parâmetros, credenciais ou versões publicadas.

## Revisão dos parâmetros ainda pendente

Confirmar dependências entre workflows e referências a credenciais por tipo, sem expor IDs/nomes de credenciais, parâmetros ou valores. Depois preservar export privado dos selecionados e da versão publicada, revisar dados sensíveis e transformar uma cópia em export importável inativo para o Git. Não solicitar JSON bruto na conversa: parâmetros, URLs, código e pinData podem conter segredos mesmo sem um objeto credentials.

Ativo não significa pronto para clientes reais. A12/A13 continuam condições antes de atendimento: identidade, autorização, isolamento e idempotência. Importar um export de teste não substitui uma versão viva existente nem autoriza ativá-la.
