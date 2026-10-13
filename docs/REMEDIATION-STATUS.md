# Remediation Status

Rodada de estabilização, 12/10/2026 (America/Fortaleza). Escopo autorizado: Etapa 0 somente leitura e correção local de A01/A02. Próximos itens são preparação, não autorização de execução.

## Baseline

- `main` conferido no GitHub: `65be4880a41bec5903b7c3c896ff14da74c4f1d7`, igual ao SHA auditado.
- Branch inicial `feat/visual-contas`, HEAD `b19c447a04d5de32d11c426b7251b3d20f6f2391`, sem mudanças não commitadas e árvore idêntica ao snapshot auditado.
- Branch desta rodada: `fix/audit-ui-regressions`, criada no SHA auditado. Nenhum reset, clean, force push ou atualização destrutiva.
- Fontes atuais da auditoria, relatório de testes e plano foram lidas. Não houve mudança de `main` que exigisse reauditar evidências.
- Antes das correções, CSS e renderer auditados foram preservados fora do checkout. A captura `before` serve esses dois arquivos diretamente do SHA auditado; não troca os arquivos do projeto.

## Etapa 0

**PARTIAL**, com runtime interno **BLOCKED**. Detalhes em [LIVE-ENVIRONMENT-INVENTORY.md](LIVE-ENVIRONMENT-INVENTORY.md).

Validados: estado do Git, SHA/árvore de `main`, fontes atuais e HEAD público sanitizado da API (401/Basic). A tentativa HEAD da raiz expirou; isso não comprova que o site esteja indisponível.

Sem acesso autenticado à VPS: Docker/Compose/digests/versões/mounts/networks efetivos; n8n vivo e suas execuções; schema/grants/contagens reais; versão e sessão WAHA; logs; cron/backups atuais continuam BLOCKED. Nenhuma configuração, backup ou consulta de escrita foi executada. Tags do Git não foram apresentadas como versões instaladas; confirmações históricas não foram contadas como nova coleta.

Conforme a regra desta rodada, o bloqueio permite somente A01/A02 locais e não autoriza mudanças de banco/n8n/infra/deploy.

## A01

### Evidência antes

O selector `.utility-menu > .btn` tinha a mesma especificidade que `.btn.ib`, mas aparecia antes. A regra posterior impunha largura 44 px. O rótulo da busca em `::after` quebrava em três linhas; medida 44 × 78,75 px. O indicador de notificações ficava antes do texto, sem alinhamento ao final da linha.

### Mudança

Corrigida a regra original para os botões `.btn.ib` diretamente pertencentes ao menu ou aos seus dropdowns. Ícones mantêm a largura, pseudo-rótulos usam uma linha/alinhamento à esquerda e o indicador fica por último no flex. Nenhum `!important` novo ou override no final do arquivo. Cores, estrutura e direção visual preservadas.

### Testes e resultado

**PASS:** 36 estados (nove resoluções × Light/Dark/Auto-Light/Auto-Dark); mouse, Enter, Tab para busca e Escape. Busca: 244 × 44 px no menu desktop e 234 × 44 px no mobile. Ícones de 20 px preservados e indicador alinhado à direita. Capturas antes/depois em Light e Dark.

## A02

### Evidência antes

Tooltips absolutos eram relativos a cada coluna, centrados e com `white-space: nowrap`. Nas extremidades ultrapassavam o gráfico/documento mesmo quando transparentes. A regressão dedicada reproduziu overflow em 390/360, além de casos de período/valores mais amplos.

### Mudança

O plot tornou-se o bloco de posicionamento dos tooltips. `clamp()` calcula o centro próximo da coluna e reserva espaço nas bordas; largura máxima limitada ao plot e texto longo pode quebrar sem truncamento. Hover, focus-visible e rótulo de valor permanecem funcionando. Os tooltips não foram removidos nem escondidos globalmente.

A tentativa em CSS com tratamento apenas da primeira/última coluna e contexto mobile deixou dez violações da área do gráfico em 12 meses, em 768/1024 px. Por isso o renderer agora informa somente dois metadados numéricos em custom properties: quantidade e índice de colunas. Todo o posicionamento continua em CSS; não foram adicionados handlers, timers, observers ou cálculos de geometria em JavaScript.

### Testes e resultado

**PASS:** 936 verificações de coluna distribuídas em 144 configurações de gráfico (nove resoluções × Light/Dark × Hoje/7 dias/30 dias/12 meses × dois conjuntos de valores). Todas as colunas, incluindo primeira/central/última, foram focadas e receberam hover. Valores incluem zero, centavos, ordinários e grandes.

