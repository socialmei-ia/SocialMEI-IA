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
