# SocialMEI.IA — Integração 1:1 dos dois HTMLs oficiais do usuário

## Regra fundamental (não negociar)
O usuário pediu **literalmente os layouts e todas as interações** de dois HTMLs fornecidos, dentro das abas oficiais da aplicação:
1. `frontend/reference/Oportunidades-V8-original.html` (61 KB);
2. `frontend/reference/Divulgacao-V4-original.html` (55 KB).

Estes são os **golden masters** da interface. O código anterior da PR #100 tentou recriá-los com componentes e CSS novos (`opportunities-v8.js`, `opportunities-v8-parity.js`, `divulgacao-v4.js`, `divulgacao-v4-parity.js` etc.) e o usuário confirmou que **não** ficaram iguais. O problema não se resolve adicionando mais cartões/dashboards ou pequenos overrides sobre a adaptação existente. Preserve e leia os dois arquivos de referência, além de testá-los no navegador. **Não altere os golden masters**; um teste SHA-256 evita modificações.

**Entregável:** substituir efetivamente o miolo das abas `Oportunidades` e `Divulgação` de `frontend/socialmei-app.html` pelo layout, DOM, hierarquia, CSS, transições e comportamentos visíveis correspondentes, preservando a navegação principal, temas, autenticação e integrações oficiais. Não basta criar links para abrir os originais, colocar `iframe` demonstrativo separado ou semear clientes fictícios em contas autenticadas.

## Fonte da verdade e restrições
- Frontend oficial é um documento HTML com estilos/JS clássicos, sem build de framework. **Não migrar para React, Vue, Next, TypeScript, novos bundlers**. É permitido refatorar em arquivos de JS/CSS vanilla.
- Backend é FastAPI/Postgres; o store autenticado é `frontend/scripts/opportunity-lifecycle-store.js`, fachada nativa `frontend/scripts/opportunity-lifecycle.js`, API `python-service/opportunities.py`. A primeira chamada pode retornar até 100 oportunidades ordenadas por atualização.
- Divulgação: `frontend/scripts/content-studio.js`, `frontend/scripts/content-drafts.js`, `frontend/scripts/content-workspace.js`, `frontend/scripts/content-preparation-store.js`, `frontend/scripts/content-preparation.js`, configurações e sessão existentes.
- Não perder funcionalidades não presentes nos protótipos: histórico remoto, auditoria e revisão de oportunidade, vinculação de vendas, isolamento de negócio, rascunhos e agendamentos preparados, proteção de sessão e CSRF. Não degradar telas adjacentes, onboarding, tema ou sidebar.
- Nada de n8n, WAHA, Meta/Instagram, email ou IA externa reais, nem simular que uma publicação foi enviada. Preservar os rótulos de “simulação”.
- Não fazer merge, deploy, modificar AWS, credenciais, schemas ou migrations **sem autorização explícita específica**. Trabalhar na branch atual da **PR #100**, manter Draft e abrir commits revisáveis. Não criar PR concorrente redundante.

## Fase 1 — Inventário exaustivo ANTES de codificar
Compare os DOMs, layouts e handlers dos dois HTMLs originais com o app nativo. Registre uma matriz **cada seção / estado / interação → equivalente integrado / novo endpoint necessário / decisão de segurança**.

