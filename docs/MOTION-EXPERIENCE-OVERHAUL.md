# SocialMEI.IA — experiência, comunicação e movimento

## Base e escopo

- HEAD inicial de `main`: `6fe56d625f17a9f50164a3c9b2c971caa3150362`, conferido no remoto antes de editar.
- Branch: `feat/premium-experience-overhaul`, criada diretamente dessa base.
- Aplicação: `frontend/socialmei-app.html`, navegação oficial e JavaScript vanilla. Sem outra aplicação, dependência nova, alteração de cálculo, autenticação, backend ou infraestrutura.
- Publicação: somente PR Draft. Merge e deploy dependem de autorização posterior.

## Problemas e decisões

O modo de teste acumulava banner global, aviso experimental, aviso da fonte e dois botões antes das abas de Oportunidades. A mesma limitação reaparecia em diversos módulos. A apresentação tinha precedência sobre os próprios clientes.

Agora um único componente identifica a demonstração no cabeçalho. Na Caixa desktop, que intencionalmente oculta a topbar, o mesmo elemento ocupa o cabeçalho nativo da lista. Não há cópia concorrente. O menu oferece explicação, configuração e desativação; Enter/Escape e foco são preservados. A ativação/desativação usa o toast real, com anúncio acessível e desaparecimento temporizado.

Os controles de reanálise/encerramento ficam em **Opções da análise**. A fila começa após título, subtítulo e três abas. Informações completas continuam em Ver conversa; o cartão antecipa o primeiro dado desconhecido. Classificação, revisão humana, evidências e separação comercial/suporte não mudaram.

## Inventário e política de comunicação

Foram procurados textos estáticos e dinâmicos no HTML e nos scripts nativos. Arquivos de demonstrações antigas não são carregados na aplicação e não foram reescritos.

| Contexto                             | Apresentação                                                                                                 |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| Dados de teste ligados               | Um indicador global, menu com explicação da origem e toast de confirmação                                    |
| Dados de teste desligados            | Sem indicador nem exemplos da amostra; registros originais preservados                                       |
| Demonstração isolada de análise      | Mesmo indicador, explicação limitada à análise; desligar encerra essa demonstração                           |
| Dados reais e amostra na mesma lista | Identificação pontual `Exemplo` nas conversas fictícias                                                      |
| Home e perfil local                  | Ajuda recolhível “Sobre este espaço”; módulos futuros continuam identificados                                |
| Caixa/Assistente local               | Ajuda recolhível; rascunho e ausência de envio permanecem explícitos junto à ação                            |
| Oportunidades                        | Regras em ajuda e menu; recomendação heurística/revisão aparecem no contexto da decisão                      |
| Automações                           | “Como funcionam as rotinas” recolhível; habilitação e teste simulado mantêm textos próprios                  |
| Relatórios                           | Origem/definições recolhíveis; falha da fonte continua aberta e visível; exportações preservam a origem      |
| Divulgação                           | Ajuda sobre rascunhos/publicação; ausência de conexão, seleção de mídia e erros continuam no momento da ação |
| Configurações                        | Sessão/armazenamento recolhíveis; preferência dos dados de teste permanece explícita                         |
| Rodapé                               | Uma seção “Origem e armazenamento”, sem parágrafos repetidos em cada tela                                    |
| Erro real                            | Mantido visível; toast `role=alert`, cor de erro, conteúdo escapado                                          |
| Sucesso/informação reais             | Toast `role=status`; nenhuma simulação de processamento remoto                                               |

A revisão encontrou ainda uma colisão entre a chave de uma conversa fictícia e a de um contato real com o mesmo nome. Apenas amostras agora usam o prefixo `demo:`; as chaves reais permanecem idênticas. O painel de uma conversa fictícia também não consulta o cadastro real por nome.

## Componentes, gráficos e movimento

- `premium-experience.css/js`: acabamento nativo, indicador móvel da sidebar, entrada seletiva de novos itens e contadores de gestão. Os números finais continuam no DOM; a camada visual não modifica registros ou exportações.
- `motion.js`: uma animação por alvo, cancelamento seguro em interações rápidas e restauração de `will-change`. Entrada discreta em Home/Caixa/gestão; sem desfoque em texto operacional.
- Linhas de Relatórios: interpolação monotônica, sem picos inventados entre valores; desenho progressivo e transição a partir da geometria efetivamente exibida. As coordenadas dos registros são preservadas.
- Barras: alteração por `transform`/`opacity`, com dimensões finais estáveis e continuidade ao interromper uma transição.
- Tooltips: ponto ativo, guia, alvo por faixa, teclado, toque e fechamento por toque externo/repetido. A série financeira secundária permanece acessível.
- Controles: foco visível, pressionado, seleção, menus e detalhes contextuais; sem atraso artificial nem movimento contínuo.
- Movimento reduzido: contadores e transições encerram imediatamente; foco e informações permanecem disponíveis.
- Landing, autenticação e onboarding: composição aprovada, lógica e animações existentes preservadas; refinamentos comuns de foco/seleção/hover, sem refazer o fluxo.

## Skills e agente

O catálogo local apresentou 13 Skills: `agent-routing`, `ai-eval-gate`, `database-migration`, `feature-plan`, `incident-triage`, `interface-finish-gate`, `maintainability-review`, `mei-pilot-research`, `n8n-workflow-review`, `prototype-first`, `release-check`, `team-deploy`, `visual-qa`. O catálogo do ambiente também foi consultado; não foram carregadas todas as instruções.

Utilizadas: `.agents/skills/visual-qa/SKILL.md` para matriz real de navegador, foco, movimento reduzido e comparação; `.agents/skills/interface-finish-gate/SKILL.md` para hierarquia, legibilidade mobile, ações honestas e revisão final. Seguidos `AGENTS.md`, `frontend/AGENTS.md`, design system e perfil frontend. A autorização explícita desta tarefa dispensa novo protótipo intermediário.

Um agente especializado, `premium_charts`, trabalhou exclusivamente em geometria/interação dos gráficos e testes próprios. O restante foi implementado e conferido diretamente. Nenhum outro agente foi convocado.

## Verificação e evidências

Checkpoint: 236 testes Node passaram. A matriz nova de comunicação cobre 312 estados: 13 destinos nativos, seis larguras (320/390/768/1024/1280/1440), claro/escuro e demonstração ligada/desligada. Testa preservação dos registros, ausência de amostras fora do modo, indicador único, teclado/foco, menus e contadores.

Os testes de gráficos mediram descontinuidade zero na interrupção de linhas, barras e segmentos; verificam fonte/CSV intactos, segunda série, foco, toque e movimento reduzido. Isso não representa medição de FPS em aparelhos físicos.

Capturas equivalentes: base imutável extraída do HEAD inicial, mesma data controlada, fonte fictícia explicitamente ativada e mesmos módulos/temas/larguras. O modo reduzido permite comparar layouts assentados; vídeo registra movimento separado. [Galeria antes/depois](motion-experience-evidence/README.md).

### Finalização pendente neste checkpoint

- Concluir regressões completas de navegador, visual, estabilidade e formatação.
- Registrar medição de desempenho de laboratório e revisão visual final.
- Consolidar commits, abrir PR Draft e conferir CI remoto no HEAD final.
- Validar em aparelho físico e leitor de tela real antes da publicação; automação Chromium não substitui essas verificações.

Nenhuma ação de produção foi executada.
