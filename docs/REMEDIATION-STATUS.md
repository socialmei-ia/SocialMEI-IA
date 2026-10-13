# Remediation Status

**Estado atual — 13/10/2026, 09:57 (-03:00): A03 APLICADA.** Registro operacional e revisão do PR #31 na seção final. As seções anteriores preservam a evolução da auditoria/proposta; afirmações antigas de A03 pendente, PR #32 em rascunho ou ausência de deploy não descrevem o estado atual. Limpeza dos registros sintéticos de QA confirmada pelo responsável às 09:57 (-03:00), pelo fluxo normal do site. A04 não implementada.

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

Capturas em `test-results/audit-ui/`, ignoradas pelo Git. O CI normal gera as capturas `after` e as inclui no artifact `frontend-regression`. As capturas `before` foram geradas localmente contra o SHA auditado e acompanham o pacote de evidências desta rodada; não são geradas pelo modo normal do CI:

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
5. `docs: clarify local baseline evidence`.

Não foram alterados banco, migrations, autenticação, workflow n8n, WAHA, Compose, deploy, branch protection, landing/sidebar/Home/Assistente/cards/cores. As fixtures dos testes não são dados de produção. Esta rodada não autoriza merge/deploy ou correções A03–A21.

## Encerramento

Etapa 0 documentada como PARTIAL/BLOCKED e Etapa 1 preparada para revisão com regressão e capturas. Aguardar revisão e autorização para a próxima etapa. Inventário vivo não preenchido com valores presumidos e nenhuma integração real ativada.

## Acompanhamento autorizado — 13/10/2026

- PR #30 aprovado especificamente, integrado em `main` (`9e943a92624f1cdefc50bfc2322b0f7bfc2a0af3`) e aplicado pelo responsável somente ao gateway. Backup prévio reportado concluído/conferido; nenhuma migration ou reconstrução de API/banco. Usuário confirmou visualmente Ferramentas/Relatórios: **A01/A02 concluídos no site online**. As notas anteriores de “sem merge/deploy” descrevem exclusivamente o encerramento da rodada inicial.
- Etapa 0 agora **PARTIAL com evidência viva fornecida por SSH**: versões Docker/Compose/n8n/WAHA, containers/mounts/redes efetivos, migrations 001–010 e 27 tabelas, 24 workflows/execuções agregadas, estado WAHA aguardando QR e cron ativo com agenda 02:30. Inventário detalhado no acompanhamento de LIVE-ENVIRONMENT-INVENTORY.md.
- Acesso direto do auditor permanece indisponível. Consultas do responsável somente leitura; nenhum segredo ou payload registrado. Não contar verificações pendentes como passes.

### Prontidão revista, sem implementar A03–A21

| Item | Prontidão atual                            | Evidência ou dependência restante                                                                                                  |
| ---- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| A03  | NEEDS PRODUCT DECISION                     | Contrato monetário pendente; valores reais incompatíveis ainda não consultados. Sem arredondamento/migration.                      |
| A04  | READY                                      | Origem dos seeds mapeada; correção e regressão precisam rodada própria.                                                            |
| A05  | READY                                      | Preparar atualização documental em PR separado das correções UI.                                                                   |
| A06  | READY                                      | Migrations 009/010 efetivas confirmadas; healthcheck específico continua necessário, sem implementação agora.                      |
| A07  | NEEDS INFRA DECISION                       | Proteção de main depende de aprovação administrativa do dono.                                                                      |
| A08  | NEEDS INFRA DECISION                       | Versões/IDs vivos parciais conhecidos; faltam RepoDigests e política de pin/atualização.                                           |
| A09  | NEEDS PRODUCT DECISION                     | Definir remetente e recuperação de senha; não há envio Gmail implementado.                                                         |
| A10  | NEEDS PRODUCT DECISION                     | Contrato de onboarding real versus demo.                                                                                           |
| A11  | NEEDS PRODUCT DECISION                     | Definir dados locais que devem sincronizar.                                                                                        |
| A12  | BLOCKED                                    | Legados ativos confirmados; autenticação/versão publicada não verificadas. P0 antes de atendimento real, sem incidente confirmado. |
| A13  | READY para proposta; implementação BLOCKED | Identidade/idempotência exigem contrato e versão publicada dos fluxos legados.                                                     |
| A14  | BLOCKED                                    | WAHA aguarda pareamento; chip autorizado/adaptador/API e A12/A13 pendentes.                                                        |
| A15  | NEEDS INFRA DECISION                       | Agenda/cron/arquivos confirmados; retenção, cópia externa e sucesso automático/restore permanecem pendentes.                       |
| A16  | BLOCKED                                    | Team runtime confirmado diferente do Compose genérico; automação de deploy ainda sem contrato aprovado.                            |
| A17  | READY                                      | Proposta de E2E integrado isolado; nenhuma execução com cliente real.                                                              |
| A18  | NEEDS PRODUCT DECISION                     | Volume alvo/paginação e limites.                                                                                                   |
| A19  | READY                                      | Refatoração futura por componente; não misturar nesta rodada.                                                                      |
| A20  | NEEDS PRODUCT DECISION                     | Política de compartilhamento de dispositivo e arquivos locais.                                                                     |
| A21  | READY para triagem; correções BLOCKED      | Inventário de 24 fluxos disponível; correspondências são candidatas, versão publicada e responsável de cada fluxo pendentes.       |

