# V2 Foundation — base para evolução

Revisão de 15/10/2026, America/Fortaleza. Este plano complementa [FUTURE-READINESS-REVIEW.md](../FUTURE-READINESS-REVIEW.md); não substitui evidências datadas por uma suposta nova auditoria da AWS.

## 1. V1: baseline candidata

Código de partida: `main`, `db775dc5ae427eafed01a7dcd0d365dc92b23a16`, merge do [PR #47](https://github.com/socialmei-ia/SocialMEI-IA/pull/47). Checkout local limpo e árvore igual à branch testada do cadastro temporariamente aberto. Branch desta rodada: `chore/v2-foundation`.

O responsável forneceu publicação conferida desse SHA na AWS: API/gateway atualizados, 41 arquivos frontend e 35 API conferidos, Basic e API anônima retornando 401; CRM ready, auth enabled/schema ready, channels prepared/not_checked. Backup anterior: `team-auto-20261015-012244-734d84`. São evidências fornecidas, não SSH deste chat.

Cadastro sem convite está publicado segundo essa saída. Falta confirmação humana final de criar conta nova/sair/entrar. O visual aprovado permanece intacto. Nenhuma migration, configuração privada ou integração viva é alterada nesta rodada. API de planilha e executor n8n dos PRs #45/#44 continuam fora da baseline.

**Decisão:** candidata a V1, não release definitiva. Não criar tag `v1.0.0` enquanto aceite de contas, testes finais do SHA e bloqueios críticos de operação estiverem pendentes. Versão npm `0.1.0` identifica ferramentas; não alterá-la para simular release do produto. Quando os gates passarem, propor uma tag anotada sobre o merge aprovado, com imagens e evidência de runtime próprias.

## 2. Problema de ambientes

[ENVIRONMENTS.md](ENVIRONMENTS.md) é o mapa canônico: demo estática/local, Docker dev, CI, Pages condicional, AWS team/piloto, legado e staging apenas planejado. A AWS possui dois projetos Compose. O n8n legado e sua API auxiliar não são o `team-api` autenticado.

Não há dependência do Python do notebook para um HTTP Request executado no n8n da AWS. Code node precisa de executor próprio; arquivo/planilha deve existir no serviço que o usa, com armazenamento persistente e backup. O erro HTTP “Campo obrigatório” é um contrato errado, distinto de Python ausente. Diagnóstico e limites em [PYTHON-N8N.md](PYTHON-N8N.md).

## 3. Fontes de verdade

| Responsabilidade                                             | Fonte                                                             |
| ------------------------------------------------------------ | ----------------------------------------------------------------- |
| Código, contratos, configuração pública e dependências       | GitHub, branch/commit revisados                                   |
| Processos, mounts, imagens instaladas e configuração privada | Runtime AWS, conferido por serviço                                |
| Dados persistentes, contas e sessões                         | PostgreSQL de cada ambiente; não exports JSON de demonstração     |
| Orquestração, agenda e integrações                           | n8n; export versionado precisa corresponder à versão publicada    |
| Ambiente de execução reproduzível                            | Dockerfile, Compose, dependências fixadas e imagens identificadas |
| Segredos                                                     | Cadastro privado no alvo autorizado; nunca Git, HTML ou conversa  |

GitHub verde não significa AWS atualizada; container running não significa integração connected. Mudanças locais inesperadas no servidor bloqueiam atualização e devem ser reconciliadas com o Git, sem descarte automático.

## 4. AWS como runtime

Team em `/home/ubuntu/socialmei-team`; legado em `/home/ubuntu/socialmei`; backups privados em `/home/ubuntu/socialmei-backups`. O checkout team usa detached HEAD aprovado. O acesso deste chat oferece GitHub/testes locais, sem identidade AWS, SSH ou credenciais n8n. Nenhum comando deste plano foi aplicado remotamente.

O site oficial conhecido é `https://socialmei-ia.54-94-213-7.sslip.io/`. A raiz é servida por `frontend/socialmei-app.html`. URLs `localhost` de desenvolvimento não são links para o grupo. AWS/região/IAM/Security Groups completos, Elastic IP e cobertura operacional de todos os backups continuam **NÃO CONFIRMADOS**.

## 5. GitHub → AWS e rollback

Branch de tarefa → testes locais → PR/CI → revisão/merge → SHA aprovado → leitura do alvo/backup → build de serviços afetados → conferência → troca restrita → saúde/smoke → recibo. O procedimento canônico é [DEPLOYMENT.md](../DEPLOYMENT.md), com operação em [OPERACAO-EQUIPE.md](OPERACAO-EQUIPE.md).

| Mudança                                          | Como chega ao serviço                                                                                     |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| `frontend/scripts/`, estilos, HTML/assets do app | `deploy/team/Dockerfile` copia frontend; reconstruir apenas gateway                                       |
| `python-service/scoring.py` futuro               | `COPY *.py ./` da API inclui o módulo; importá-lo explicitamente no router/app; reconstruir API relevante |
| `requirements.txt`/`.lock`                       | Copiados antes do código; rebuild da API reinstala a camada de dependências e executa `pip check`         |
| Export n8n                                       | Git não importa nem ativa; operação de importação/revisão separada no n8n autorizado                      |
| Migration nova                                   | Etapa própria com revisão, backup e autorização; não rodar migrador por padrão                            |
| `prototypes/`/documentação                       | Revisão e artefatos; Dockerfile do gateway não copia protótipos                                           |

Antes de publicar, registrar SHA anterior/novo, IDs exatos de imagem por serviço, lista/ordem dos Composes efetivos por labels, arquivos privados por hash, containers/StartedAt e backup verificado. API/gateway podem ter SHAs diferentes. Não unir overlays de serviços por conveniência nem usar workflow genérico de produção para team.

Separar build de `up`. Trocar somente serviço autorizado, sem dependências, sem build/pull na troca, com imagem já conferida e recibo que bloqueie repetição. Conferir arquivos realmente presentes, Basic401, API anônima401 e saúde das capacidades. O smoke humano verifica contas e módulos, não só `/health`.

Rollback preparado aponta checkout/imagem/configuração anteriores por serviço, com mesmo projeto/redes/volumes. Em falha, parar e revisar o recibo; a recuperação é uma etapa dirigida. Não usar restore de produção como teste, não repetir publicação cegamente, não trocar chave n8n. Dump com hash/índice válido não prova restauração ensaiada.

## 6. Python + n8n

Padrão: lógica do domínio em FastAPI versionado; n8n chama contratos HTTP e orquestra. JavaScript simples no nó é permitido. Runner oficial externo é opção para Code Python, avaliada separadamente. Não instalar pacotes dentro de container vivo.

O export manual `/processar` passa a ter nomes de ação e timeout explícitos; o grafo continua com os mesmos dois nós e sem credenciais/ativação. O teste Python usa o corpo desse próprio JSON e reproduz o erro422 quando enviado `chatInput` sem mapear `texto`. Isso testa API/contrato local, não execução no editor n8n.

Rotas de pedidos/planilha do PR #45 exigem revisão própria: opt-in, dados fictícios, volume persistente, autenticação e teste de confirmação/idempotência. Não transformar exemplo de estoque em dependência do CRM de serviços.

## 7. Dependências

| Camada         | Declaração atual                                                                    | Limite / próximo gate                                                                   |
| -------------- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Node/npm       | Node22 no CI; engines >=22; Playwright1.62.1/Prettier3.9.9 e package-lock           | Usar `npm ci`; Node local pode ser mais novo; não afirmar Windows validado sem execução |
| Python         | Python3.12-slim; requirements diretos exatos + constraints transitivas desta rodada | Instalação limpa, `pip check`, HTTP/SQL/browser/CI; versões da AWS não inferidas        |
| PostgreSQL     | postgres:16-alpine; migrations001–011                                               | Digest/patch por ambiente pendentes; não atualizar banco nesta rodada                   |
| n8n            | Compose versionado usa latest; responsável observou2.40.5                           | Conferir digest e compatibilidade dos exports antes de fixar/impor no alvo              |
| WAHA           | latest/GOWS no Git; WEBJS observado na AWS                                          | Divergência conhecida; preservar engine/sessão e homologar separadamente                |
| Caddy          | caddy:2-alpine; borda legada e gateway separados                                    | Identificar digest/runtime e testar TLS/Basic; sem troca automática                     |
| Docker/Compose | Docker29.8.2/Compose5.5.1 relatados anteriormente                                   | São versões do host, não instaladores embutidos no projeto; nova coleta pendente        |

Não se afirma reprodução byte a byte: imagens base ainda flutuam e o lock não contém hashes de distribuição. A melhoria congela a resolução Python atualmente testada, sem inventar versão da AWS. Toda dependência nova deve responder por que precisa, onde roda, como é versionada/instalada/testada e como outro integrante reproduz. Bibliotecas de runner têm ambiente separado das da API.

## 8. Frontend para evolução

Preservar scripts clássicos, ordem do HTML e tokens. [PROJECT-STRUCTURE.md](PROJECT-STRUCTURE.md) mapeia navigation/page views/stores/forms/dialogs/helpers. Stores distinguem local/remote; sessão e negócio são autoridade do servidor. Não duplicar a regra da API em cada tela, nem inserir token técnico em config pública.

A revisão anterior já melhorou listener, templates e helpers. Repetir uma “limpeza geral” agora elevaria o risco sem benefício medido. Arquivos grandes/CSS histórico ficam na dívida para extrações por área, com regressão. Nesta rodada nenhum arquivo do app é redesenhado.

## 9. Backend para evolução

Router/modelo/regra e teste por área; configuração em `settings.py`; queries parametrizadas e contrato de dinheiro/versão/importação preservados. Novo módulo Python copiado pelo Dockerfile só entra em uso se importado. Estado de negócio deve ser persistente; dict em memória não é fila ou histórico confiável entre workers/restarts.

Não criar framework interno, plugins, worker ou API genérica de execução de código. Contratos novos precisam de autorização, limites, erro sanitizado e testes de isolamento; score futuro não aceita workspace/papel do navegador como autoridade.

## 10. Banco para evolução

Migrations001–011 e 27 tabelas incluindo controle são a baseline relatada; nenhuma nova migration é necessária para documentação/protótipo. `db:status` é leitura; suites SQL usam banco descartável. Role runtime foi observada como superuser: inventariar grants e ensaiar separação em destino isolado antes de mudar privilégios.

Não criar campos de score antes dos critérios. Se persistência/histórico forem necessários, propor migration com workspace, fonte, versão e integridade; validar concorrência/upgrade e rollback de código compatível. Não usar planilha para substituir PostgreSQL das contas/CRM.

## 11. n8n para evolução

[n8n-workflows/README.md](../n8n-workflows/README.md) contém os sete contratos/exportações, estado e promoção. Nome, objetivo, trigger, input, output, dependências, serviço e status são obrigatórios. Classificações: PROD homologado; DEV; TEST; EXPERIMENTAL; LEGACY. OPS e ARCHIVE existentes têm significado operacional/histórico e não devem ser apagados por padronização estética.

Nenhum export da pasta `producao/` é promovido só pelo nome. Exports ficam inativos, sem credentials/pinData. Antes de renomear nós, atualizar todas as conexões/expressões que os referenciem. Diferença entre sete exports e inventário histórico24/8ativos/3arquivados continua pendente de reconciliação; não tocar em workflow incerto.

## 12. WhatsApp futuro

Arquitetura e campos existentes estão em [BASE-WHATSAPP.md](BASE-WHATSAPP.md): WhatsApp → WAHA → adaptador/n8n → API autenticada → PostgreSQL → Caixa, e saída com operação autorizada/estado/reconciliação.

Antes de uso real: resolver canal/workspace no servidor, validar assinatura/token e corpo, IDs externos, dedup por evento/canal, idempotência de gravação/envio, ACK fora de ordem, retry com conciliação, mídia privada, auditoria e segredo por finalidade. ACK só após commit; timeout de envio pode ser estado incerto, não autorização para reenviar.

Container running ≠ sessão conectada. Chip, pareamento e A12/A13 continuam bloqueios. Não ativar legado, enviar mensagem, exibir QR ou ligar cliente real. A seção Integrações de Configurações é o ponto futuro para saúde/conexão de Canais; página dedicada só se volume de canais exigir, após protótipo/aceite.

## 13. Multi-MEI

Modelo atual possui workspace e catálogo, mas estoque é tratado nos fluxos de produtos/vendas; exemplos do app privilegiam comércio. Salão/manutenção precisam de serviços sem baixa física, agenda/duração e termos adequados. Essas capacidades não estão implementadas só porque há nome de serviço na UI.

Evoluir por configuração simples de negócio/capacidades e tipo produto/serviço/misto, depois de requisito e protótipo. Preservar contratos/estoque existentes até existir migração e teste. Não adicionar sistema de plugins nem adaptar pedido de planilha para todos os segmentos automaticamente.

## 14. Política oficial: protótipo antes de integrar

Ideia → análise → HTML isolado → responsável visualiza → ajustes → aprovação explícita → implementação no app → regressão → publicação por etapa.

Regra detalhada em [prototypes/README.md](../prototypes/README.md). Nova feature visual grande não entra em navegação/CSS global antes desse gate. Protótipo não usa dados reais, stores, banco ou API e não promete integração. Correções funcionais/acessibilidade da V1 não precisam virar uma feature visual nova.

## 15. Funil / Oportunidades

Recomendação: **página própria em Negócio para a visão de oportunidades + resumo contextual na Caixa futuramente**. A página suporta volume, filtros, priorização e mobile; a Caixa mantém atendimento e mostra razões/ação relacionadas à pessoa, sem carregar um funil completo em cada conversa. Evitar tela somente dentro da Caixa ou duplicar registros independentes em dois módulos.

Protótipo: `prototypes/opportunities.html`, independente, dados fixos de comércio e serviço. Explora busca, filtros, lista/quadro, seleção, razões e linha do tempo, etapa editável em memória, tema e movimento reduzido. Percentuais, temperaturas e histórico são ilustrações manuais; não existe função de score, pesos, thresholds ou probabilidade estatística calibrada. Nada muda a conta/CRM.

Modelo conceitual futuro: oportunidade vinculada a workspace/cliente e, opcionalmente, conversa; etapa comercial separada da temperatura; evidências com fonte/instante e versão de regra, avaliação/data de atualização e origem humana/automatizada. Percentual ausente aparece “Sem avaliação”, não zero/frio. Negócio sem mensagens confiáveis não ganha score de demo.

Pendente do responsável: critérios/pesos, janela temporal, evidências válidas, significado do percentual, permissões/revisão humana, expiração, regra de reabertura e impacto comercial. API/banco/IA só após essas decisões e aprovação do protótipo. Não interpretar “78%” como chance real de compra por parecer plausível.

## 16. Próximas features e releases

Marcos de planejamento, sem promessa de data: V1 candidata → V1.1infra/ambientes → V1.2Oportunidades após protótipo/critérios → V1.3WhatsApp após segurança/homologação → V1.xdemais requisitos do grupo. Prioridades/gates em [ROADMAP.md](../ROADMAP.md).

## 17. Dívida técnica e riscos

Principais pendências observadas: versões flutuantes de imagens, runtime legacy fora do Git em pontos relatados, grants amplos, backup externo/restore real não ensaiado, scripts globais/CSS grandes, transporte repetido, exports≠publicações, APIs auxiliares sem autenticação no contrato antigo e canais ainda não conectados. Cadastro aberto não verifica e-mail; o Basic compartilhado continua provisório.

Recuperação e onboarding acompanhados pelo professor continuam adiados. Rotação de chave exposta anteriormente permanece **NÃO CONFIRMADA**; não reutilizá-la. Nenhum desses riscos é resolvido apenas escrevendo este plano.

## 18. Ordem recomendada e aceite

1. Conferir contas/isolamento e testes finais da baseline; registrar resultados em [QA](QA.md).
2. Revisar este PR sem publicar automaticamente. Artefatos de protótipo são para decisão, não deploy do app.
3. Fazer leitura dirigida de runtime n8n/API/runner, confirmar mecanismo necessário e executar o teste fictício por HTTP. Aprovar uma mudança de runtime separada somente se necessária.
4. Homologar dependências/imagens e reprodução por outro integrante; confirmar backup externo/restore isolado.
5. Apresentar/ajustar o protótipo e receber critérios de score; só então desenhar contrato e plano de integração.
6. Resolver A12/A13 e homologar WhatsApp isoladamente antes de atendimento real.

Para cada evidência usar TESTADO (execução descrita), VALIDADO (conferência definida), INFERIDO (hipótese), NÃO TESTADO ou BLOQUEADO. CI testa o SHA; recibo identifica runtime; aceite humano confirma uso. O resultado final não deve afirmar execução n8n/AWS sem essa evidência.