Critérios: tooltip visível no teclado/hover; bounds dentro do gráfico; `document.documentElement.scrollWidth <= document.documentElement.clientWidth`; rótulo acessível de faturamento/valor preservado. Zero falha na versão corrigida, zero pageerror e zero erro/warning de console na suíte específica. Reduced motion preservado.

## Regressão e evidências

Comandos locais:

```bash
npm test
npm run format:check
CHROMIUM_EXECUTABLE=/tmp/chromium npm run test:browser
CHROMIUM_EXECUTABLE=/tmp/chromium node tests/audit-ui-browser.cjs
AUDIT_UI_PHASE=before CHROMIUM_EXECUTABLE=/tmp/chromium node tests/audit-ui-browser.cjs
```

`CHROMIUM_EXECUTABLE` identifica o navegador disponível no ambiente do auditor; nos computadores com Playwright instalado, o override é desnecessário. A captura `before` requer o objeto Git do SHA auditado e **deve falhar** ao reproduzir os bugs; não é o modo usado no CI.

| Verificação                        | Resultado                                                                                                                         |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| npm test                           | 51 passaram, 0 falhas, 0 skips                                                                                                    |
| Formatação                         | PASS após finalização dos dois documentos e testes                                                                                |
| Browser existente + regressão nova | 88 estados gerais e 16 fluxos; inclui a regressão dedicada A01/A02                                                                |
| A01/A02 específico                 | 36 estados do menu, 144 configurações/936 colunas do gráfico; 0 falhas, 0 skips                                                   |
| Baseline específico                | 810 checks falharam como esperado: 108 de menu/indicador, 254 de bounds de tooltip e 448 de overflow; não são 810 bugs diferentes |
| Python complementar                | 24 executados passaram; 70 ignorados por ausência de PostgreSQL local; não contados como passes                                   |
| Docker/PostgreSQL vivo             | BLOCKED; não foi feita validação de runtime nem teste de integração na AWS                                                        |
| Diferenças revisadas               | Somente dois arquivos de UI, dois arquivos de teste e os dois documentos autorizados                                              |

Capturas em `test-results/audit-ui/`, ignoradas pelo Git e incluídas no artifact `frontend-regression` do CI quando a suíte é executada:

- `before-tools-light.png` / `after-tools-light.png`.
- `before-tools-dark.png` / `after-tools-dark.png`.
- `before-reports-390-light.png` / `after-reports-390-light.png`.
- `before-reports-390-dark.png` / `after-reports-390-dark.png`.
- `before-reports-360-light.png` / `after-reports-360-light.png`.
- `before-reports-360-dark.png` / `after-reports-360-dark.png`.
- `before-summary.json` / `after-summary.json`: métricas e falhas por cenário.

Capturas usam fixtures de teste, sem clientes/contas reais. Antes/depois foram inspecionados. O CI desta branch deve ser consultado no PR; o sucesso anterior do `main` não é resultado desta mudança. Nenhuma publicação na produção foi feita.

## Próximos itens

READY significa suficientemente definido para preparar/revisar a próxima mudança; **não significa aprovado para implementar**. BLOCKED exige uma dependência ausente. NEEDS PRODUCT DECISION e NEEDS INFRA DECISION indicam decisões a obter antes da implementação.

