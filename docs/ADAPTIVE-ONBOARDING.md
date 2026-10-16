# Etapa 2 — cadastro e perfil adaptativo nativos

Continuação da Etapa 1 na branch `feat/socialmei-native-integration`, PR #57. Entrada única: `frontend/socialmei-app.html`. Sem nova aplicação, protótipo, iframe, autenticação, migração ou conexão externa.

## O que funciona

O cadastro existente agora percorre seis etapas: contato, negócio, ofertas, rotina, ferramentas e revisão. Barbearia, perfumaria, costura/confecção, comércio, prestação de serviços e outro segmento compartilham um catálogo extensível em `frontend/scripts/business-profile.js`. O segmento sugere o tipo de oferta; o usuário pode combinar produtos e serviços independentemente da profissão.

As perguntas mostram serviços e categorias pertinentes ao segmento e permitem opções manuais. Agenda aparece para serviços; estoque para produtos. Encomendas, entregas e equipe são escolhas independentes. As ferramentas elegíveis acompanham essas capacidades. É possível voltar, pular etapas opcionais e revisar antes da confirmação. Pular indica necessidades não informadas, não uma afirmação definitiva sobre a operação do negócio.

Em **Configurações → Perfil e ferramentas**, é possível recuperar, editar e cancelar alterações. O nome de um negócio autenticado continua sob o fluxo existente de Configurações → Negócio; o onboarding não simula uma alteração no servidor. Cadastro remoto solicita o onboarding após a resposta bem-sucedida da autenticação existente e a recarga com sessão verificada. Login de contas existentes continua funcionando; essas contas podem preparar seu perfil em Configurações.

## Persistência explícita

O perfil adaptativo é **uma preferência local do navegador**, inclusive quando a conta está conectada. Isso é informado no formulário e em Configurações. Não há tentativa de escrita remota nem fallback de uma escrita remota que falhou.

- Contas autenticadas: chave e envelope contêm usuário e workspace verificados. A leitura exige também que o vínculo de navegador do `auth-store.js` corresponda à sessão atual. Trocar usuário ou workspace não recupera o perfil anterior; voltar ao mesmo vínculo recupera seu próprio perfil pelo mecanismo existente de arquivamento. Nenhuma credencial é incluída no perfil.
- Antes da sessão, sem sessão ou com falha de bootstrap: leitura e gravação indisponíveis. Uma identidade alterada durante o preenchimento não recebe o rascunho da identidade anterior.
- Modo público/local: seleção explícita da demonstração por e-mail de cadastro/login, ou prévia local. **Não equivale a autenticação ou isolamento de contas reais.** Quem compartilha o mesmo navegador pode acessar dados locais de demonstração. Sair remove a seleção da demonstração. Não utilizar informações pessoais ou comerciais reais nesse modo.
- Apenas a confirmação final salva o perfil. Dados incompatíveis ou corrompidos não são tratados como perfil recuperado. Falha de armazenamento mantém as respostas na revisão e não anuncia sucesso. Cancelar não substitui o perfil confirmado. Respostas ainda não confirmadas não são recuperadas depois de fechar/recarregar a página.

O contrato de backend existente foi conferido: `PATCH /auth/profile` aceita dados pessoais/nome do negócio e somente `cnpj`, `telefone`, `horario`, `pix`, `logo` em `configuracao_negocio` (`python-service/account_auth.py`). **Não aceita o perfil adaptativo estruturado.** Sincronizá-lo entre dispositivos/colaboradores requer contrato versionado, validação de capacidades, autorização por workspace, controle de concorrência e testes próprios. Nada disso foi alterado nesta etapa.

## Perfil compartilhado pelo frontend

`SocialMEIBusinessProfile.browserRepository().read()` fornece `{status, profile}`; ausência ou indisponibilidade produz `profile: null`. `save()` normaliza uma lista permitida de campos e exige confirmação, ofertas e nome. O perfil contém `businessName`, `segment`, `activity`, `offers`, `services`, `productCategories`, `capabilities`, `modules`, `version`, `completed`.