### Pendências alinhadas com o usuário

- Orçamento/Google Sheets: quatro documentos de orçamento, dois com o mesmo nome. “Resposta Orçamento copy 2” (ID 8hSF0mABWNYJqWQB) não inclui Google Sheets/toolWorkflow no documento salvo e teve 15 erros/8 sucessos retidos nos últimos sete dias. Escolher o ID com o responsável; não sobrescrever outro fluxo por nome. Existem subfluxos Google Sheets ativos, mas seu sucesso não comprova o orçamento original corrigido.
- WAHA no computador do colega: guia/comando dev:waha preparados; atualização efetiva do notebook e preservação das sessões ainda precisam confirmação dele. Estado do WAHA na AWS não é evidência do notebook.
- Estes itens não foram marcados como resolvidos e não autorizam ativar/publicar/enviar mensagens. Nenhuma alteração A03–A21 foi aplicada.

Esta atualização altera somente os dois documentos de acompanhamento. Não exige deploy, migrations ou mudança do runtime. Próxima correção deve ter alvo/ID e critério de aceite definidos antes da implementação.

## Proposta A03 — contrato monetário, 13/10/2026

**Somente preparação autorizada; NEEDS PRODUCT DECISION e inventário monetário vivo pendente.** Google Sheets/orçamento pausado a pedido do usuário. Não alterar validação, preços, custos, schema ou imports nesta etapa.

### Evidência revalidada em leitura

`catalog_data.py` usa `float` finito não negativo em ProdutoFields/ProdutoCreate; `product_import.py` reutiliza ProdutoCreate. A migration 005 armazena preço/custo em `NUMERIC` sem precisão/escala declaradas. `sales_data.py` usa Decimal com 15 dígitos totais e até duas casas decimais; FinanceFields reutiliza Money. As migrations 006/007 usam NUMERIC(15,2). VendaFields valida também desconto e total (preço × quantidade − desconto).

O baseline da auditoria já reproduziu 12.345/1e20 aceitos em catálogo e rejeitados por vendas. A diff do PR #30 não alterou esses contratos. Nesta proposta revalidaram-se os arquivos; não se contou nova execução de modelos/API/PG como pass. O ambiente Python da sessão atual não dispõe das dependências completas para importar esses módulos.

Há dois caminhos adicionais: TransferProduct aceita Decimal com 50 dígitos/20 casas (`workspace_transfer.py`), enquanto as respostas de catálogo e normalizador no frontend usam números JSON/Number finitos (`product-store.js`). Mudar somente o tipo de entrada pode mudar serialização para string e tornar o catálogo ilegível no frontend. Importações/fingerprints e transferência precisam entrar no plano de compatibilidade.

### Regra recomendada, ainda não aprovada

| Aspecto                 | Proposta                                                                                                                                                                                                     |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Preço de venda unitário | Não negativo, finito, até duas casas significativas após a vírgula; mesmo contrato atual de Money.                                                                                                           |
| Custo                   | Mesmo contrato, se o responsável confirmar que não precisa custo unitário fracionário com três/quatro casas. Esta decisão é separada; a A03 comprovada trata a compatibilidade do preço com venda.           |
| Limite                  | Preservar o limite já existente em Vendas/Financeiro: 9.999.999.999.999,99. Não ampliá-lo nesta correção.                                                                                                    |
| Valor zero              | Permitido, como no contrato atual.                                                                                                                                                                           |
| Casas extras            | Rejeitar com mensagem clara; não arredondar silenciosamente. 12.340 equivale a 12.34 e não contém uma terceira casa monetária significativa.                                                                 |
| Quantidade/total        | Preservar quantidade inteira e validação do total/limite/desconto. Um preço válido não garante que qualquer quantidade gere total válido.                                                                    |
| Formato de API          | Manter compatibilidade com números JSON exigidos pelo frontend; conferir limites e ida/volta em centavos. Não mudar para strings sem contrato separado.                                                      |
| Dados existentes        | Contar primeiro. Preservar leituras e históricos; correção por registro somente após prévia e decisão explícita do responsável.                                                                              |
| Banco                   | Não reescrever migrations 005/006/007; nenhuma migration nesta proposta. Constraint futura somente após verificar dados e aprovar plano. Evitar ALTER NUMERIC(15,2) que possa arredondar valores existentes. |