### Oportunidades V8: obrigatoriamente iguais visual e funcionalmente
- Header e hero exatamente como original: iconografia, cores azul-marinho/azul, títulos animados, ilustração, menus de Ajuda, Ferramentas, usuário e barra de comando `Ctrl+K`.
- Formulário: cliente com busca/seleção, interesse Em análise/Frio/Morno/Quente, campo “O que o cliente procura?”, valor, data de retorno, validação, feedback e criação.
- Retomar hoje: vencidos e sem atualização conforme regra original, ícones, copiar retornos, remarcar e concluir contato, com datas consistentes.
- Modos **Lista / Termômetro / Semana** com mesmo controle segmentado deslizante, filtros animados “Em andamento”, “Em análise”, “Frio”, “Morno”, “Quente”, “Venda realizada”, “Não avançou”.
- Lista: cliente com avatar, interesse, valor, próxima ação, expansão de linha com todos campos de edição, encerramento, reabertura, histórico e ações; filtros, busca por `/`, ordenação, empty states e cartões animados/FLIP.
- Termômetro **original de fichas circulares** em quatro zonas (não substituir por Kanban de cartões retangulares), tamanho da ficha representando valor, marca de retorno atrasado; drag-and-drop para mudar interesse **mais alternativa acessível sem arrastar**.
- Semana com colunas “Atrasadas”, Hoje, próximos dias e Sem data; movimento pelo mouse, toque e teclado (selecionar ficha → selecionar dia).
- Mensagens, undo, atalhos, modais e feedback animado conforme arquivo. Undo remoto só se operação inversa autorizada e realmente persistida: **não simular desfazer alteração no servidor**.
- Não criar registros falsos do `seed()` no modo autenticado; usar cliente real selecionado da lista do negócio autenticado. Dados exibidos jamais misturam workspaces.

**Contrato existente:** `Interest = unknown/cold/warm/hot`; o HTML original chama `analysis` ao `unknown`. Backend tem `outcome=open/won/lost`; criação `POST /api/v1/opportunities` exige `client_id,title,interest_level,operation_id`. Edição exige `expected_revision` e `operation_id`. Motivos para ganhar/perder e integração de vendas seguem validadores do servidor. Renderizar datas e status sem falsificar.

**Campos que a API ainda não oferece:** `valor estimado (v)`, `data de retorno (f)` e `nota (n)` originais. Para paridade integral e sincronizada é preciso projeto e aprovação de migrations, schema, autorização e API. Até haver autorização, manter sidecar local por `usuario+negocio+oportunidade`, visualmente marcado como **não sincronizado** e sem somá-lo a vendas/financeiro. NÃO afirmar que a paridade de persistência é completa.

### Divulgação V4: obrigatoriamente igual visual e funcionalmente
- Header, hero animado, ideia de hoje, indicador de sessão, tema, barra de progresso.
- **Dock inferior fixo deslizante** com Criar / Rascunhos / Agenda / Conexões, igual ao HTML original, integrado somente dentro desta aba; teclado 1–4; esconder adequadamente ao abrir teclado mobile.
- Studio **duas colunas**: preview de telefone na **esquerda** (moldura, notch, Story/Feed/Reel, nome de negócio, mídia, texto, CTA editável), formulário guiado em `details` com etapas enumeradas na **direita**. No mobile manter a ordem/reflow do original. Não trocar por grid genérico de cards.
- Story, Feed, Reel com seleção animada, previews nos aspect ratios originais, progressão dos campos, validação de arquivos, mídia, zoom, arrastar reposicionamento e setas, área segura, Feed claro, tela cheia.
- Título/legenda/CTA/hashtags/campos `tema/prod/obj/tom`; sugestão de legendas e preenchimento; atualização imediata dos textos **dentro da prévia**, sem sobrescrever alterações sem confirmação.
- Salvar, novo, duplicar, editar, excluir com confirmação/undo quando apropriado; filtros de rascunhos e miniaturas; importação/exportação JSON V4 e JSON nativo. Respeitar limite/escopo e validação do repositório oficial; backup não inclui mídia bruta sem uma política explícita.
- Agenda de duas semanas, horários por tipo de conteúdo, seleção, edição e cancelamento, estados “Simulado/Cancelado”; **Simular 3 publicações da semana** deve ser fiel à original mas não fingir envio externo nem contornar o fluxo compartilhado com idempotência/revisão. Se o contrato impedir a transação, deixar o botão claramente desativado com motivo até obter aprovação do desenho de backend.
- Conexões Instagram/WhatsApp/Facebook como **preparações pendentes**, não autenticação externa efetiva; nome/bio do negócio coerente com o perfil autenticado sem criar outro cadastro paralelo.
- Todos os microefeitos do original (entrada das palavras, botões, progresso, skeleton/media), `prefers-reduced-motion`, focus, ESC e Ctrl+S.