Este é o contrato reutilizável para Home, Produtos e Serviços. A aplicação desse perfil foi implementada posteriormente na [Etapa 3](NATIVE-PERSONALIZATION.md); as limitações do restante deste parágrafo descrevem a entrega original da Etapa 2. **As sugestões e ferramentas escolhidas ainda não cadastram itens, reorganizam a Home ou ativam/ocultam abas.** A interface deixa isso explícito. Não foram inventados produtos, serviços, preços, estoque, clientes, vendas ou agendamentos. Aplicar as preferências aos módulos é a próxima etapa, separada da conclusão do onboarding.

## Abrir e conferir

Na branch, execute um servidor estático na raiz (`python3 -m http.server 5500`) e abra `http://localhost:5500/frontend/socialmei-app.html`. Use **Criar conta** para o fluxo local identificado como demonstração. Para uma demonstração já aberta, use **Configurações → Perfil e ferramentas → Preparar meu perfil**. Evite servidor com configuração de produção; a configuração pública desta branch mantém canais externos desconectados.

Capturas reais do arquivo principal, sem mockups de imagem:

| Tela                       | Desktop claro                                              | Desktop escuro                                            | Mobile 390 claro                                          | Mobile 390 escuro                                        |
| -------------------------- | ---------------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------- | -------------------------------------------------------- |
| Ofertas                    | [Abrir](adaptive-onboarding/offers-1440-light.png)         | [Abrir](adaptive-onboarding/offers-1440-dark.png)         | [Abrir](adaptive-onboarding/offers-390-light.png)         | [Abrir](adaptive-onboarding/offers-390-dark.png)         |
| Revisão                    | [Abrir](adaptive-onboarding/review-1440-light.png)         | [Abrir](adaptive-onboarding/review-1440-dark.png)         | [Abrir](adaptive-onboarding/review-390-light.png)         | [Abrir](adaptive-onboarding/review-390-dark.png)         |
| Configurações              | [Abrir](adaptive-onboarding/settings-1440-light.png)       | [Abrir](adaptive-onboarding/settings-1440-dark.png)       | [Abrir](adaptive-onboarding/settings-390-light.png)       | [Abrir](adaptive-onboarding/settings-390-dark.png)       |
| Conta autenticada simulada | [Abrir](adaptive-onboarding/account-offers-1440-light.png) | [Abrir](adaptive-onboarding/account-offers-1440-dark.png) | [Abrir](adaptive-onboarding/account-offers-390-light.png) | [Abrir](adaptive-onboarding/account-offers-390-dark.png) |

As capturas de conta usam somente uma API simulada de sessão; não representam persistência de perfil no servidor.

## Verificação

Resultados locais: `npm test` — **185 passaram**; `CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser` — **88 estados e 23 fluxos passaram**. O teste focado `tests/adaptive-onboarding-browser.cjs` também passou sobre os últimos ajustes de foco, cancelamento e validação de armazenamento. `npm run format:check` e `git diff --check` passaram. Os cenários incluem quatro cadastros completos (barbearia, perfumaria, costura e negócio misto), edição/cancelamento, atividade manual, opcionais, falha de gravação, recuperação, troca de usuário/workspace e sessão ausente/indisponível. Capturas e verificações de geometria cobrem 320/390/1440 px, claro/escuro. A suíte existente continua cobrindo Oportunidades e as demais abas.

**Gate visual: PASS para o escopo da Etapa 2.** Capturas de ofertas, revisão, Configurações e sessão simulada foram conferidas em claro/escuro e desktop/mobile. As escolhas são legíveis e possuem estados selecionados; a revisão não cria registros nem promete sincronização. A personalização efetiva dos módulos continua pendente e é indicada como tal.

Nenhum agente utilizado. Skill aplicada: `interface-finish-gate`, com inspeção visual real das capturas e validação de estados, controles, navegação por teclado e movimento reduzido. Sem merge, deploy ou alteração de serviços externos.