Mensagem candidata: “Informe um valor entre R$ 0,00 e o limite permitido, com até duas casas decimais.” O limite deve ficar visível no formulário/validação, sem expor detalhes de implementação ao usuário final.

### Consulta proposta, somente contagens

Executar no banco team em `BEGIN READ ONLY`, com statement_timeout. Consultar preço/custo de todos os workspaces em agregado, sem retornar nomes, IDs de clientes, e-mails ou valores individuais. Separar valores não finitos/negativos, acima do limite e com fração efetiva além de centavos. O resultado ainda não foi recebido; não afirmar que os dados atuais são válidos ou inválidos.

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '20s';
WITH amounts AS (
  SELECT 'preco' AS campo, preco AS valor FROM socialmei.crm_produtos
  UNION ALL
  SELECT 'custo' AS campo, custo AS valor FROM socialmei.crm_produtos
), assessed AS (
  SELECT campo, valor,
    valor::text NOT IN ('NaN', 'Infinity', '-Infinity') AS finite
  FROM amounts
)
SELECT campo,
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE NOT finite OR valor < 0) AS nao_finito_ou_negativo,
  COUNT(*) FILTER (WHERE finite AND valor > 9999999999999.99) AS acima_do_limite,
  COUNT(*) FILTER (WHERE CASE WHEN finite THEN valor <> trunc(valor, 2) ELSE false END)
    AS fracao_alem_de_centavos
