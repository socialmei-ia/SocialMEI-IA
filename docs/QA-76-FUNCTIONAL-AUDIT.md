# QA funcional — Issue #76

Referência: PR #75 em `79f33107b0d441c9b0d91cacbde8ebc8cbf93bda`.
Branch de correções: `fix/qa-functional-76`. SHA final e checks próprios constam na PR Draft; o CI aprovado da #75 foi conferido, mas não substitui o CI desta branch.

Esta é uma candidata para revisão/testes controlados. Nenhum merge, deploy ou acesso AWS/n8n/Meta/banco real foi realizado. #72 permanece separada e #73 aberta.

## Prioridades e problemas confirmados

| ID  | Prioridade | Reprodução / causa                                                                                                                                                                                                                                                                                  | Correção e prova                                                                                                                                                                                                                                                                                                      |
| --- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F01 | P1         | Iniciar pagamento ou duplicação na venda, fechar o drawer e abrir outro formulário antes da resposta. O callback remoto chamava `openRecord` incondicionalmente e reabria a venda sobre o formulário novo. Encontrado também no ensaio com API/DB reais descartáveis.                               | Atualizar somente o drawer ainda aberto e correspondente; ações iniciadas na lista preservam a abertura usual se o contexto não mudou. O callback do próximo frame respeita fechamento em curso. Regressão com resposta controladamente atrasada falhou antes e passou três vezes depois para pagamento e duplicação. |
| F02 | P1         | Focar coluna financeira, atualizar o gráfico antes do próximo frame e pressionar End. A substituição remove o nó focado; restauração somente em rAF deixa o teclado no body. A suíte inicial também falhou em tooltip invisível; a ordem temporal exata desse primeiro incidente não foi capturada. | Se o gráfico focado foi substituído e o foco está no body, atualizar/restaurar no MutationObserver antes do próximo evento. Sem roubar foco de outro controle, sem alterar cálculos ou animações. Teste com frame retido falhou antes, passou três vezes depois; estabilização passou duas vezes.                     |
| F03 | P2         | Em simulação explicitamente habilitada, carregar contas com papel viewer. Criar conta era desabilitado, mas simular continuava habilitado. A API já rejeitava a escrita, portanto não foi demonstrado bypass de autorização.                                                                        | Botão segue os papéis owner/admin/member do backend e status informa somente leitura. Regressão viewer falhou antes e passou após a correção.                                                                                                                                                                         |
| F04 | P2         | Automações em 320/390 px: a grade de duas colunas deixava “Área”/“Situação” em 47 px; o rótulo podia quebrar letra por letra apesar de não haver overflow. Captura e medição real de fonte/valor reproduziram a falha.                                                                              | Grade de uma coluna somente no mobile, rótulos sem quebra e controles inline; desktop preservado. Regressão compara largura do rótulo+valor com célula em 320/360/390 px e ambos os temas.                                                                                                                            |
| F05 | P1         | O autofocus adiado do modal podia substituir o foco já escolhido pelo usuário entre Tab e Shift+Tab. O CI reproduziu a falha; teste com frame controlado falhou antes da correção.                                                                                                                  | O callback verifica abertura, época do modal, fechamento e foco já dentro do diálogo antes de aplicar autofocus. Três repetições da regressão e matriz de 160 estados passaram.                                                                                                                                       |
| F06 | P2         | Na simulação opt-in, segurar uma leitura de contas/histórico, registrar a segunda simulação e liberar a leitura antiga: o histórico volta de duas entradas para uma e a confirmação some. Regressão controlada falhou antes da correção.                                                            | Invalidar gerações de leitura ao iniciar uma mutação; leituras antigas não substituem resultados novos. Contas, chave de idempotência e contratos permanecem os mesmos.                                                                                                                                               |

**P0:** nenhum defeito P0 confirmado dentro do escopo testado. Isso não equivale a homologação de segurança ou de produção.

Não houve redesign; apenas a grade mobile de Automações foi ajustada pontualmente. Sem mudança de autenticação, contratos de API, persistência, cálculos, esquema/migration ou flags padrão.

## Matriz de funcionamento e limites reais

