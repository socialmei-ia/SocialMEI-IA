# SocialMEI.IA — Future Readiness Review

Revisão de 14/10/2026, America/Fortaleza. Objetivo: incorporar a limpeza revisada e preparar manutenção, sem redesign, novas funcionalidades ou alterações de produção.

## 1. Baseline

**BASELINE BEFORE FUTURE-READINESS REVIEW**

- Checkout encontrado: `feat/spreadsheet-orders-api`, `fef6cc50ea6039696d3e5d47c9dee91b81b9cc15`, limpo. Essa feature não entrou nesta revisão.
- `main` remota conferida explicitamente: `92d4c20a106d330a24452f6cca969c79762c15b3`. Branch de trabalho: `refactor/future-ready-foundation`, criada dessa main limpa.
- Inventário inicial: 217 arquivos versionados; textos, scripts/configurações e metadados de assets confrontados com a revisão anterior. Revisão direcionada dos contratos, módulos alterados, configuração, banco e infraestrutura. Não se afirma auditoria manual linha por linha de todos os arquivos.
- Baseline local: 64 testes Node, 130 testes Python com PostgreSQL 16 descartável e formatação passaram. Antes da mudança foram capturados 44 estados de 11 telas, dois temas e duas larguras, com dados fictícios e relógio fixo.
- A limpeza do PR #42, branch `refactor/code-maintainability` em `79ffd38954f401a10aa654e8c2a3a26b5fc5a1df`, estava fora da main. Seus cinco commits foram incorporados por merge nesta branch; CI anterior #133 aprovado. O novo CI deve validar a composição final.
- `PROJECT-AUDIT.md`, `TEST-REPORT.md` e `NEXT-STEPS.md` não estão no checkout. Foram usados os relatórios versionados existentes, sem inventar conteúdo dos anexos ausentes.

## 2. Ambientes

O [mapa canônico](docs/ENVIRONMENTS.md) diferencia demonstração estática, desenvolvimento Docker, CI, Pages condicionado à habilitação, piloto team e pilha legada na AWS. Staging é proposta, sem instalação comprovada. Banco, URLs, config, segredo, teste e forma de publicação estão ligados a cada ambiente.

Existem dois projetos na mesma AWS: team e legado. Não transformar essa separação em uma nova estrutura de pastas de produção. O checkout local deste chat e seus containers de teste não são o servidor AWS.

## 3. Arquitetura atual

Frontend estático → stores → gateway → FastAPI → PostgreSQL no modo remoto. No modo local, os stores usam estado do navegador. Sessões e negócio são resolvidos no servidor. n8n/WAHA e API auxiliar permanecem integrações separadas, com limites de homologação.

`settings.py` passa a concentrar a leitura de ambiente da API. Não foi criado framework interno, container de injeção, sistema de plugins ou camada repository/service para cada operação. Contratos HTTP e a montagem dos routers permanecem iguais.

## 4. Estrutura do repositório

O [mapa por pasta/funcionalidade](docs/PROJECT-STRUCTURE.md) classifica atual, compatibilidade, legado, teste, protótipo, infra, asset, documentação e backup privado. As entradas de compatibilidade são redirecionamentos úteis, não cópias do app. Não houve arquivo removido, movido ou renomeado: faltou evidência para descartar assets, seletores dinâmicos ou arquivos históricos necessários.

`.gitignore` passou a ignorar backups `*.bak`, `*.bak-*`, resíduos `*.orig` e `*.rej`; isso não apaga arquivos nem retira algo já versionado. Arquivos privados de produção continuam fora do checkout e não foram examinados.

## 5. Frontend

A limpeza incorporada reduz o listener principal de `app.js`, nomeia composição local do Assistente, compartilha mensagem inicial da Caixa e seleção de período, e torna templates/estados menores mais legíveis. O relatório [CODE-MAINTAINABILITY-REVIEW.md](CODE-MAINTAINABILITY-REVIEW.md) registra os antes/depois.

Permanecem scripts clássicos e globais dependentes de ordem. A nova documentação diferencia UI, stores/transporte, estado local, snapshots remotos e fixtures. Não houve renomeação de storage keys ou criação de um API client genérico que mudasse importação/replay de quatro módulos distintos.