FROM assessed
GROUP BY campo
ORDER BY campo;
COMMIT;
```

As categorias podem se sobrepor: não somar esses contadores como registros únicos. Esta consulta não cobre snapshots legados de importação/transferência nem preço hipotético de vendas futuras; esses casos entram nos testes e na revisão de compatibilidade.

### Aplicação futura e aceite

1. Receber contagens vivas e confirmar precisão/limite, sobretudo custo fracionário. Se houver incompatíveis, preparar prévia privada; não normalizar em lote.
2. Alterar apenas validação de entradas create/update/import de preço (e custo se aprovado), preservando DTO de saída/leitura de antigos. Não alterar contrato contábil ou histórico de vendas.
3. Revisar transferência, fingerprints de importação e reenvio de operações: mudança Decimal/string/escala não pode transformar repetição legítima em conflito nem modificar hashes/snapshots antigos automaticamente.
4. Conferir formulário/feedback nos modos local e remoto; preço inválido deve ser identificado ao cadastrar/importar/selecionar item, sem fallback silencioso para zero ou arredondamento.
5. Testar zero/centavos/12.340/12.345/limite/acima do limite/NaN/Infinity/negativos; Produto/Serviço; PATCH parcial; import/transferência; leitura de item antigo; quantidade/desconto/total no limite; serialização/frontend e idempotência. Rodar suites relevantes com PostgreSQL real em ambiente isolado; skips separados.
6. PR separado de documentação/infra; aprovação específica antes de merge/deploy. Backup pertinente e atualização apenas dos serviços realmente modificados. Migration somente se necessária e aprovada separadamente.

**Não implementado:** tipos/validações novos, arredondamento, constraint, migration, normalização de preço/custo, alteração de workflow/WAHA ou novo deploy. Esta proposta não conclui A03.

### Contagens monetárias recebidas — 13/10/2026, 01:10 (-03:00)

O responsável executou a consulta proposta em transação READ ONLY no banco team. Ela agregou `crm_produtos` de todos os workspaces: um preço e um custo; zero valores não finitos/negativos, zero acima do limite de Vendas e zero com fração efetiva além de centavos em ambos os campos. Não foram retornados valores individuais ou dados pessoais.

Esse resultado fecha o inventário monetário da tabela atual na hora da coleta. Não cobre snapshots/importações arquivadas, arquivos locais ou cadastros futuros. Não há valor atual nessa tabela que precise normalização segundo a regra candidata; nenhuma escrita/constraint/migration foi feita.

A03 continua **NEEDS PRODUCT DECISION**: confirmar duas casas para preço e decidir se custo também deve ter duas casas ou se exige precisão unitária adicional. Preservar o limite atual de Vendas e rejeitar casas extras sem arredondamento são recomendações, ainda sem implementação. Após essa decisão, preparar PR de código separado do PR documental #31.

## Implementação proposta A03 — 13/10/2026

Branch `fix/catalog-money-contract`, baseada no merge aprovado A01/A02 `9e943a92624f1cdefc50bfc2322b0f7bfc2a0af3`. Evidências de runtime e contagens monetárias estão no PR documental #31: um preço e um custo no catálogo atual, zero incompatíveis na consulta READ ONLY de todos os workspaces. Não é nova auditoria nem inventário de snapshots/arquivos locais. Google Sheets continua pausado.

### Contrato e preservação

- Preço e custo de entradas novas create/PATCH/import usam a validação Decimal `Money` já usada em Vendas/Financeiro: finitos, não negativos, até duas casas efetivas e limite de 9.999.999.999.999,99. Casas extras são recusadas antes da conversão float. Não há quantize/arredondamento automático.
- JSON de catálogo continua numérico. Snapshots/fingerprints de importações válidas mantêm a representação anterior; teste fixa um hash produzido pela versão baseline. Parâmetros monetários enviados ao SQL usam Decimal, sem alterar valores de registros existentes.
- DTO de saída e validação do registro combinado ficam separados da nova validação de entrada. Itens antigos com preço/custo fora do contrato continuam legíveis, e PATCH de nome sem campos monetários não os normaliza. PATCH que enviar preço/custo inválido é recusado.
- Transferência nova valida os valores depois de conferir recibo, mas antes de gravar registros. Recibo já existente de transferência é recuperado sem revalidar/normalizar o snapshot antigo, preservando fingerprint e idempotência.
- Formulário de Produtos nos modos local/remoto valida a representação decimal antes de converter para Number, mostra limite/mensagem de duas casas e preserva o texto inválido para correção. Importações recusadas recebem mensagem monetária específica, sem expor valores privados.

Não foram alterados contrato de quantidade/desconto/total de vendas, Financeiro, schema, migrations, snapshots/hashes históricos, auth, n8n, WAHA, Compose ou deploy. Nada foi aplicado à produção.

### Compatibilidade e limites

O catálogo atual não contém valores incompatíveis na hora da coleta, mas importações locais/snapshots históricos podem conter. Novo pedido de importação de catálogo com valor inválido é recusado, inclusive reenvio de um payload antigo fora do novo contrato; seu recibo armazenado e o item já existente permanecem intactos. Reenvios válidos mantêm os hashes. Transferências completas já registradas têm tratamento explícito para recuperar recibos antigos. Não corrigir valores ou reescrever fingerprints como atalho.

Produto antigo pode ser lido com valor incompatível; não se promete que esse preço antigo seja aceito em venda nova. A regra garante a compatibilidade dos preços novos aceitos, respeitando também o limite do total da venda. Se custo unitário com mais casas for necessário, reabrir a decisão de produto antes de publicar a mudança.

### Validação desta branch

- `npm test`: 53 passaram, zero falhas/skips.
- Python local: 106 registrados, 31 executados passaram e 75 skips por falta de PostgreSQL local; skips não contados como passes. Inclui sete testes locais novos de Money/limites/JSON/PATCH/fingerprint/validação antes do banco.
- Cinco testes de integração adicionais exigem PostgreSQL isolado: roundtrip e venda nos limites, leitura/PATCH de antigo, replay de importação válida, bloqueio de transferência nova inválida, replay de recibo antigo de transferência sem arredondamento.
- Browser: 88 estados/16 fluxos passaram, incluindo bloqueio de valores inválidos e preservação dos formulários em modos local/remoto. Format check e git diff --check passaram. CI com PostgreSQL real deve ser conferido no PR desta branch; sucesso de outra branch não vale para esta.

Próximo passo desta etapa: revisar diff e testes, preparar [PR #32](https://github.com/socialmei-ia/SocialMEI-IA/pull/32) exclusivo A03 e aguardar aprovação específica para merge/deploy. Não avançar automaticamente para A04 ou atendimento real.

### Resultado do CI A03

[Repository checks #93](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/38346881087) concluído com sucesso, head `fa6ad1e21e41a1f604734fe44e455c8ca22be215`, correspondente aos dois commits de código/testes do PR #32. Jobs validate/browser verdes: 106 testes da API com PostgreSQL real, zero skips; Node/formatação; 88 estados/16 fluxos; gateway HTTPS/Basic; inicialização e restauração isoladas. O sucesso em CI não é evidência de deploy na AWS.

PR #32 permanece em rascunho, sem merge/deploy. PR #31 contém somente documentação. A03 está preparada para revisão, com os limites de compatibilidade descritos acima; A04 e Google Sheets não foram implementados. Nenhuma migration ou alteração de dados foi aplicada ao banco de produção.

## Registro operacional A03 — 13/10/2026

**Status: APLICADA.** Atualização explicitamente autorizada, executada pelo responsável via PowerShell/SSH, seguida de conferências sanitizadas e teste autenticado reportado pelo responsável. O auditor não possui sessão SSH própria. A aprovação de A03 não autoriza merge do PR #31 ou implementação de A04.

### Git, backup e rollback

- PR de código [#32](https://github.com/socialmei-ia/SocialMEI-IA/pull/32) integrado em `main`; branch de origem `fix/catalog-money-contract`.
- SHA anterior: `9e943a92624f1cdefc50bfc2322b0f7bfc2a0af3`.
- SHA aplicado e checkout limpo conferido: `28ae7ef3af563d5405da4e52236468d55de1afdb`, HEAD destacado no servidor team.
- CI [Repository checks #93](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/38346881087) verde no head aprovado `fa6ad1e21e41a1f604734fe44e455c8ca22be215`. Resultados isolados descritos acima; não substituir evidência da AWS por CI.
- Backup existente aprovado, concluído antes do deploy: `/home/ubuntu/socialmei-backups/team-auto-20261013-092524-6fa657`. `equipe.dump` 100905 bytes, `configuracao.tar.gz` 2128 bytes e `conteudo.txt` 18040 bytes; integridade SHA256 e índice do dump conferidos. Nenhum restore em produção.
- Imagens anteriores preservadas nas tags `socialmei-team-api-rollback:team-auto-20261013-092524-6fa657` e `socialmei-team-gateway-rollback:team-auto-20261013-092524-6fa657`. Registro `a03-operacao.json` e overlay `a03-rollback.compose.json` no diretório do backup.
- Rollback conhecido: checkout não forçado do SHA anterior e `compose.team.yaml` com overlay de rollback, recriando somente `team-api`/`team-gateway` com `--no-build --no-deps --force-recreate --wait`; executar doctor depois. Não restaurar banco automaticamente. Rollback não utilizado nesta aplicação.

### Runtime e serviços preservados

Rebuild e recriação somente de `team-api` e `team-gateway`, com `--no-deps`; nenhum serviço de migration iniciado. SHA aprovado confirmado e conteúdo dos três módulos Python e quatro scripts frontend envolvidos comparado por SHA256 entre checkout e containers: PASS.

| Serviço      | Campo Image efetivo após deploy                                           | Estado observado                                                                             |
| ------------ | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| team-api     | `sha256:52cabc25188a466f9d616881ab3004226a2bd7335f7157d909babc931cb910df` | running, healthy, restart count 0; início 2026-10-13T12:33:21.575905504Z                     |
| team-gateway | `sha256:cb27d163ffdab16967c24ae2f6f1d27354bd84b68ee2819d7506b446edd7be1b` | running, sem healthcheck configurado, restart count 0; início 2026-10-13T12:33:28.157690255Z |

PostgreSQL team/legado, n8n, WAHA e Caddy público mantiveram os mesmos campos Image e StartedAt do preflight recebido às 09:21, todos com restart count 0. Não extrapolar esta comparação para containers não incluídos na coleta. Diretório legado `/home/ubuntu/socialmei` não atualizado. Gateway sem healthcheck Docker não foi descrito como funcionalmente saudável apenas pelo `compose --wait`.

Logs desde o início dos containers alterados: zero indicadores de Traceback, HTTP 500 Internal Server Error, connection refused, import error e nível ERROR. Somente contadores sanitizados foram retornados; isso não equivale a captura do console do navegador ou monitoramento contínuo.

### Banco e comparação estrutural

- **Migration: NENHUMA.** As mesmas dez versões 001–010 permaneceram instaladas. Não houve alteração SQL de schema ou normalização monetária.
- Antes dos testes pela interface, as contagens físicas do workspace team permaneceram clientes 1, produtos 1, vendas 1 e financeiro 1. Doctor permaneceu healthy/shared_data true: clientes 1, produtos 1, vendas visíveis 0 e financeiro 1. A venda antiga logicamente excluída explica a diferença; não foi removida para ajustar o diagnóstico.
- Os hashes de colunas/índices das duas consultas iniciais não são comparáveis diretamente: as fórmulas de agregação diferiam. Não foram usados como prova de alteração ou igualdade.
- Para fechar essa lacuna, o responsável comparou o DDL do schema `socialmei` extraído do backup pré-deploy com o DDL atual, em memória. `pg_dump` atual executado com transação somente leitura; `pg_restore --schema-only --file=-` apenas produziu texto, sem conexão de restauração. Normalização removeu comentários, linhas vazias e marcadores aleatórios restrict/unrestrict, preservando demais instruções: **PASS**.
- SHA256 estrutural normalizado de ambos: `e97f6e9a3a949d0bc0737e85916a5da2e555727d62e9e8e2fc2e8f25dd9f4587`. Evidência limitada ao schema `socialmei`; não é inventário completo de roles globais ou prova byte a byte dos dados.
- Dados preexistentes não foram modificados em massa. Os testes manuais criaram somente dados sintéticos pelo fluxo normal da aplicação; as contagens anteriores não representam o total depois desse QA.

### Testes A03 e regressão

| Verificação                     | Evidência / resultado                                                                                                                                                                                                                                                                                                              |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Contratos no container aplicado | Produto e Serviço, preço/custo em create/PATCH: zero, 12.34 e limite aceitos; 12.345 e 1e20 recusados. Contrato de venda compatível. Dez grupos reportados PASS; modelos não gravaram registros.                                                                                                                                   |
| Auth                            | `/api/v1/auth/me` anônimo retorna 401; raiz do gateway sem Basic retorna 401. PASS. Nenhuma credencial publicada.                                                                                                                                                                                                                  |
| Health                          | API healthy e doctor healthy/shared_data true/workspace team após aplicação. PASS.                                                                                                                                                                                                                                                 |
| Interface autenticada           | Responsável confirmou o roteiro: Clientes, Catálogo, Vendas e Financeiro abrem; Claro/Escuro; serviço sintético QA A03 criado por 12,34, persistiu após reload, editado para 15,90 e persistiu; cliente fictício e venda do serviço criados, preço/persistência conferidos. PASS reportado, sem captura automatizada dessa sessão. |
| Produto / integração isolada    | Cobertos pelos modelos do container e testes CI com PostgreSQL real. Não afirmar criação manual de produto na AWS: o roteiro autenticado usou Serviço.                                                                                                                                                                             |
| Console do navegador            | Não foi recebida captura do console nessa sessão. Ausência de erro visual reportada e logs sanitizados sem indicadores; ausência de novo pageerror/erro de console permanece evidência das suites browser isoladas, não observação do console vivo.                                                                                |
| Limpeza de QA                   | PASS reportado às 09:57 (-03:00): responsável confirmou a remoção pelo site somente da venda, serviço e cliente sintéticos desta validação, na ordem orientada. Sem SQL ou exclusão em massa.                                                                                                                                      |

Não houve falha crítica reportada na atualização ou validação. A suite completa não foi executada contra o banco de produção; testes de integração/restore permaneceram isolados no CI. Skips locais continuam separados dos passes, conforme resultados registrados acima.

### Revisão do PR #31

Revisão documental após confirmação da aplicação, testes reportados e comparação estrutural. PR permanece somente com `docs/LIVE-ENVIRONMENT-INVENTORY.md` e `docs/REMEDIATION-STATUS.md`, sem código A04/infra. Nesta atualização, somente o registro operacional deste documento foi modificado.

Divergências encontradas: acompanhamento ainda dizia A03 pendente/PR #32 em rascunho, Git/AWS em 9e943a9 e nenhum deploy; o inventário vivo descreve coleta histórica anterior e não os dois novos campos Image. Este registro supersede esses estados para a operação A03; preserva os snapshots datados. O inventário histórico não deve ser apresentado como inventário atual completo. Descrição do PR #31 também precisa refletir o deploy confirmado antes de aprovação final.

Etapa 0 continua PARTIAL: versões publicadas/equivalência integral de workflows, autenticação estrutural dos legados, roles/grants globais, RepoDigests e retenção/sucesso automático/cópias externas de backup permanecem sem fechamento completo. Não foram inferidos incidentes ou integração WhatsApp pronta.

Prontidão: **para revisão do responsável; ainda sem merge autorizado**. Revalidar CI e metadados de mergeabilidade no GitHub após esta atualização documental. A simulação local `git merge-tree --write-tree` contra main 28ae7ef não apresentou conflitos; isso não substitui o status administrativo do GitHub. Limpeza de QA confirmada pelo responsável. Descrição do PR ainda precisa atualização antes de aprovação final. CI documental do commit `4d83bec6e15dbafa170949f57f1b20e875305e27` concluído com sucesso: [Repository checks](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/38400593538). Esse resultado antecede esta anotação final de limpeza; não atribuí-lo automaticamente ao novo commit. Não executar novo deploy para documentação.

### Próxima rodada — somente plano A04

Separar a origem dos seeds demonstrativos de conversas/atividades/notificações: mantê-los no Pages/demo e usar dados autorizados ou estados vazios para contas reais novas. Preservar notas/rascunhos e dados existentes; testar demo, conta nova, conta existente e isolamento entre workspaces em ambiente isolado. Não apagar dados como atalho. **Não implementado nesta rodada.**

Google Sheets permanece PAUSADO. n8n e WAHA/WhatsApp não foram alterados, ativados, pareados ou usados para envio. Branch protection, deploy genérico, migrations e A04+ não alterados. Encerramento desta execução após revisão documental; próxima implementação depende de autorização própria.

## A04 — separação dos exemplos de atendimento, 13/10/2026

**Implementação local para revisão; sem merge/deploy.** Rodada autorizada após encerramento da A03 e merge documental do PR #31. Branch `fix/account-demo-state`, baseline `main` em `303373b9f111a9662ed8d720d5a4892cc1f7e3ad`; checkout inicial limpo. As seções anteriores de A04 somente planejada são históricas. Proteção do GitHub e ajustes de deploy foram adiados pelo responsável; não incluídos nesta rodada.

### Reprodução e mudança

O teste browser de conta real falhou antes da correção, inclusive na tela de autenticação: `sessionData` continha quatro conversas, seis atividades e três notificações demonstrativas. Confirmada a mesma origem mapeada na auditoria: declaração estática em `frontend/scripts/app.js`. Não houve nova auditoria geral.

A inicialização agora remove somente esses três arrays de exemplos da sessão em memória quando `SocialMEIAuth.remote` está habilitado. A decisão usa o modo de autenticação configurado, sem esperar uma identidade assíncrona: conta ainda não autenticada ou sessão expirada não cai no demo. O modo local/Pages mantém os quatro/seis/três exemplos.

Não houve escrita de limpeza em localStorage ou banco. A restauração existente de conversas locais, notas e rascunhos permanece; arquivos arquivados por identidade não são apagados. Notas antigas associadas a exemplos removidos continuam armazenadas, mas não se transforma o exemplo fictício em conversa real para exibi-las. Recuperação/reassociação futura desses contextos requer decisão própria. Não foi criado histórico de atendimento, feed de eventos ou integração de notificações inexistentes.

### Testes e limites

- Teste dedicado reproduziu quatro/seis/três no baseline antes da correção; a execução `before` falhou como esperado.
- Regressão de contas ampliada: usuário sem sessão, administrador existente, conta MEI nova por convite, reload, logout e retorno ao administrador. Verifica estado sem seeds e arquivamento/restauração das notas e rascunhos, sem apresentá-los na outra identidade.
- Estados vazios de Início, Caixa Unificada, Assistente, Relatórios e notificações nos temas Claro/Escuro e larguras 360/390/430/1440, para administrador e MEI novo. Mantido o critério de ausência de overflow global. Página pública/demo deve manter exatamente os exemplos quatro/seis/três após cadastro local.
- Browser usa API controlada e dados sintéticos, com endpoints externos bloqueados; não substitui autenticação/isolation no PostgreSQL real ou QA autenticado na AWS. Testes anteriores de auth/store e suites de regressão permanecem aplicáveis. A mudança não altera contrato de identidade/deduplicação dos fluxos n8n, que continua A12/A13.
- Resultado local final: `npm test` 53 passes, zero falhas/skips; `npm run format:check` PASS; `CHROMIUM_EXECUTABLE=/tmp/chromium npm run test:browser` 88 estados/16 fluxos PASS, incluindo regressão A01/A02/A03 e os checks A04 acima. Dezesseis combinações adicionais de identidade/largura/tema verificadas no fluxo de contas; nenhum pageerror detectado por esse fluxo. `git diff --check` PASS. CI do PR A04 ainda deve ser conferido no head publicado. Sem execução local Docker/PostgreSQL nesta rodada; não atribuir cobertura de runtime AWS a mocks browser.

Somente UI de inicialização, testes e este acompanhamento. Sem redesign, CSS, backend, schema, migrations, limpeza de dados existentes, n8n/WAHA/WhatsApp, Google Sheets ou branch protection. Aplicação no servidor e merge exigem revisão própria. A05/A06, recuperação por e-mail e onboarding ainda não implementados nesta rodada.

Primeiro CI A04: job validate passou; browser falhou ao preencher a confirmação de senha após reload, pois o formulário foi recriado enquanto o teste interagia. A carga inicial já desabilita `#refresh` e depois redesenha as telas; módulos remotos também possuem botões de reload desabilitados durante carga. O teste agora aguarda esses controles habilitados antes de interagir com a conta autenticada. Nenhum timeout foi ampliado, teste ignorado ou comportamento de renderização da aplicação alterado para esconder a falha. Conferir a nova execução do head atualizado; a primeira execução não foi contada como PASS.

