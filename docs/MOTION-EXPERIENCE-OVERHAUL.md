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

A revisão encontrou ainda uma colisão entre a chave de uma conversa fictícia e a de um contato real com o mesmo nome. Apenas amostras agora usam o prefixo `demo:`; as chaves reais permanecem idênticas. O painel de uma conversa fictícia também não consulta o cadastro real por nome. Edição de perfil, observação, etiquetas e criação de cliente ficam bloqueadas no modo de teste, inclusive em submissão direta. A exclusão de exemplos continua persistindo e respeita também os marcadores antigos, sem recuperar rascunhos/estado de contatos reais.

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

238 testes Node passaram. A matriz nova de comunicação cobre 312 estados: 13 destinos nativos, seis larguras (320/390/768/1024/1280/1440), claro/escuro e demonstração ligada/desligada. Testa preservação dos registros, ausência de amostras fora do modo, indicador único, teclado/foco, menus e contadores.

Os testes de gráficos mediram descontinuidade zero na interrupção de linhas, barras e segmentos; verificam fonte/CSV intactos, segunda série, foco, toque e movimento reduzido. Isso não representa medição de FPS em aparelhos físicos.

Capturas equivalentes: base imutável extraída do HEAD inicial, mesma data controlada, fonte fictícia explicitamente ativada e mesmos módulos/temas/larguras. O modo reduzido permite comparar layouts assentados; vídeo registra movimento separado. [Galeria antes/depois](motion-experience-evidence/README.md).

### Comparação de composição

| Oportunidades             | Antes | Depois |
| ------------------------- | ----: | -----: |
| Abas, desktop 1440px      | 517px |  228px |
| Primeiro cliente, desktop | 667px |  316px |
| Abas, mobile 390px        | 748px |  235px |
| Primeiro cliente, mobile  | 950px |  341px |

Valores aproximados da posição vertical na mesma amostra, iguais nos dois temas. A correção mobile também preserva o orçamento vertical de Clientes/Vendas: o botão Ferramentas mantém alvo de 44px sem acrescentar uma linha invisível no cabeçalho.

### Desempenho medido

Chromium 151 headless em Linux, orçamento de duas CPUs, 1440×1000, sem CPU throttling, fonte/data/ações equivalentes. Uma sequência isolada de aproximadamente seis segundos em cada versão; gravação de vídeo desligada nesta medição. A primeira medição, concorrendo com outras suítes e gravando vídeo, apresentou ruído e não foi utilizada para afirmar fluidez. O vídeo de evidência permanece separado.

| Medida                                  |  Antes | Depois |
| --------------------------------------- | -----: | -----: |
| Intervalo mediano de frame              |   16ms |   16ms |
| Percentil 95                            |   18ms |   18ms |
| Frames acima de 33,5ms                  |      6 |      5 |
| Tarefas acima de 50ms                   |      0 |      0 |
| Soma de deslocamentos sem input recente | 0,0220 |      0 |
| Animações após reduzir movimento        |      0 |      0 |

A amostra sustenta fluidez próxima de 60 FPS nesse laboratório, sem garantia para aparelhos modestos. Os deslocamentos incluem navegações deliberadas: não são uma certificação de Core Web Vitals. [Dados completos](motion-experience-evidence/performance-results.json).

### Testes e revisão final

- `npm test`: 238 aprovados.
- Matriz nova: 312 estados, seis larguras, dois temas, demonstração ligada/desligada; preservação de dados, teclado, foco, submissão protegida e ausência de erros JavaScript.
- Gráficos: geometria monotônica, interrupção sem salto, fontes/CSV preservados, segunda série, teclado/toque e movimento reduzido.
- Relatórios V2 e V2.1: suites nativas conferiram CSV/PDF contra snapshots, histórico imutável/isolado, formatos BR/ISO, modal, filtros, cancelamento, falhas e fontes local/remota.
- Estabilidade: 935 estados de layout/tema e 121 estados de botões; zero pageerror/404 local.
- Revisão visual: 22 estados de Home e 22 de Financeiro; privacidade, foco, navegação, touch e movimento reduzido.
- Configurações: 990 estados; modos local/conectado, salvar, temas e teclado.
- Regressões específicas: 484 estados locais/remotos em 11 resoluções; 36 estados de ferramentas e 936 colunas de gráficos; contatos, telefone/Instagram, exclusão persistente e cliente preservado.
- A suíte agregada `npm run test:browser` e `npm run format:check` são gates obrigatórios da PR. O resultado no HEAD final fica registrado no GitHub Actions, junto às evidências geradas no CI; consultar os checks da PR.

Falhas encontradas e corrigidas durante QA: indicador perdido quando a Caixa atualizava o título; namespace de exclusão de exemplos; possibilidade de alcançar o CRM por uma conversa fictícia; altura excedente do controle Ferramentas no mobile. Expectativas de texto/seletores antigos foram adaptadas à ajuda recolhível, mantendo verificações de fonte e ausência de execução externa. Nenhuma falha foi contornada com relaxamento dos limites de layout ou dos contratos financeiros.

Finish gate: interface integrada revisada nas capturas reais de oito módulos, desktop/mobile, claro/escuro. Informação essencial permanece junto às ações, sem novos controles de publicação fictícia. Verificação automatizada e visual em Chromium; validação com leitor de tela real e aparelhos físicos permanece pendente antes da publicação.

## Histórico e continuidade

HEAD funcional: `e91abec4a79adf21973fc02c1b3ad5cd5a8f2158`. O commit posterior reúne somente documentação e evidências; o HEAD final completo deve ser conferido na PR.

- `c6e5e4b`: comunicação consolidada e movimento nativo.
- `c64fa21`: gráficos, transições contínuas e pontos acessíveis.
- `38b9443`: contratos de ajuda contextual e isolamento de conversas.
- `e91abec`: bloqueio de gravação comercial em demonstração, exclusão compatível e controles mobile compactos.
- Entrega: galeria com 64 capturas, vídeo, resultados e relatório neste diretório.

Próxima ação: revisão da PR Draft, validação em aparelho físico/leitor de tela e autorização específica antes de qualquer merge ou publicação. Não há alteração em AWS, banco, autenticação, API, n8n, WAHA, credenciais ou volumes. Nenhuma ação de produção foi executada.
