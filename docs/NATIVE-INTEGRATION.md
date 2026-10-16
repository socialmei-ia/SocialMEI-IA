# Integração nativa — etapa 1: Oportunidades

Branch `feat/socialmei-native-integration`, criada diretamente da `main`. A aplicação é `frontend/socialmei-app.html`; não há hub, iframe ou página de apresentação nova. PRs #54, #55 e #56 foram consultadas e não foram alteradas. Esta etapa integra a aba Oportunidades; não conclui onboarding/personalização/Relatórios V2.

## O que funciona no app principal

- Oportunidades na navegação oficial, com shell, sidebar, temas e sistema de modais existentes.
- Análise local do texto informado, com classificação provisória, evidências literais, critérios, informações faltantes, limites e próximo passo. Editar invalida o resultado; limpar/recarregar descarta texto e análise.
- Fila calculada a partir dos exemplos fictícios que já existem na Caixa, somente após **Explorar conversas fictícias da Caixa**. Acompanhamento comercial, pós-venda/suporte e recusas aparecem separados. Relato de pedido sem defeito explícito é apresentado como pós-venda, sem modificar a categoria do motor.
- Revisão humana com motivo, reordenação e restauração da recomendação automática, somente em memória. Não grava no CRM nem muda mensagens, cadastro ou status da conversa.
- **Abrir na Caixa Unificada** usa a conversa existente no app. **Consultar cliente vinculado** abre o painel nativo somente quando existe um ID local compatível; sem associação nova por nome nesta funcionalidade.

Os motores `intent-engine.js` e `priority-engine.js` são cópias byte a byte da PR #55, commit `37655e5`. Não foram reescritos ou recalibrados. Seus 20 cenários e regressões foram reaproveitados com imports para `frontend/scripts/`. Vocabulário finito, ambiguidades e necessidade de supervisão continuam presentes. Sem probabilidades. A janela de 24 horas permanece experimental; os exemplos originais não têm datas completas e não recebem recência inventada.

## Limites e contrato pendente

O contrato legado de mensagens fornece nome/canal/texto e ID da mensagem, mas agrupa conversas por nome/canal. Isso não basta para identificar com segurança uma oportunidade por cliente/workspace. Por isso **nenhuma mensagem do conector alimenta a nova fila**. Contas autenticadas/remotas e stores de clientes remotos não herdam os exemplos. Começam no estado vazio, com acesso a Configurações → Integrações; a análise manual local continua disponível.

A origem demonstrativa é um snapshot dos quatro exemplos já existentes, capturado antes da restauração de mensagens locais/remotas. Uma conversa removida, um ID reutilizado por outra pessoa/canal ou uma conversa que recebeu `remoteId` é excluída do recorte; a interface não abre detalhes antigos de uma linha invalidada. Mensagens de empresa, notas e rascunhos não viram intenção do cliente. Nenhum novo cliente/mensagem fictícia foi acrescentado à aplicação.

Integração real futura exige contrato validado com identidade externa estável da conversa, workspace resolvido pela sessão, vínculo explícito de cliente, autoria/direção e timestamps originais, autorização de leitura e estados de erro/permissão. Deve haver confirmação de contexto de pós-venda e revisão dos erros antes de habilitar prioridade real. Revisões compartilhadas exigirão persistência versionada e autorização no backend; esta etapa não simula esse salvamento.

Na configuração pública **desta branch**, `n8nMessagesUrl` fica `null` para impedir conexão automática ao endpoint legado ao abrir o app. Não foram modificados serviços n8n/WAHA, AWS, credenciais, banco ou autenticação. Reativar um canal real exige configuração autorizada; o botão de integrações não finge conectá-lo.

## Abrir e conferir

Na raiz do checkout desta branch:

```sh
python3 -m http.server 5500 --bind 127.0.0.1
```

Abra `http://127.0.0.1:5500/frontend/socialmei-app.html`, use a entrada demonstrativa já existente e selecione **Oportunidades** no menu. O estado inicial é vazio. Para avaliar a fila com exemplos, ative a demonstração explicitamente. O cadastro e o fluxo de entrada existentes foram preservados.

Capturas reais dentro do app: [desktop claro](native-integration/queue-1440-light.png), [desktop escuro](native-integration/queue-1440-dark.png), [mobile claro](native-integration/queue-390-light.png), [mobile escuro](native-integration/queue-390-dark.png). Estado vazio de conta autenticada em teste controlado: [desktop](native-integration/account-empty-1440-light.png) e [mobile](native-integration/account-empty-390-dark.png). [Revisão humana](native-integration/review-390-light.png).

## Verificação

- `npm test`: **171 passaram**, incluindo motores, cenários comerciais, identidade/origem da análise e regressões Node.
- `CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser`: **88 estados e 22 fluxos passaram**, com a suíte existente e novo fluxo nativo incorporado. O teste novo usa a configuração pública local da branch; a conta remota é API simulada, sem chamadas externas.
- O fluxo nativo verifica menu real em 320/390/1440, claro/escuro; vazio; análise e negação; evidências; revisão sem persistência; foco/Escape; Caixa; cliente; conteúdo malicioso como texto; reset; invalidação por mensagem remota e bloqueio em conta remota. Nenhum recurso de `prototypes/` é carregado pelo app.
- Skill `interface-finish-gate`: revisão visual, contraste com tokens existentes, hierarquia mobile, estados, controles reais, foco e movimento reduzido. Nenhum agente utilizado.

**Gate visual: PASS.** Os controles têm efeitos verificáveis; a lista mobile tem hierarquia própria, sem métricas inventadas; o foco, Escape e as evidências foram testados. `npm run format:check` e `git diff --check` passaram. Resultados finais e SHA estão na PR. As capturas foram conferidas visualmente. Sem merge ou deploy; aprovação de produção continua separada.

## Próximas etapas autorizadas, ainda não implementadas

2. Onboarding progressivo no cadastro existente, perfil extensível, edição posterior e persistência coerente com os contratos atuais; sem autenticação paralela.
3. Aplicar o perfil a sugestões e módulos/Home, sem cadastrar produtos ou serviços automaticamente.
4. Ler integralmente o arquivo anexado `SocialMEI-Relatorios-Prototipo-V2 (1).html` e integrar componentes/animações na seção oficial, preservando cálculos, filtros/exportações e acessibilidade. O anexo foi localizado, mas não foi analisado nem incorporado nesta etapa.
5. Validar consistência entre as funcionalidades e estados vazios de contas sem canais. O conector real de Oportunidades continua bloqueado até existir contrato seguro.