## 6. Backend

`settings.py` reúne DSN/componentes PostgreSQL, modo/origem de auth, CORS, defaults de workspace e token n8n. Os pontos de entrada anteriores continuam acessíveis: `database.database_url`, `database.shared_data_enabled`, `account_auth.enabled/origin` e `shared_data.workspace_slug/name` preservam os contratos dos consumidores.

Não há cache de configuração ou impressão de valores privados. CORS continua definido na inicialização do app; defaults consultados durante uma requisição mantêm a semântica anterior. Flag de auth mal escrita continua ativando o bloqueio e produzindo 503 sanitizado. A identidade da sessão continua tendo precedência sobre o workspace do ambiente. O OpenAPI completo foi comparado com a main e permaneceu idêntico: **53 operações**, com os mesmos modelos.

## 7. Banco de dados

As migrations 001–011 permanecem byte a byte iguais à main. Há 26 tabelas funcionais declaradas pelas migrations, mais `schema_migrations`; são grupos de clientes/conversas legadas, workspaces/associações, CRM/importações/operações/transferência, canais/eventos e contas/auditoria. A migration 011 protege sete vínculos por negócio; não é RLS.

O bug preparatório corrigido foi no **executor local**: `npm run db:status` não cria mais schema/tabela para poder consultar versões. Apenas `db:migrate`, explicitamente solicitado, inicializa o controle. Nenhuma migration nova, schema/grant de produção ou registro de negócio foi alterado.

## 8. n8n

Os sete exports continuam com nomes classificados, grafos e parâmetros preservados, todos inativos. O guia passou a declarar entrada, saída, integração, estado e critérios de promoção/rollback. Não foi feita importação, renomeação ou publicação no n8n vivo.

24 workflows/oito ativos/três arquivados são uma coleta anterior, não contagem reconfirmada. A relação export × versão publicada continua pendente. A12/A13 (identidade, autorização e idempotência) são P0 condicionais para atendimento real. O protótipo de estoque e o executor Python discutidos em outros PRs não foram adicionados por esta manutenção.

## 9. Docker / Infra

Compose, Dockerfiles, Caddyfiles, redes, portas, volumes e políticas de reinício não mudaram. Atualizar team-gateway, team-api e python-api legado são operações distintas. O guia alerta que os workflows manuais usam Compose genérico e não publicam corretamente team por mera escolha do environment.

Versões flutuantes (`latest`, dependências Python sem pin e tags major/minor) permanecem dívida documentada. Não foram fixadas a uma versão inferida de memória ou trocadas por uma imagem não homologada. O registry não prova a versão que roda na AWS.

## 10. Configuração e secrets

O mapa distingue `.env.development`, `.env.team`, `.env` legado, `frontend/config.js` e o diretório privado de Caddy. O conteúdo do `config.js` team também chega ao navegador: um mount privado não autoriza embutir um segredo naquele JavaScript.

Nenhuma senha, token, hash de senha, cookie, chave privada ou QR foi solicitado ou publicado. O acesso Basic compartilhado da equipe, confirmado pelo responsável, não foi removido, recriado ou colocado no Git. Rotação/revogação de chaves expostas no passado continua pendência, sem afirmar que a limpeza do histórico corrente a resolve.

## 11. Testes

Os resultados finais e comandos estão em [docs/QA.md](docs/QA.md). Os testes novos exercitam comportamento observável: configuração ausente, precedência/escape de DSN, auth inválida, workspace da sessão, CORS, leitura dinâmica e status de migrations sem escrita.

