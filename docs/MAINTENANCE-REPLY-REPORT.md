# Manutenção e preparação de respostas

Base #92 (`c2a0dfc`), branch `fix/maintenance-reply-readiness`. Ancestralidade da
cadeia #83/#89/#90/#91/#92 preservada. #93 continua separada; main não foi alterada.

## Resultado selecionado

- **P0:** nenhum defeito P0 confirmado nesta intervenção; não equivale a homologação.
- **P1 corrigido:** clicar novamente em Usar na conversa duplicava a mesma sugestão
  após o texto humano. Regressão vermelha reproduziu o prefixo e o fecho humanos.
  Agora uma sugestão integral já presente é preservada, sem nova inserção ou envio.
- **P1 corrigido nos gráficos:** substituir o gráfico Financeiro com os mesmos
  dados perdia o ponto fixado e podia reabrir um tooltip dispensado. Dois testes
  vermelhos reproduziram os casos. A interação agora acompanha a substituição
  apenas com assinatura igual; saída real de foco continua dispensando o tooltip.
- **Preparação P1:** o contrato sintético não aceitava hora original. Campo opcional
  `occurred_at`, UTC canônico e leitura por horário/ID reutilizam a coluna existente.
  Hashes/operações antigos continuam reproduzíveis, sem migration ou outro motor.
- **P2 da QA da extensão:** entradas extremas podiam exceder a conversão UTC e um
  offset com minuto60 era aceito. Testes vermelhos/verde cobrem rejeição422 sem escrita.
- **P2 no teste de sincronização:** a espera após reload consultava um identificador
  antes de carregar seu script. O erro foi observado na suíte completa; a espera
  agora aguarda a definição antes de exigir o mesmo negócio autenticado.
- Não houve redesign nem mudança cosmética de Automações, Assistente ou Caixa.

## Contrato e limites

[Preparação multicanal](MULTICHANNEL-REPLY-READINESS.md) mapeia identidade, direção,
texto, horários, rastreamento, revisão/descarte e exigências futuras de autenticação
na entrada/saída. A integração real permanece inexistente/desabilitada. Referências
sintéticas não comprovam vínculo com contas externas. Aprovação significa rascunho,
`transport:none`, nunca envio ou entrega.

Não há nova fila, tabela, autenticação, vínculo por nome, conector, API de envio ou
workflow. Texto editado preservado; se uma pessoa modificar a sugestão a ponto de
ela não estar mais integralmente no composer, inserir pode acrescentar outra versão.
Não se tenta deduplicar textos semanticamente parecidos.

## Evidências

[Resumo sanitizado](evidence/reply-maintenance/results.json) e testes versionados:

- `npm test`:305, sem falhas/skips; `npm run format:check`:aprovado.
- Python/FastAPI + PostgreSQL16 próprio:245, sem falhas/skips.
- Browser focado: rascunho humano antes/depois, reinserção, homônimos/canais,
  ausência de envio, 320/390/768/1024/1440 e claro/escuro, sem erros JS.
- HTTPS real: dois negócios, WhatsApp/Instagram fictícios, deduplicação canônica,
  mensagens fora de ordem, revisão/descarte, persistência e leitura cruzada404.
- Gráficos: fechamento por segundo toque/clique, preservação do ponto fixado e
  dispensado em redesenho, teclado e matriz claro/escuro da estabilização.
- Suítes completas e CI: resultados do HEAD final registrados na PR. Nenhuma
  assertiva removida, timeout aumentado ou teste ignorado para obter aprovação.

O primeiro CI desta PR falhou no segundo toque do gráfico, que deveria fechar o
tooltip. A investigação reproduziu a perda de estado durante o redesenho; a
regressão nova força essa substituição, sem depender de temporização. A revisão
reproduziu também o primeiro hover após Escape; um teste adicional verifica que
movimento físico reabre a inspeção sem fazê-lo na simples restauração do DOM. Isso não
confirma a causa do timeout histórico da Issue #73.

A revisão independente identificou os casos de UTC extremo e texto humano; foram reproduzidos
antes das correções e acrescentados às regressões. A inspeção inicial de possível
sobrescrita na primeira inserção **não se confirmou**, portanto esse caminho não
foi alterado.

Ambiente desta execução: Docker/PostgreSQL/HTTPS exclusivamente locais, com projeto
`socialmei-reply-preview` e banco de testes separados. Um volume de preview antigo
não correspondia ao `.preview/.env` do novo worktree; foi preservado, sem troca de
senha ou remoção. A prévia de teste passou a usar volume próprio. CA do proxy e
exceções para aliases internos/loopback foram usadas somente em arquivos temporários
fora do Git; Dockerfiles/Compose oficiais e serviços existentes foram preservados.

## Pendências reais

- Revisar esta PR e a cadeia dependente; combinar #93 exige decisão/validação
  próprias. Nenhum merge/rebase/cherry-pick foi realizado.
- Contas/provedores autorizados, assinaturas reais, thread/grupos, mídia,
  rastreamento separado de hora de origem/recebimento e transporte de saída exigem
  contratos e homologação futuros. Não são integrações concluídas nesta entrega.
- A Issue #73 permanece aberta: CI verde nesta rodada não prova a causa do timeout
  histórico do Financeiro. Não se atribuiu uma correção não reproduzida.
- Celular físico, leitor de tela físico e homologação operacional não executados.

Nenhuma operação na AWS, n8n/WAHA/Meta ativos, dados reais, credenciais de produção,
banco real, publicação, merge ou deploy.