### Encerramento A04 — aplicação confirmada

PR #33 integrado mediante aprovação específica. SHA aplicado no servidor: `8c719b76c8b17e11af691dbb6e09aba3413be70a`; anterior `28ae7ef3af563d5405da4e52236468d55de1afdb`. CI do head A04 `757a65855906c8de13a1d50c7c752d555f966f6d` passou nos jobs validate/browser: [execução](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/38407234414).

Backup pré-deploy `/home/ubuntu/socialmei-backups/team-auto-20261013-111726-eee954`: dump 101037 bytes, configuração 2128 bytes e índice 18040 bytes, integridade conferida. Imagem anterior do gateway preservada e overlay de rollback registrado. Atualização somente do gateway com `--no-deps`; arquivo `app.js` do container comparado com o aprovado, proteção Basic PASS, zero indicadores de erro e containers restantes iguais ao snapshot anterior. API/PG saudáveis; nenhuma migration, restore ou alteração direta de dados. Rollback não utilizado. Responsável confirmou o roteiro autenticado no site, com refresh e temas Claro/Escuro: A04 APLICADA/VALIDADA.

Clientes visíveis já estavam em zero no preflight A04 e permaneceram zero após deploy; produtos 1, vendas visíveis 0, financeiro 1. A queda anterior de clientes 1 → 0 ainda não teve explicação confirmada pelo responsável. Não atribuir essa variação à A04 nem afirmar exclusão intencional; manter a pendência sem restaurar/apagar dados como atalho.

