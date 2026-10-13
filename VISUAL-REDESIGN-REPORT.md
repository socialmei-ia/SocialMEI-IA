# Redesign visual — implementação e validação

Data: 13/10/2026. Branch: `feat/visual-redesign`. Base Git: `31a94c2b1c9eb4b80c5a6413e71e1cd383178862`.

## Escopo e estado de publicação

Aplicada a solicitação de analisar os três textos anexados e implementar o redesign por etapas em todas as telas existentes. A interface continua em HTML, CSS e JavaScript puro. Nenhuma alteração de backend, SQL, integração, credencial, Docker ou workflow n8n foi feita.

Este relatório descreve o código da branch e a validação isolada. A última publicação de produção informada pelo usuário permanece em `ae73f6e093fc2d271a69a2ba9de1ebffc66c0705`; o redesign não foi instalado no servidor por esta tarefa. Não há acesso SSH direto confirmado neste ambiente. GitHub e CI não comprovam o runtime da AWS.

Backup local do frontend da base feito antes da edição por `git archive`, SHA256 `927e7f3df57e5bb82cca91d893d7f70f8f6d29deacce447e7f3b12d279b7bad3`. É uma cópia de código, não backup de banco ou configuração privada do servidor.

## Conceito e referências

Mais espaço e hierarquia nas apresentações; mais clareza no trabalho diário. Fundo claro quente, superfície branca, escuro azul profundo, azul para ação e dourado em detalhes da marca. O produto mantém conteúdo, logo, rotas, controles e limitações.

