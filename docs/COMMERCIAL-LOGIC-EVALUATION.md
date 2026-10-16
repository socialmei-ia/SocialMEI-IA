# Avaliação comercial sintética — PR #55

Corpus: 20 cenários, quatro por segmento, com mensagens e expectativas fixadas antes da primeira execução em [commercial-evaluation.cjs](../tests/fixtures/commercial-evaluation.cjs). Referência fictícia: 16/10/2026, 12h UTC. Baseline: `06d4ce6`, regras `local-rules-2`; correção: `local-rules-3`. Nenhum dado real, API ou alteração visual.

## Resultado

Antes: 17/20 cenários compatíveis com as expectativas, três reclamações encaminhadas incorretamente à fila comercial e ordem global incorreta. Depois: 20/20 compatíveis, sem reclamação ou recusa promovida a venda **neste corpus**; ordem global e sugestões verificadas. São verificações regressivas do mesmo conjunto usado para encontrar os bugs, não acurácia estimada, calibração ou validação independente.

| ID  | Segmento e situação                                          | Classificação da última mensagem / encaminhamento | Resultado |
| --- | ------------------------------------------------------------ | ------------------------------------------------- | --------- |
| p1  | Perfumaria · Compra e entrega                                | high / first                                      | Mantido   |
| p2  | Perfumaria · Pesquisa declarada                              | exploratory / clarify                             | Mantido   |
| p3  | Perfumaria · Recusa explícita                                | declined / declined                               | Mantido   |
| p4  | Perfumaria · Produto quebrado e devolução                    | insufficient / support                            | Mantido   |
| m1  | Mercadinho · Compra explícita com prazo                      | high / first                                      | Mantido   |
| m2  | Mercadinho · Reclamação de alimento vencido                  | insufficient / support                            | Corrigido |
| m3  | Mercadinho · Compra concluída e prazo                        | insufficient / completed                          | Mantido   |
| m4  | Mercadinho · Pesquisa de preço                               | exploratory / clarify                             | Mantido   |
| b1  | Barbearia · Agendamento explícito                            | high / first                                      | Mantido   |
| b2  | Barbearia · Objeção ao preço                                 | unclear / clarify                                 | Mantido   |
| b3  | Barbearia · Agendamento recusado                             | declined / declined                               | Mantido   |
| b4  | Barbearia · Correção de serviço anterior                     | unclear / support                                 | Corrigido |
| c1  | Costureira · Orçamento de ajuste                             | initial / first                                   | Mantido   |
| c2  | Costureira · Contratação condicionada ao orçamento           | unclear / clarify                                 | Mantido   |
| c3  | Costureira · Desistência posterior ao pedido                 | declined / declined                               | Mantido   |
| c4  | Costureira · Retrabalho de ajuste anterior                   | unclear / support                                 | Corrigido |
| a1  | Assistência de celulares · Contratação com urgência          | high / first                                      | Mantido   |
| a2  | Assistência de celulares · Celular com defeito e orçamento   | insufficient / support                            | Mantido   |
| a3  | Assistência de celulares · Consulta após recusa              | initial / clarify                                 | Mantido   |
| a4  | Assistência de celulares · Referência a atendimento anterior | insufficient / unknown                            | Mantido   |

Os identificadores técnicos acima correspondem às categorias e grupos já presentes no motor; `first` é acompanhar primeiro, `clarify` é esclarecer, `unknown` é entender necessidade. `insufficient` em pós-venda significa ausência de intenção nova suficiente, não ausência de importância do atendimento.

## Bugs comprovados e corrigidos

- **m2:** “O leite que comprei está vencido. Quanto custa trocar?” retornava `initial / inquiry`. A reclamação explícita agora leva a `insufficient / support`.
- **b4/c4:** “Meu corte ficou torto. Quero agendar uma correção.” e “A barra ficou torta. Quero contratar o conserto do mesmo ajuste que você fez.” retornavam `high / first`. Agora retornam `unclear / support`; não se presume nova contratação comercial.
- Mudança restrita ao reconhecimento de expressões de defeito/validade no sinal de suporte existente. Não foram alterados ranking, revisão humana, encaminhamentos, sugestões ou limiar temporal. Seis contrastes verificam negações, hipótese futura e orçamento vencido, para evitar uma expansão indiscriminada de suporte.

## Ordem, motivos e recomendações

Fila comercial esperada e observada: `a1 → b1 → m1 → p1 → c1 → a3 → c2 → b2 → m4 → p2 → a4`. Os quatro primeiros têm compra/contratação com prazo; c1 é orçamento sem urgência; depois vêm esclarecimentos e informação insuficiente. Recência desempata dentro dos grupos. Inverter a entrada não muda a fila; segmentos e volume não conferem bônus. Suporte, compra concluída e desistências ficam separados; sua ordem de exibição não representa importância de atendimento.

Todos os 20 cenários verificam o motivo do encaminhamento e a recomendação correspondente. Todas as evidências são comparadas com o trecho e os índices da mensagem do próprio cliente. A revisão dos resultados confirmou orientação de atendimento para reclamações, respeito à recusa, verificação de compra relatada, escopo/orçamento/prazo para serviço conhecido e orientação neutra quando falta contexto, sem inventar preço ou disponibilidade.

## Ambiguidades e limites restantes

- **a2 — ambiguidade legítima:** celular que “não funciona” pode exigir suporte de compra anterior ou primeiro reparo pago. O encaminhamento ao atendimento é prudente, mas pode deixar uma venda de serviço fora da fila comercial; perguntar pelo histórico é necessário.
- **a3 — ambiguidade legítima:** recusar um celular e perguntar sobre troca de tela pode indicar mudança de oferta, não contradição. O motor pede esclarecimento e não promove automaticamente. Não foi alterado para adivinhar a referência.
- **m1/c1 — vocabulário/contexto:** arroz e ajuste de barra não recebem identificação específica completa; sugestões neutras são aceitáveis. **a4:** “igual ao da outra vez” depende de histórico; urgência isolada continua insuficiente.
- Regras finitas ainda podem perder reclamações com outras palavras, ironia, erros de escrita ou referências indiretas. Evidência literal prova presença das palavras, não compreensão do sentido. Relato de compra não comprova pagamento; suporte resolvido e retomada de interesse exigem confirmação humana.
- A janela de 24 horas continua **experimental**, centralizada em `EXPERIMENTAL_POLICY.followUpHours`, sem validação por segmento nem configuração de usuário nesta etapa.

## Verificação e parecer

`node --test tests/commercial-evaluation.test.cjs tests/customer-priority.test.cjs tests/purchase-intent.test.cjs`: 88 testes passaram (20 cenários, ordem, contrastes e regressões anteriores). Prettier dos arquivos alterados e `git diff --check` passaram. Sem redesenho ou nova rodada de capturas; a camada visual não mudou.

**Pronto para demonstração supervisionada com dados fictícios**, com revisão das evidências antes de qualquer abordagem. Sem bloqueadores observados nesse escopo após as correções. Para homologar uso comercial definitivo ainda faltam avaliação independente e representativa, critérios de erro por negócio, resolução de contexto/histórico e validação da janela temporal. Não está aprovado para priorização autônoma ou integração com dados reais. PRs #54/#55 permanecem Draft, sem merge/deploy.