## A05/A06 — documentação e readiness, rodada atual

Autorizada após A04 validada. Baseline `main`/checkout team aprovado em `8c719b76c8b17e11af691dbb6e09aba3413be70a`; checkout local limpo, branch `fix/auth-channel-health`. A evidência afetada pela evolução desde a auditoria foi revalidada: guias ainda negavam contas/CRM remotos e `check_database` consultava CRM até 008 sem contas/canais ou versões registradas. Sem nova auditoria geral.

A05 corrige ARCHITECTURE.md, BANCO-DE-DADOS.md e SHARED-DATA-API.md: três modos de frontend/gestão e legado separado; contas opt-in, isolamento por sessão, Basic adicional e Bearer técnico distinto; fontes de verdade/schema/migrations e limites de documentação histórica. Mantidos os arquivos e passos legados explicitamente rotulados; roles declaradas não apresentadas como grants vivos. Inclui contrato monetário A03 e separação demo A04 já aprovados.

A06 mantém liveness `/health` e amplia readiness `/health/db` com `capabilities` aditivo. Verifica 001–008 registradas e CRM em READ ONLY/LIMIT 0; auth ativada exige configuração válida, migration 010 e consultas de estrutura de contas. Ausência retorna 503 sanitizado. Auth desativada não exige 010 e informa `not_checked`. Canais são capacidade opcional: 009/estrutura disponíveis → `prepared`; ausência/falta de coluna ou permissão de leitura → `unavailable`, sem derrubar CRM. Conexão do provedor fica `not_checked`; sem WAHA/webhooks/envios. `doctor` passa a consumir o mesmo endpoint HTTP e exige CRM healthy/shared_data true.