| Área                       | Evidência executada                                                                                                                                                                                                                      | O que ainda impede funcionamento pleno                                                                                                                                                 |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Login/cadastro             | Cadastro real via UI, seis etapas, cookie de sessão, logout/login e recuperação de registros na API/DB descartáveis; suítes de contas/CSRF/isolamento.                                                                                   | Recuperação por e-mail/OAuth e homologação operacional têm contratos próprios; não foram simulados como implementados. Nome remoto do workspace é somente leitura no onboarding atual. |
| Perfil / Configurações     | Segmentos/capacidades, edição, identidade, temas, preferências e isolamento pelos testes existentes; navegação e estados vazios na matriz.                                                                                               | Perfil comercial e preferências ainda locais ao navegador, inclusive na conta conectada; sem sincronização entre dispositivos.                                                         |
| Clientes                   | Criação real ligada ao workspace; suíte remota cobre edição/conflito/exclusão e vínculo por ID; DB cobre isolamento.                                                                                                                     | Contexto de conversas depende de uma fonte autorizada; histórico comercial não inventa conversas.                                                                                      |
| Produtos/serviços          | Produto real a 30 reais, estoque7, venda de2 e estoque5; catálogo cobre serviço sem estoque, sugestões, edição, versão e falhas.                                                                                                         | Sugestões são locais e exigem confirmação; não há catálogo/estoque real pré-carregado.                                                                                                 |
| Vendas                     | Criação e pagamento reais no DB descartável; estoques e recarga conferidos. Suítes cobrem cancelamento, versões, importação, idempotência e recuperação.                                                                                 | Pagamento é registro manual; não comprova recebimento por instituição nem entrega.                                                                                                     |
| Financeiro                 | Entrada12.35 editada para15.25 em API real, reload e novo login; receita da venda não duplicada. Suítes de conflito, indisponibilidade, importação e recuperação.                                                                        | Não há integração bancária. Causa do timeout histórico da #73 continua não confirmada.                                                                                                 |
| Caixa Unificada            | Conta remota sem conversas fictícias; estado vazio, demo marcada, filtros, conversa/notas locais e teclado nos testes existentes.                                                                                                        | Contrato autenticado de canais, ingestão/reconciliação e envio real não homologados. Resposta local não é mensagem entregue. Endpoint legado não reativado.                            |
| Relatórios                 | Venda paga de 60 reais lida do DB real descartável e CSV gerado; suítes de períodos, fonte, histórico/snapshot, CSV seguro, PDF/impressão, teclado e movimento.                                                                          | Métricas sem fonte ficam indisponíveis; histórico/snapshots locais não sincronizam. Impressão não é serviço remoto de PDF.                                                             |
| Divulgação / Instagram     | Editor local e mídia apenas em preview; duas contas fictícias,503 controlado, mesma seleção/chave ao repetir, chave diferente ao alterar conteúdo ou conta, viewer e histórico. Backend/DB testa autorização, isolamento e idempotência. | Publicação real bloqueada: faltam conta/instância autorizadas, mídia privada, worker, transporte/callback/reconciliação e homologação. Nenhum token Meta ou webhook foi utilizado.     |
| Automações                 | Rotinas locais, habilitação e teste/rascunho simulado, matriz visual e regressões existentes.                                                                                                                                            | Não executam workflows n8n externos. Preferência não equivale a integração ativa.                                                                                                      |
| Agenda/encomendas/entregas | Interesse/módulos futuros identificados na configuração.                                                                                                                                                                                 | Não são módulos operacionais completos; não demonstrados como disponíveis.                                                                                                             |

## Execuções e evidências

- Node: 258 testes na referência; suíte e formatação reexecutadas nas correções. Resultados finais constam na PR.
- Backend + PostgreSQL16 descartável: **160/160**, sem skips. Nenhuma porta pública de DB.
- Instagram Python: **13/13** (5 simulação +8 protocolo), com transportes HTTP Python bloqueados. Flags ausente/vazia/inválida/disabled falham503 antes de acessar banco/sessão.
- Contratos Python do repositório:25 aprovados;5 testes de gateway opt-in executados separadamente e aprovados.
- `functional-audit-browser.cjs`: **160 estados** =10 áreas ×320/390/768/1440 ×claro/escuro ×vazio/amostra. Verifica overflow, navegação, flags padrão, Tab/Shift+Tab/Enter/Escape e cancelamento sem criar registros. Captura80 estados de amostra na navegação nativa.
- `chart-focus-browser.cjs` e `sale-payment-dialog-browser.cjs`: regressões determinísticas dos estados assíncronos; sem aumentar timeout ou remover assertivas.
- `instagram-integration-browser.cjs`: duas contas,503, repetição, mudança de conteúdo/conta e papel viewer; somente mocks na mesma origem, sem upload binário.
- `functional-api-browser.cjs`: ensaio adicional **sem mock de API**, com HTTPS/Basic, FastAPI e PostgreSQL reais descartáveis. Cadastro/onboarding, cliente/produto/venda, estoque7→5, pagamento, financeiro12.35→15.25, reload, relatório60/CSV e logout/login passaram, sem erros JS ou requests externos. Instagram default503 foi verificado. Não prova publicação real.
- Logs sanitizados e dados exclusivamente fictícios: `test-results/functional-audit/`, `test-results/functional-api/`, `test-results/integration/`; os resultados da regressão completa e artefato do CI estão na PR.