| Item | Prontidão                                       | Próximo passo / dependência                                                                                                                                                                                                                       |
| ---- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A03  | NEEDS PRODUCT DECISION; inventário real BLOCKED | Decidir precisão/limite de preços/custos e consultar contagens incompatíveis em READ ONLY. Nada foi arredondado, normalizado ou validado de forma diferente.                                                                                      |
| A04  | READY                                           | Origem dos seeds e consumidores mapeada abaixo; definir importação/preservação antes de separar demo e conta real. Nenhum dado foi apagado.                                                                                                       |
| A05  | READY                                           | Preparar PR documental próprio: diferenciar auth opt-in/legado e banco CRM atual em ARCHITECTURE, BANCO-DE-DADOS e SHARED-DATA-API. Nenhum diff desses guias aplicado nesta rodada.                                                               |
| A06  | READY                                           | Proposta própria: verificar schema/auth quando ativada; falta de tabelas auth → diagnóstico de indisponibilidade; separar base de canal preparada de canal conectado. Testar também auth desativada e flag inválido. Nenhum healthcheck alterado. |
| A07  | NEEDS INFRA DECISION                            | Responsável deve aprovar PR/checks/revisão obrigatórios e política de bypass em main. Nenhuma configuração administrativa alterada.                                                                                                               |
| A08  | BLOCKED / NEEDS INFRA DECISION                  | Obter imagens/digests/versões reais; só depois propor combinação homologada fixa.                                                                                                                                                                 |
| A09  | NEEDS PRODUCT DECISION                          | Remetente/provedor e fluxo de recuperação; dados/credenciais privados. Não implementado.                                                                                                                                                          |
| A10  | NEEDS PRODUCT DECISION                          | Definir campos e estado compartilhado de primeiro acesso MEI.                                                                                                                                                                                     |
| A11  | NEEDS PRODUCT DECISION                          | Priorizar notas/rascunhos/regras, conflitos e retenção entre aparelhos.                                                                                                                                                                           |
| A12  | BLOCKED                                         | Inventário de auth/rotas dos workflows vivos e contrato de adaptador. P0 antes de atendimento real, não incidente confirmado.                                                                                                                     |
| A13  | READY para proposta; runtime BLOCKED            | Base 009 suporta contrato de IDs/eventos; detalhar identidade/deduplicação e compatibilidade com o fluxo vivo antes de implantar.                                                                                                                 |
| A14  | BLOCKED                                         | A12/A13, adaptador, API de atendimento e chip dedicado autorizado. Sem pareamento/envio/restart.                                                                                                                                                  |
| A15  | NEEDS INFRA DECISION; runtime BLOCKED           | Escolher armazenamento externo/retensão e destino de restore isolado após inventariar cron/cópias/volumes reais.                                                                                                                                  |
| A16  | BLOCKED / NEEDS INFRA DECISION                  | Conferir overlays/paths vivos e revisar deploy team separado; não acionar workflow genérico.                                                                                                                                                      |
| A17  | READY                                           | Preparar teste isolado browser HTTPS + conta real + API/PG, sem usar credenciais AWS.                                                                                                                                                             |
| A18  | NEEDS PRODUCT DECISION                          | Medir volume/uso e definir paginação compatível antes de alterar as listas.                                                                                                                                                                       |
| A19  | READY para plano incremental                    | Não refatorar agora; componentes, baseline visual e medição de desempenho em etapa própria.                                                                                                                                                       |
| A20  | NEEDS PRODUCT DECISION                          | Política de dispositivos compartilhados, arquivos locais por conta e retenção.                                                                                                                                                                    |
| A21  | BLOCKED                                         | Enumerar workflows vivos/execuções e correspondência com o Git; não renomear/ativar/excluir.                                                                                                                                                      |

### Origem precisa de A04, sem alteração

| Estado           | Fonte                                                                     | Consumo atual                                                    | Estado esperado na proposta futura                                                                |
| ---------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| 4 conversas demo | `app.js`, `sessionData.conversas`                                         | Inbox, Home/radar, badge, Assistente e relatórios de atendimento | Pages: exemplos explícitos. Conta real: histórico autorizado ou estado vazio/integração pendente. |
| 6 atividades     | `app.js`, `sessionData.atividade`                                         | Atividade de Visão Geral e contextos do negócio                  | Pages: exemplo. Conta real: eventos do próprio negócio ou vazio.                                  |
| 3 notificações   | `app.js`, `sessionData.notificacoes`; `navigation.js` renderNotifications | Menu/indicador de notificações                                   | Pages: exemplo. Conta real: eventos autorizados ou “sem notificações”.                            |

`experience.js` verifica a identidade remota para entrar no app, mas não substitui esses seeds por uma fonte de atendimento real. `auth-store.js` arquiva/troca estados locais por identidade; isso não remove a declaração estática de sessionData. Nenhuma das duas áreas foi modificada.

Na futura A04, distinguir seeds, histórico remoto e notas/rascunhos/vínculos locais existentes. Não esvaziar localStorage ou tabelas como atalho; preservar trabalho local e definir prévia/migração própria. O teste atual com quatro módulos remotos vazios reproduziu os seeds; não é evidência de vazamento entre MEIs.

## Arquivos e commits desta rodada

Arquivos de UI: `frontend/styles/socialmei.css`, `frontend/scripts/business-views.js`. Testes: `tests/audit-ui-browser.cjs`, integração em `tests/browser.cjs`. Documentação: somente este arquivo e `docs/LIVE-ENVIRONMENT-INVENTORY.md`.

Commits separados previstos/concluídos na branch:

1. `fix: correct tools menu search layout`.
2. `fix: prevent report tooltip mobile overflow`.
3. `test: cover audited responsive regressions`.
4. `docs: record audit remediation status`.

Não foram alterados banco, migrations, autenticação, workflow n8n, WAHA, Compose, deploy, branch protection, landing/sidebar/Home/Assistente/cards/cores. As fixtures dos testes não são dados de produção. Esta rodada não autoriza merge/deploy ou correções A03–A21.

## Encerramento

Etapa 0 documentada como PARTIAL/BLOCKED e Etapa 1 preparada para revisão com regressão e capturas. Aguardar revisão e autorização para a próxima etapa. Inventário vivo não preenchido com valores presumidos e nenhuma integração real ativada.