Testes novos cobrem configuração inválida, auth desativada, erro sanitizado, ausência de migration/tabela/coluna e canal opcional. Simulações de metadata/DDL e registros de migrations ocorrem somente no PostgreSQL de teste isolado, com restauração da estrutura ao final. Nenhuma migration adicionada/editada. Readiness não é prova de grants de escrita completos, constraints/índices, login individual ou disponibilidade de WhatsApp.

Implementação preparada para testes/PR próprio, **sem merge/deploy desta rodada**. Proteção de main e workflow/deploy adiados a pedido do usuário. Sem alteração de frontend, contas existentes, preços, n8n, WAHA/WhatsApp ou Google Sheets. Recuperação por e-mail e onboarding dos MEIs continuam etapas posteriores.

Validação local: Node 53 passes/zero falhas/skips, formatação PASS, browser 88 estados/16 fluxos PASS incluindo A01–A04 e conta real/demo. Python API: 119 registrados, 36 executados passaram, 83 skips por ausência de PostgreSQL local; oito skips novos são cenários reais de schema/readiness e não contam como passes. Operação/backup: 24 registrados, 19 passaram, cinco skips de gateway dependentes de Docker. Compilação dos arquivos Python alterados e `git diff --check` PASS. CI com PostgreSQL/gateway reais precisa ser confirmado no head publicado antes de aprovação.

Primeira execução CI A05/A06: 119 testes API executados no PostgreSQL isolado; a assertiva antiga de `test_database_health` falhou porque comparava o payload inteiro sem o novo campo aditivo `capabilities`. Atualizada para exigir o payload completo, incluindo capacidades de CRM/auth/canais, sem remover a checagem dos campos antigos. Não contar essa execução como PASS; conferir o novo head antes de revisão final.

## Continuidade — base de estabilização, 13/10/2026

Esta seção é posterior às anotações históricas de A03/A04/A05/A06 acima. Main conferida em `b27e75d01bdadef33707123347cab5272ee05040`; merge #34 e CI aprovados. O responsável relatou aplicação somente da API, saúde CRM/auth/canais e login/saída/reentrada. Acesso AWS não disponível nesta rodada: não se apresentou esse relato como reconfirmação independente.

A estabilização usa branch própria, preserva as decisões adiadas e registra correções/testes em [PROJECT-BASELINE-REVIEW.md](../PROJECT-BASELINE-REVIEW.md). Migration 011 e perfil interno de consulta preparados/testados somente em destino descartável; nada aplicado na AWS. Instância n8n/WAHA inalterada. Base operacional completa continua pendente de inventário/homologação do responsável, separada do resultado local/CI.