Foram consultadas páginas públicas de [Mobbin](https://mobbin.com/), [21st](https://21st.dev/), [Origin UI](https://21st.dev/community/originui/library/origin-ui), [Motion Primitives](https://21st.dev/community/ibelick/library/motion-primitives) e [Navigation Menu](https://21st.dev/community/components/s/navigation-menu). O acesso de referência forneceu texto/conteúdo estruturado; não permite afirmar que velocidades ou animações específicas do Mobbin foram medidas visualmente. A composição e o motion implementados são decisões do SocialMEI, com apoio no código dos componentes anexados.

### Componentes fornecidos

1. **Password strength:** quatro barras, sugestões e aviso de padrões previsíveis adaptados para JavaScript puro. Respeita o `minlength` real do campo (8 no fluxo local; 12 quando configurado pelo fluxo de conta). É orientação: não altera validade, submissão, política da API ou login. Texto em português, anúncio adiado 700ms, regras por teclado, cleanup de campos dinâmicos e tratamento de reduced motion. Nenhuma senha é registrada, armazenada ou enviada pelo componente.
2. **GlowCard / spotlight:** efeito convertido em gradiente local azul/dourado em três superfícies da landing. Um único card ativo, atualização por `requestAnimationFrame`, eventos passivos, sem ponteiro global contínuo ou bloqueio touch. Desligado com movimento reduzido, touch, página oculta ou saída da landing. Sem biblioteca nova, cores neon ou efeito em todos os cards.

O [design system](docs/DESIGN-SYSTEM.md) registra valores reais, componentes, exceções legadas e manutenção.

## Antes e depois por área

| Área                          | Antes                                                                 | Implementado                                                                                                                                             |
| ----------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Home                          | Headline animada, superfícies repetidas e foco concentrado em atalhos | Busca e ações imediatas, conversa contextual, lista de prioridades e últimas vendas do estado existente; vazio sem falsa sensação de atividade           |
| Sidebar / topbar              | Peso visual e destaque disperso                                       | Sidebar de 232px, seleção azul suave, menos sombra e mais espaço no conteúdo; destinos preservados                                                       |
| Caixa Unificada               | Painéis com pouca diferenciação                                       | Lista, conversa e contexto separados por superfície e hierarquia; composer e ações existentes mantidos                                                   |
| Clientes                      | Diretório com apresentação densa                                      | Linhas, filtros, espaços e textos refinados; CRUD, busca, importação e drawer preservados                                                                |
| Produtos                      | Catálogo com hierarquia uniforme                                      | Preço e identificação mais claros, cards mais tranquilos; contrato monetário preservado                                                                  |
| Vendas                        | Lista e controles visualmente pesados                                 | Ações e tabela mais legíveis; links da Home navegam, enquanto Registrar venda continua abrindo criação                                                   |
| Financeiro                    | Resumo com métricas de peso semelhante                                | Saldo registrado domina; demais métricas separadas. Mobile em uma coluna até 720px para evitar quebra dos valores usuais                                 |
| Relatórios / visão de negócio | Muitas superfícies e efeitos competindo                               | Painéis mais sóbrios e números com hierarquia; cálculos, períodos, exportação e correção de tooltip mantidos                                             |
| Assistente                    | Composição pesada entre contexto e saída                              | Área de contexto, intenção e rascunho com foco mais claro; geração local e revisão permanecem                                                            |
| Automações                    | Etapas e resultado com apresentação genérica                          | Etapas, estado e próxima ação mais claros; testes e execução continuam locais conforme o produto atual                                                   |
| Configurações / Administração | Painéis e botões de conta pouco alinhados ao restante                 | Tipografia, espaços, superfícies e controles harmonizados; regras, permissões e contratos inalterados                                                    |
| Auth / onboarding             | Campos e composição pouco diferenciados                               | Identidade compartilhada, campos de 48px, progresso existente e indicador complementar de senha; sem novo cadastro público ou recuperação de senha       |
| Landing                       | Hierarquia e ritmo menos coerentes com o app                          | Títulos editoriais, fundo e superfícies alinhados ao tema, maior espaço entre seções e spotlight seletivo; demos existentes e suas ressalvas preservadas |

Os conteúdos de Home reutilizam `priorityItems()`, `operationalMetrics()` e os registros do estado atual. Não foram criadas métricas de crescimento, integração de IA, cálculo paralelo, WhatsApp real ou regra nova de negócio. A ocultação de valores monetários também cobre vendas recentes.

## Etapas no Git

1. Fundação: paleta, tipografia, spacing, tokens de motion e shell.
2. Componentes auxiliares acessíveis: senha e spotlight.
3. Home: contexto, operações e navegação sem abrir formulário em links de consulta.
4. Módulos, conta, autenticação, onboarding e landing: refinamento dos seletores existentes.
5. Polimento mobile, testes e documentação.

As regras alteradas foram consolidadas nos seletores existentes, em vez de anexar um tema inteiro ao fim do CSS. O CSS geral continua grande; não houve refatoração integral ou remoção de comportamento histórico não relacionado.

## Validação local

Ambiente isolado, APIs simuladas nos testes de navegador e tráfego externo bloqueado. PostgreSQL local descartável 17.11 nos contratos de API, sem conexão com produção. Chromium do ambiente. Os estados de demonstração usam dados sintéticos.

| Verificação                                          | Resultado                                                                                                                                     |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Node / contratos do repositório e indicador de senha | 63 passaram; zero falhas e skips                                                                                                              |
| Python / API contra PostgreSQL isolado               | 126 passaram; zero falhas e skips                                                                                                             |
| Operação / backup e gateway                          | 19 passaram; 5 testes de gateway Docker não executados localmente                                                                             |
| Total de testes unitários registrados                | 213: 208 passaram, 5 skips, zero falhas                                                                                                       |
| Regressão de navegador existente                     | 88 estados e 16 fluxos passaram                                                                                                               |
| Responsividade / temas                               | 825 estados de layout/tema e 185 estados de botões; zero erros JavaScript ou 404 locais                                                       |
| Interações novas                                     | 22 estados geométricos/tema da Home e 22 do Financeiro; navegação, privacidade, senha, teclado, spotlight, touch, vazio e reduced motion      |
| Auditoria de Ferramentas / gráficos                  | 36 estados e 936 colunas conferidos na validação de fundação; regressão existente preservada                                                  |
| Formatação / diff                                    | Prettier e `git diff --check`                                                                                                                 |
| Evidência visual                                     | 56 capturas anteriores e 56 posteriores: 14 telas × claro/escuro × 1440/390px; capturas adicionais de conta/administração e novos componentes |

A matriz cobre 1920, 1600, 1440, 1366, 1280, 1024, 900, 768, 430, 390 e 360px. Temas claro, escuro, automático claro, automático escuro e custom. Esses estados não são 825 testes independentes de integração externa.

Os fluxos existentes cobrem CRUD, busca/filtro, modais/drawers, toasts, armazenamento, importação/exportação, backup local, login/convite/administração com API controlada, erros remotos e preservação de edições. As capturas públicas de onboarding são do fluxo existente de demonstração, não prova de onboarding de MEIs em produção.

### Problemas encontrados durante implementação

- O helper de edição CSS usou inicialmente um offset incorreto, afetando seletores. A revisão visual identificou o problema; o helper foi corrigido e o CSS regenerado antes dos commits. A nova verificação de geometria protege o posicionamento do shell e da Home.
- Uma transição de navegação sobrepunha reduced motion. A cascata foi corrigida, preservando a asserção de nenhuma animação sob essa preferência.
- O novo `summary` de sugestões de senha tornou um seletor de teste ambíguo. O seletor foi restringido ao filho direto; o teste de troca de senha permanece e passou.
- A captura final mobile mostrou valores monetários quebrados no resumo financeiro. O layout foi ajustado para uma coluna e incluída asserção de linha única para os valores dos dados de teste nas 11 larguras e dois temas.

Não foram removidas asserções, aumentados timeouts para esconder falhas ou desativados testes para concluir a mudança.

## CI, publicação e limites

O workflow `Repository checks` mantém os jobs `validate` e `browser`. A matriz foi ampliada para 11 larguras e uma etapa de interações visuais foi adicionada. O CI executa PostgreSQL 16, gateway HTTPS protegido e stack Docker isolada, incluindo restauração de backup em banco separado. O resultado da execução deste PR deve ser consultado no GitHub; o sucesso do PR anterior não valida esta branch.

Docker local está sem daemon disponível, por isso os cinco testes dependentes ficaram como skip local. Caddy/HTTPS, stack e restore dependem do CI nesta revisão. Nenhum container de produção foi iniciado, atualizado, migrado ou restaurado.

Não confirmados por esta tarefa: FPS em hardware real, Lighthouse de produção, uso de CPU/GPU no telefone do usuário, homologação em Safari/Firefox, leitores de tela reais e funcionamento de n8n/WAHA/Instagram/IA remota. Não foram chamados webhooks legados ou enviados mensagens.

O orçamento de motion evita loops contínuos novos, limita efeito de ponteiro a um card e preserva animações por viewport e reduced motion. Isso reduz trabalho desnecessário, mas não equivale a uma medição de 60 FPS.

## Próxima etapa

Revisar comparação visual e PR, exigir CI aprovado no SHA final e aprovar merge/publicação separadamente. Depois da autorização, preparar atualização somente do frontend/gateway com backup e imagem anterior preservados, sem atualizar API, banco ou integrações por conveniência. Confirmar no navegador login, módulos, temas, mobile e logout/reentrada.

Continuam fora deste redesign: recuperação por e-mail, novo onboarding de MEIs, atendimento real, configuração de permissões PostgreSQL e reorganização integral do CSS. A estabilização existente continua sendo a fonte para essas etapas.