| Camada                                 | Evidência desta revisão                                                                                    |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Node                                   | 71 contratos passaram: 64 da baseline, três da limpeza e quatro do executor de migrations                  |
| Python/API + PostgreSQL 16 descartável | 140 testes passaram, sem skips: 130 existentes e dez de configuração                                       |
| Operação/backup/admin                  | 19 passaram; cinco de gateway são opt-in no comando padrão                                                 |
| Gateway Caddy isolado                  | Cinco testes passaram em execução separada                                                                 |
| HTTP/OpenAPI                           | Contrato completo idêntico à main; nenhum endpoint/modelo adicionado                                       |
| Navegador funcional                    | 88 estados e 21 fluxos passaram                                                                            |
| Temas / estabilidade                   | 825 estados de layout/tema e 167 de botões passaram, sem pageerror/404 local                               |
| Visual Home / Financeiro               | 22 estados de cada módulo passaram, incluindo teclado, touch e reduced motion                              |
| Configurações                          | 990 estados passaram: salvar, temas, teclado e modos local/remoto simulado                                 |
| HTTPS e Basic                          | Quatro módulos conectados, escrita autenticada e API anônima recusada em containers próprios               |
| Capturas antes/depois                  | 44 pares: 39 idênticos, cinco com 6–40 pixels residuais de rasterização, sem mudança de geometria/conteúdo |
| AWS / integrações externas             | **NÃO CONFIRMADAS nesta rodada**; sem acesso SSH ou chamadas aos webhooks                                  |

Não usar `TEST_DATABASE_URL` com um banco de trabalho: as fixtures limpam seus próprios dados. Scripts auxiliares de browser também são chamados pela suite principal; não executar arquivos exportadores como se fossem CLIs independentes.

O executor local foi exercitado também contra um banco novo descartável: `status` listou 11 pendências sem criar o schema; `migrate` instalou 001–011; nova consulta leu as versões. O banco exclusivo desse teste foi removido ao final. O setup e a configuração Compose foram validados; isso não é startup completo de n8n/WAHA nem teste no Windows.

Tentativas iniciais em paralelo falharam durante inicialização de algumas suites; repetições isoladas passaram sem relaxar expectativas. A causa pontual não foi isolada e fica registrada em [QA](docs/QA.md). O proxy interno e o Chromium do ambiente também exigiram adaptação de execução local; não houve alteração da configuração de produção para fazer os testes passarem.

## 12. CI / GitHub

O workflow existente já cobre Node, formatação, API/SQL, backup, gateway, stack team descartável com restore isolado, browser, temas e contas. Os testes adicionados seguem os globs atuais, sem duplicar jobs. A suite HTTPS passou a aceitar `CHROMIUM_EXECUTABLE`, como as demais, e exibir apenas o status HTTP se o gateway não subir.

CODEOWNERS e template de PR existem. O template agora pede ambiente, contrato e separação entre CI e evidência de deploy. Proteção de branch, environments/reviewers e secrets administrativos são **NÃO CONFIRMADOS**; não foram alterados. PR/CI final são registrados no GitHub; um resultado de execução anterior não é o resultado do SHA final.

## 13. Desenvolvimento local

O caminho existente é Git/Node/Docker → `npm ci` → `npm run setup` → `npm run dev` → `npm run db:migrate` para gestão compartilhada local. Abrir o servidor estático não cria uma API remota nem muda automaticamente o modo dos stores. É necessário configurar explicitamente o modo local ou uma API de desenvolvimento.

Setup/configuração, testes e integrações isoladas são evidências separadas de iniciar toda a stack n8n/WAHA no notebook de cada integrante. Não foi declarado como testado um onboarding completo do Windows ou de uma stack escolar remota sem execução correspondente. [ONBOARDING.md](docs/ONBOARDING.md) mantém os blocos PowerShell existentes.

## 14. Observabilidade

`/health` verifica processo; `/health/db` consulta estrutura do CRM e, quando ativada, auth, sem escrever dados. `channels.schema=prepared` significa estrutura disponível; `connection=not_checked` não afirma conexão WhatsApp. A limpeza só agrupou as queries de saúde por capacidade.

Logs de operação não devem conter cabeçalhos, payload completo, DSN ou material de auth. Para debug, registrar serviço, versão da imagem, rota/ação, status e erro sanitizado. Não foi adicionado middleware de logging de corpos ou um sistema externo de observabilidade sem necessidade.

## 15. Documentação

`docs/ENVIRONMENTS.md` responde onde executar e quais dados/credenciais pertencem ao alvo. `docs/PROJECT-STRUCTURE.md` responde onde editar e como estender. Este relatório registra decisões e evidências; não é uma segunda cópia de todos os guias.

