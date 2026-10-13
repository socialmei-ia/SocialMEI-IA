# SocialMEI.IA — Stable Baseline Review

## Resumo

Rodada de 13/10/2026 (America/Fortaleza), branch `stabilization/project-baseline`. **Base do código preparada para revisão; estabilidade operacional completa BLOQUEADA por falta de acesso direto à AWS/n8n.** Não afirmar deploy, banco vivo atualizado ou atendimento homologado.

**BASELINE BEFORE STABILIZATION:** branch `main`, SHA `b27e75d01bdadef33707123347cab5272ee05040`, checkout limpo; último commit é o merge do PR #34. CI dessa fonte aprovado: [Repository checks](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/38417891364). É resultado do baseline, não da nova branch.

Fontes: `docs/REMEDIATION-STATUS.md`, `docs/LIVE-ENVIRONMENT-INVENTORY.md` e contexto operacional fornecido pelo responsável. `PROJECT-AUDIT.md`, `TEST-REPORT.md` e `NEXT-STEPS.md` não encontrados neste checkout; sua ausência não foi ocultada. Conferida a evolução de 28 commits desde o snapshot `65be488…`, sem reiniciar a auditoria anterior. Inventariados 190 arquivos rastreados antes das mudanças; mantidos assets e arquivos de uso incerto.

Classificação: frontend/API/migrations/team são atuais; atendimento SQL/n8n genérico e scripts de acesso n8n são legados distintos; Instagram/rotina agendada são experimentais; testes/fixtures são isolados; Pages é demonstração intencional. Não removidos arquivos para reduzir contagem artificialmente.

## Banco de dados

**TESTADO:** PostgreSQL 17.11 descartável local, executado por usuário sem root, socket privado e nenhum listener TCP. Pacotes Debian extraídos fora do repositório e conferidos por SHA256; nenhuma versão/configuração do servidor alterada. O CI deve validar PostgreSQL 16, alvo do Compose team.

O baseline passou em 119 testes de API, incluindo autenticação e duas identidades/workspaces. Login usa Argon2id; sessões/convites guardam somente digest, com expiração/revogação e consumo de convite transacional. Workspaces, membros e estrutura de atendimento existentes foram preservados. Não há recuperação por e-mail nem persistência remota de notas/rascunhos/regras.

**REPRODUZIDO:** sete relacionamentos de CRM/importação aceitam IDs de outro workspace por SQL direto no schema 001–010. Não foi reproduzido vazamento pela API: as consultas/vínculos da aplicação são filtrados e os testes de duas identidades passam. O problema é integridade referencial para outros escritores SQL.

**CORRIGIDO em migration preparada:** 011 adiciona sete FKs compostas e três índices únicos; preserva links opcionais, snapshots e exclusão lógica. Linhas existentes inconsistentes fazem o upgrade abortar, sem correção/descarte automático. Testados vínculo válido/inválido, exclusão de cliente preservando workspace/histórico, replay e rollback de upgrade incompatível. Isso não é RLS nem resolve o atendimento legado.

**NÃO CONFIRMADO nesta rodada:** schema, constraints, grants e dados da AWS. O responsável informou migrations 001–010 e 27 tabelas; isso é evidência anterior. Não se concluiu que contas/banco estão vazios pelas contagens de CRM zeradas.

## Acesso da equipe ao banco

**DEFINIDO/PREPARADO:** `docs/TEAM-DATABASE-ACCESS.md` e `database/team-readonly-access.sql`. Um perfil NOLOGIN de consulta, logins individuais provisionados privadamente pelo responsável, sem auth/segredos/escrita/default grants. Recusa perfil preexistente administrativo. Grants antigos podem ser mais amplos e exigem auditoria; o script não os revoga.

MEIs usam API/sessão, não SQL. Desenvolvedores usam banco local. O perfil interno pode ler múltiplos negócios nas tabelas autorizadas e não deve ser entregue a clientes. PgAdmin/VPN/bastion/túnel exige caminho real para a rede team: não há bind confirmado em `127.0.0.1:5432`. Não aberto 5432; nenhum login, senha, regra AWS ou grupo Docker concedido na produção. Aplicação pendente de inventário/backup de dados e roles.

## Backend

**REVISADO:** 53 operações FastAPI inventariadas em `docs/API-ENDPOINTS.md`, com método, path, auth, input/output, área de banco e consumidor. Autorização opt-in resolve o workspace pela sessão, CSRF/Origin para escrita, administração global separada e Bearer de leitura team. Desativar auth reabre o modo compartilhado configurado; não fazê-lo com MEIs reais.

**TESTADO:** 126 testes Python da API, zero falhas/skips no banco descartável final. Cobertura inclui 200/201/204/400/401/403/404/409/422/429/503 conforme o contrato, concorrência, idempotência, importação, estoque, soft delete e isolamento. Não se provoca 500 em produção. Readiness sanitiza falhas e diferencia schema de canais de conexão real. Não houve alteração de endpoint/schema de resposta para corrigir o frontend.

