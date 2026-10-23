# Oportunidades V8 — inventário antes da substituição

Golden master imutável: `frontend/reference/Oportunidades-V8-original.html`.
A composição interna será extraída, sem o header duplicado; a topbar/sidebar
oficial continuará responsável por sessão, usuário e navegação.

| Seção / estado / interação original                                    | Integração e fonte                                                                                  | Segurança / limite                                                                               |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Hero, palavras, ilustração/parallax, cores, opções, tema               | DOM/CSS original sob raiz exclusiva; tema oficial e menu de comandos contextual                     | Não aplicar tokens ao restante do app; respeitar movimento reduzido                              |
| Cliente/interesse/busca de cliente/título/valor/retorno; erros e criar | Clientes do CRM + `createStore.create`; `analysis` mapeado para `unknown`; mesma confirmação de API | Sem seed; viewer/local sem backend não criam registro; valor/retorno somente após sucesso remoto |
| Resumo, contadores e sete filtros                                      | Snapshot autenticado; encerradas fora dos contadores de interesse                                   | Até 100 recentes; valor estimado local não é faturamento                                         |
| Retomar hoje: vencidos ou 3 dias sem atualização                       | Datas explícitas do planejamento; atualização real ou contato registrado localmente                 | Regra operacional do original; não inferir venda, canal ou envio                                 |
| Registrar contato, +1/+3/+7 dias, sem data, copiar                     | Sidecar existente por usuário/negócio/oportunidade, clipboard com falha explícita                   | Nota, valor, contato e retorno não sincronizam; nenhuma mensagem é enviada                       |
| Lista, avatar, interesse, valor, retorno e expansão                    | Mesmo DOM de linhas/expansão do original; IDs nativos compatíveis                                   | Escape de texto dinâmico; sem substituir edição digitada durante requests                        |
| Busca `/`, ordenação recente/retorno/valor, empty states               | Snapshot + metadata local, filtro explícito                                                         | Não buscar outro workspace nem fingir resultados completos                                       |
| Interesse nos segmentos, teclado e termômetro                          | `store.update` com revisão/operation_id/CSRF; fichas circulares e FLIP originais                    | Sem mudança otimista; erro preserva dado confirmado; mesmas permissões                           |
| Termômetro: 4 zonas, valor/tamanho, retorno, arrastar/clicar/setas     | Pointer events para mouse/toque; setas mudam interesse; Enter abre linha                            | Sem Kanban alternativo; cancelar pointer não grava                                               |
| Semana: atrasadas, hoje, próximos 6 dias, depois/sem data              | Datas do sidecar; drag/drop + selecionar ficha e selecionar dia por toque/teclado                   | Data local, sem endpoint novo; atrasadas não é destino válido                                    |
| Anotação/valor, salvar e histórico local                               | Sidecar versionado existente `socialmei-op8-local-v1:<scope>`                                       | Falha/quota não produz sucesso; eventos locais separados da auditoria remota                     |
| Encerrar, motivos rápidos, justificar/reabrir                          | `store.close/reopen`; enums/validação do backend; mantém note/revision                              | Ganhar não cria venda ou pagamento; motivo de perda obrigatório                                  |
| Venda vinculada, disponibilidade e histórico auditado                  | `store.linkSale/history`, dados de vendas autorizados já disponíveis                                | Funções anteriores preservadas em expansão; não inferir pagamento/entrega                        |
| Undo, toast, busy, refresh, atalhos, Ctrl+K, ESC/foco                  | Escrita inversa autorizada para interesse; undo local verificado no escopo                          | Sem undo fictício de create/close; refresh usa API e não delay de servidor inventado             |
| Ajuda/ferramentas/usuário e tema                                       | Topbar oficial + comandos contextuais do V8                                                         | Restaurar seed fictício removido de contas reais; nenhum reset destrutivo                        |
| Análise de mensagens anterior                                          | Details separado sob a experiência comercial original                                               | Motor heurístico/revisão/evidências preservados; sem dois renderers comerciais                   |

Não são necessários novos endpoints para os campos comerciais existentes. Sincronizar
valor estimado, retorno, nota e contato exige desenho de API/migration aprovado em
outra etapa. Ações autenticadas nunca fazem fallback para localStorage.