A medição de geometria e as verificações de foco da suíte de estabilização consultam e avaliam o DOM na mesma execução de JavaScript. Assim não retêm handles de colunas removidas pelo refresh inicial entre a consulta e a leitura. Os limites de 44 px, a ordem das colunas e as assertivas de teclado foram preservados; nenhum timeout foi aumentado. A falha de foco modal do CI foi corrigida no produto, não contornada no teste.

O CI também apresentou timeout ao aguardar a confirmação de uma repetição Instagram por teclado. Foram adicionados diagnósticos sem dados privados e uma assertiva explícita de foco. A leitura atrasada que sobrescreve a confirmação foi reproduzida separadamente (F06); a sequência exata do incidente remoto não foi capturada. Os resultados do HEAD final constam na PR, sem atribuir aprovação aos runs anteriores que falharam.

O ensaio inicial da API teve ajustes **de fixture/roteiro**, não bugs do produto: faltava `auth.mode=remote` na configuração temporária; a autenticação remota abre diretamente a tela de login; o nome do workspace remoto é intencionalmente desabilitado no contrato atual. Esses incidentes não foram classificados como falhas do sistema. O ensaio foi reiniciado em contexto novo após corrigir o ambiente/roteiro.

O stack descartável foi removido depois do ensaio. Configurações padrão do repositório não foram habilitadas. Os registros/credenciais fictícios não pertencem a um ambiente publicado.

## Reprodução

Regressão local (sem serviços de produção):

```sh
npm ci
npm test
npm run format:check
CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser
```

O caminho explícito do Chromium é opcional, usado neste ambiente. O CI utiliza o browser instalado pelo Playwright.

Para repetir o ensaio opcional com API real, prepare um sandbox HTTPS **loopback**, banco descartável migrado e configuração remota dos quatro stores +auth. Use o Compose/guia de desenvolvimento existentes, nunca configuração ou dados de produção. O arquivo JSON privado de fixture contém `origin`, `httpCredentials` e `registration.password` fictícios. Não é incluído no repositório nem nas evidências.

```sh
SOCIALMEI_QA_CONFIG=/caminho/privado/fixture.json node tests/functional-api-browser.cjs
```

O script rejeita destinos fora de localhost/loopback e bloqueia requests externos do navegador. Ele cria dados fictícios; só deve rodar em banco descartável. A configuração/env de infraestrutura não é alterada pelo script.

## Pendências e portões humanos

- **P0 operacional:** não habilitar publicação/transportes externos sem autorização, credenciais por workspace, contratos e homologação próprios. Piloto externo não pode ser usado como atalho para isso.
- **P1:** #73 permanece aberta; edição15.25 passou neste ensaio, mas não determina a causa do timeout histórico. Preservado diagnóstico de falha da #74.
- **P2 investigativo:** timeout de cadastro pós-reload em `account-browser.cjs:622` não foi confirmado como corrigido. Só investigar com reprodução/evidência; não relaxar testes.
- Homologação em celular físico, leitor de tela e aprovação visual da equipe **não realizadas**. Os testes atuais são automação Chromium e revisão de capturas, não substituem essas etapas.
- Perfil compartilhado, canais reais, ferramentas futuras e integração operacional precisam de planejamento/contratos próprios. Não foram abertos como novas frentes nesta correção.
- Revisar a nova PR Draft e a dependência da #75 antes de qualquer integração. O diff contra main inclui a candidata #75 enquanto ela não estiver integrada; não reaplicar #69/#70/#71/#74 individualmente.
- Qualquer staging/produção requer plano separado de migrações, backup/restore, credenciais e rollback, além de autorização. Esta auditoria não verificou a AWS.