## Frontend

**REPRODUZIDO/CORRIGIDO:** conclusão tardia de gravação fechava um novo formulário de edição já aberto. O teste de Vendas falhou duas vezes no baseline; atraso controlado reproduziu o fechamento. A conclusão agora verifica a identidade da edição ou a geração do modal antes de fechá-lo, preservando feedback. Mesma proteção aplicada aos quatro módulos remotos; sem alterar CRUD, design ou regras de negócio.

**TESTADO:** suíte existente com 88 estados e 16 fluxos; conta remota controlada/demo, convite, administração, CRUD, importações, falha/conflito/replay, temas, rascunhos, modais e navegação. A01/A02: 36 estados de menu e 936 colunas em nove resoluções. Matrix adicional: 675 combinações (12 entradas de navegação, incluindo alias Meu negócio → Visão Geral, e landing/auth/onboarding × nove resoluções × cinco modos de tema). Sem overflow global, pageerror ou 404 local nesse teste; movimento reduzido utilizado.

HTML: 170 botões estáticos no app, sete em admin, três na transferência, 24 no DevHub; sem IDs duplicados ou labels `for` sem destino nas seis páginas. A matriz inspecionou 177 estados distintos de botões visíveis e seus nomes/disabled/datasets. Isso é inventário/acessibilidade, não alegação de que toda combinação de botão dinâmico e permissão foi clicada. Ações principais são cobertas pelos fluxos; integração HTTPS/gateway e QA autenticado na AWS permanecem evidências separadas. Nenhum bug visual corrigido sem reprodução; não feito redesign.

## n8n

**REVISADO/ORGANIZADO no Git:** sete exports, todos inativos e sem referência de credencial da instância. Nomes classificados como OPS/TEST/DEV/LEGACY/ARCHIVE; grafos, parâmetros, URLs e triggers preservados por comparação JSON. Não foi inventado processamento para ramos desconectados nem URL para rotina sem destino.

**BLOQUEADO no runtime:** inventário histórico informa 24 workflows, oito ativos e três arquivados, em n8n 2.40.5. IDs e classificação estão no inventário vivo; versão publicada/equivalência, execução recente e autorização não foram reconfirmadas. Nenhum webhook foi chamado ou workflow vivo exportado/renomeado/publicado. A12/A13 continuam P0 antes de atendimento real; Google Sheets pausado. Backup team não comprova preservação conjunta do banco/volume/chave original do n8n.

## WAHA

Histórico: 2026.9.2, CORE/WEBJS, sessão default aguardando QR. **NÃO CONFIRMADO agora.** Sem QR exibido, pareamento, mensagens, restart, webhook ou troca de engine. GOWS no Git não é evidência de WEBJS homologado nem autorização para upgrade. Chip e validação do adaptador permanecem dependências.

## Docker / Infra

Pilha team separada da dev/legada; banco/API não publicam portas no Compose team. Revisados Dockerfiles, dependências, volumes, healthchecks, overlays e scripts de backup; preservados nomes/projetos/mounts. Nada alterado na VPS. Tags flutuantes n8n/WAHA/pgAdmin continuam dívida: não fixar combinação por memória ou atualizar serviços sem homologação.

Docker local indisponível e usuário sem privilégio para iniciar o daemon; testes reais de gateway/HTTPS/stack local BLOQUEADOS. Configuração Compose e gateway devem ser validadas no CI. O workflow manual de produção genérico não representa o deploy team aprovado e não foi acionado.

Backup antes da alteração do banco descartável: dump privado de 100999 bytes, SHA256 `1c83129392d6e0375c821071f9b715550b7afb1caf9cf35fc88c164bd97a151e`. Restore integral desse dump em **outro banco descartável** passou; readiness e upgrade 10→11 conferidos. Essa evidência não é restore de backup AWS nem cobertura de n8n/WAHA/Caddy/roles. Nenhum dado externo lido/restaurado. Cron/último sucesso/retensão/cópia externa da VPS não reconfirmados.

## GitHub

Branch própria, sem force push/reset/clean. Código, docs e CI desta rodada serão apresentados em PR; o link e o SHA final ficam no PR e na resposta de entrega. Não realizar merge enquanto os checks não estiverem verdes; este PR não equivale a deploy AWS. `main` estava sem proteção no baseline: recomendar PR obrigatório, checks validate/browser e revisão; nenhuma configuração administrativa alterada.

## Bugs encontrados

1. Fechamento de editor novo por conclusão de edição anterior: CORRIGIDO e reproduzido com atraso controlado.
2. Mesma classe de fechamento tardio na criação remota: CORRIGIDO e coberto por testes de ownership.
3. Sete vínculos SQL sem composição de workspace no CRM/importação: CORRIGIDO na migration preparada e testada; AWS NÃO APLICADA.
4. README descrevia API auxiliar e negava workflows manuais de deploy existentes: documentação CORRIGIDA, com separação de modos/pilhas.
5. Nomes genéricos de exports e falta de grupo equipe no guia: ORGANIZADO no Git, sem alteração viva.