## Fase 2 — Implementação visual EXATA
- Extraia o DOM e CSS originais, não redesenhe. Preserve dimensões, tipografia, raios, gradientes, sombras, animações, icons, alvos de toque e mobile breakpoints.
- Escopar a CSS a cada aba/raiz específica para impedir que `header`, `main`, `:root`, `body`, `button`, `.bar`, `.card` etc. impactem outras telas. Não inserir o documento HTML inteiro no app; extrair a composição interna e nomes de classe sob namespaces. Preservar a experiência exata, trocando apenas a topbar redundante necessária para manter sidebar/navegação global.
- Separar ações/renderização da lógica de persistência e normalização. Um adapter traz estado de `SocialMEIOpportunityLifecycle` para o modelo da V8 e serializa operações de volta ao store. Adapter de Divulgação liga o visual V4 a drafts/preparations existentes.
- Interações devem funcionar com **mouse, teclado e toque** e feedback de êxito apenas após escrita; sem `localStorage` global sem escopo.
- Na PR atual, remover/substituir o código redundante da adaptação antiga de V8/V4 (somente depois de transicionar e testar) para evitar dois geradores de DOM competindo ou dois sistemas de navegação.

## Fase 3 — Homologação de paridade com evidências
1. Abrir **os golden masters originais** e **as duas abas integradas** no navegador na mesma viewport (ex.: 1440x900, 390x844 e 320x700), com os mesmos dados de teste e temas. Capturar screenshots lado a lado; apontar cada diferença e corrigir. Não usar só testes de presença de IDs.
2. Automatizar fluxos com Playwright, em preview HTTPS real `npm run preview -- up`, com duas contas e workspaces separados, permissões diferentes, clientes, opportunities, edições de interesse, closes, historico, vendas, valores locais, retorno semanal, rascunhos, mídia, filtros, backups, e simulação/agenda. Garanta que edições não salvas, ESC, foco e mobile funcionem.
3. Rodar `npm test`, `npm run format:check`, `npm run test:browser`, `npm run test:preview` e Python tests aplicáveis. Confirmar os **três jobs** no SHA final do CI (validate, browser, preview); não declarar aprovado enquanto job estiver queued.
4. Não executar testes destrutivos em banco ou conta reais; staging descartável e dados fictícios.
5. Registrar capturas (desktop/mobile, light/dark), checklist de fidelidade funcional e visual, resultados CI, limitações de backend, arquivos alterados e comandos Windows para atualizar checkout local.

## Critérios de aceite
- Navegar para Oportunidades e Divulgação **dentro do SocialMEI.IA** mostra as mesmas telas e o mesmo fluxo do HTML original, sem cair no componente alternativo da PR #100.
- Testar ações principais das referências produz efeitos observáveis idênticos, exceto integrações externas explicitamente simuladas e campos que requerem schema/contratos ainda não autorizados.
- Frontend nativo continua autenticado e sem dados fictícios injetados; outras abas não sofrem alterações.
- CI integralmente aprovado no último SHA, comparação de capturas documentada, PR #100 ainda Draft.
- Falta que depender de migrations/produção deve ser registrada como **pendência**, nunca esconder com mock nem dizer que está concluída.

## Ambientes
- GitHub `socialmei-ia/SocialMEI-IA`; PR #100, branch `feat/native-opportunities-v8-content-v4`, base correta `release/integration-candidate-94-review` (#95).
- Windows do usuário já tem Git, Node 24 e Docker Desktop; usa `npm.cmd` (PowerShell bloqueia `npm.ps1`).
- `npm.cmd run preview -- up`, `https://127.0.0.1:8443`; nunca mexer em `.env`/senhas e não usar `docker compose down -v`.
- O repositório e os HTMLs originais já estão disponíveis na própria branch. Execute as mudanças sem solicitar de novo o upload e apresente commits/PR/testes.