README/arquitetura/desenvolvimento apontam para esses mapas. ROADMAP foi enxugado para remover afirmações superadas sobre ausência de API, testes SQL, migrations ou isolamento. Guias históricos foram preservados com indicação clara de seu contexto.

## 16. Simplificações realizadas

- Incorporados os cinco commits da limpeza já testada, sem reimplementar a mesma revisão.
- Leitura de configuração movida de seis módulos de API para `settings.py`.
- Auth conserva tratamento distinto para desativada, ativada e inválida; sem helper booleano que reabra acesso por erro de digitação.
- `db:status` tornou-se consulta; inicialização permanece no comando de migração.
- Quatro declarações CSS exatamente redundantes foram retiradas pela limpeza anterior, mantendo as posteriores na cascata.
- Mapas por área/ambiente substituem a necessidade de adivinhar qual Compose ou script alterar.

## 17. Mudanças para facilitar manutenção

Novos endpoints têm router/modelo/validação/operação próximos da área, configuração num ponto conhecido e teste correspondente. Novas telas seguem navegação/estado/renderização existentes com seletor estável. Não se cria uma abstração apenas para uma mudança prevista.

As convenções continuam simples: nomes técnicos novos em inglês, UI em português, comentários curtos, formatação legível, commits por responsabilidade e contratos antigos preservados. Nenhum emoji foi adicionado à documentação técnica, logs ou commits.

## 18. Dívida técnica restante

- Arquivos grandes, globais e ordem de scripts; reduzir por responsabilidade com testes, sem migração de framework automática.
- Transporte parcialmente repetido nos stores; abstrair somente depois de comparar erros, replay, importação e auth.
- Cascata CSS extensa com valores/overrides históricos; revisar componentes individualmente com comparação visual.
- Role da API observada como superuser; inventário de grants e separação operacional pendentes.
- Fixação/homologação de dependências e imagens, cobertura/cópia externa de backups e ensaios reais de restore.
- Atendimento externo sem contrato multiempresa/idempotência homologado; exports incompletos preservados.

## 19. Pontos ainda frágeis

O Compose de desenvolvimento ainda exige migrations explícitas e configuração pública dos stores; n8n/WAHA opcionais não equivalem a integrações prontas. `config.js` versionado mantém a URL histórica de leitura n8n; testes bloqueiam rede externa e team usa configuração própria. Não trocar esse comportamento silenciosamente numa limpeza.

Deploys recentes mantêm API e gateway com SHAs diferentes. Um script antigo com snapshot pré-deploy pode bloquear corretamente uma segunda publicação. Não reaplicar ou reverter por tentativa: comparar com a publicação registrada. Backups locais ao host não protegem sozinhos contra perda da instância.

## 20. Como adicionar uma nova feature

O [guia na estrutura](docs/PROJECT-STRUCTURE.md#como-adicionar-uma-feature) liga contrato → migration se necessária → backend → store → UI → testes → documentação → PR. Integração de canal adiciona ainda autorização/identidade/idempotência e homologação isolada. O deploy só acontece com alvo e rollback concretos.

## 21. Preparação para próximas mudanças visuais

O [design system](docs/DESIGN-SYSTEM.md) permanece a fonte dos tokens e da linguagem aprovada. Seletores de comportamento e classes visuais devem se separar ao tocar um componente, quando houver benefício; não renomear todos os seletores agora.

A revisão compara Home, Visão Geral, Caixa, Clientes, Produtos, Vendas, Financeiro, Relatórios, Assistente, Automações e Configurações, em claro/escuro e desktop/mobile. Não houve uma nova direção de arte, novos assets ou mudança de conteúdo do produto.

## 22. Preparação conceitual para Customer Score

O contexto provável é Clientes; regra autorizada no backend; modelo/endpoint específico quando os critérios existirem; persistência por workspace apenas se houver necessidade de histórico; testes de regra e isolamento antes da UI. Não calcular a partir de mensagens demo ou tratar tabelas de canal preparadas como integração confiável.

Nenhuma fórmula, campo, peso, score, tabela ou migration foi inventado. A definição funcional pertence à próxima etapa, depois das decisões do grupo.