Não identificado incidente de vazamento nem vínculo inválido na produção; falta de acesso não é prova de ausência ou presença de problema.

## Correções realizadas

Mudanças pontuais nos handlers de conclusão, regressão determinística, migration incremental, perfil de leitura separado, matriz de layout/temas no CI e documentação de contratos/limites. Sem refatoração massiva, nova função de produto, troca de framework, abertura de cadastro, remoção de Basic ou ativação de canais.

## Arquivos alterados

- `frontend/scripts/dialogs.js`, `record-editor.js`: proteção de conclusão assíncrona.
- `tests/editor-dialog.test.cjs`, `sales-browser.cjs`, `stability-browser.cjs`, workflow repository-checks: regressões.
- Migration 011, perfil SQL e `python-service/test_workspace_integrity.py`: integridade/acesso interno.
- Sete exports e README n8n: nomes/classificação, sem grafos alterados.
- README, ARCHITECTURE, CHANGELOG, ROADMAP e guias de acesso/banco/endpoint/revisão: estado real e gates operacionais.
- Nenhum arquivo removido/movido; migrations 001–010, assets e configuração privada preservados.

## Migrations

011 preparada e aplicada **somente aos bancos descartáveis de teste**. Não edita 001–010, não cria workspace/conta, não limpa dados, não entrega senha. Executar na AWS apenas após backup, inventário sanitizado de links, janela de manutenção e migrador transacional. Se um vínculo for incompatível, parar para decisão do responsável; não apagar linhas. Locks limitados a cinco segundos e statements a 60 segundos. Índices normais exigem janela/volume compatível; não prometer upgrade sem indisponibilidade.

## Testes

Resultados locais finais: **57 Node + 126 Python API + 19 operação passaram**, zero falhas nesses conjuntos; cinco gateway ignorados por falta de Docker. Total registrado unit/integration: 207, 202 passes, cinco skips. Matriz/browser e restore são evidências adicionais, não somadas artificialmente às contagens de unittest/Node.

Browser existente: 88 estados/16 fluxos PASS; matrix: 675 estados/177 estados de botão PASS; auditoria A01/A02: 36 menus/936 colunas PASS. Formatter, sintaxe shell, diff, JSON, IDs/labels/recursos e comparação dos grafos verificados. Python local: PostgreSQL 17.11; CI alvo 16. A execução da nova branch deve ser consultada no PR, não substituir pelo CI do baseline.

## Limitações restantes

- SSH/credenciais/TCP AWS não configurados: nenhum inventário vivo novo, deploy ou backup externo.
- n8n/WAHA/grants/firewall/volumes/backups externos ainda pendentes; não declarar base operacional completa.
- Gateway HTTPS/Basic real depende de Docker/CI e homologação AWS; navegador local usa fixtures/APIs controladas.
- Relatórios originais de auditoria externos ausentes; fontes versionadas/contexto usados, mantendo o limite.
- Não certificadas todas as combinações dinâmicas de botão/teclado/permissão, grandes volumes nem integração externa. Sem baseline visual novo de produção aprovado.

## Dívida técnica

Globais e controladores/CSS grandes; listagens CRM sem paginação humana; storage local de notas/regras; isolamento SQL por aplicação sem RLS; runtime API com usuário/grants a inventariar; dependências/imagens flutuantes; backup parcial de infraestrutura; integração legada sem contrato tenant/idempotência homologado. Planejar pequenos PRs com regressão, não limpar overrides/renomear contratos em massa.

## Próxima fase visual

Liberar somente depois da revisão do PR e do gate operacional do responsável. Preservar dados, autenticação e navegação; Mobbin/21st.dev poderão orientar a próxima rodada autorizada. Nenhuma credencial 21st anterior foi reutilizada e nenhum framework foi introduzido.

## Preparação para calculadora de probabilidade

Local sugerido: perfil/drawer do cliente, com resumo opcional em uma lista. Entradas existentes possíveis: histórico autorizado de vendas, frequência/recência, situação financeira e interações quando o atendimento for realmente integrado. Qualquer uso exige critérios fornecidos e validação do responsável; não estimar percentual com dados demonstrativos.

Ainda faltam critérios/pesos/formula, tratamento de falta de dados, período e necessidade de histórico. Se o cálculo for determinístico sob demanda, não pressupor tabela nova; se houver histórico, pode exigir estrutura com workspace/cliente, versão do modelo, entradas/referência temporal, resultado e autor/data. Decidir depois. Lógica no backend, tenant resolvido pela sessão, saída explicável; UI apenas apresenta. **Nenhuma calculadora, campo, fórmula, peso ou endpoint implementado.**
