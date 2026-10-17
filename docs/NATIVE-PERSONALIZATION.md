# Etapa 3 — perfil aplicado ao negócio

Mesma branch `feat/socialmei-native-integration`, mesma PR #57 em Draft. Toda a experiência permanece em `frontend/socialmei-app.html`. Sem novo site, onboarding, store de perfil ou protótipo.

## Home e ferramentas

A Home mantém título, campo de comandos, estrutura, radar, prioridades, vendas e animações existentes. O perfil passa a orientar a frase de contexto e os atalhos: serviços/produtos/estoque, clientes, vendas, financeiro, oportunidades, Caixa e relatórios existentes. A ordem é contextual às ofertas e às ferramentas escolhidas, sem inventar urgência comercial. Até seis atalhos escolhidos são destacados; as demais funcionalidades continuam acessíveis pelo menu. Configurar atalhos abre o editor já existente em Configurações, sem refazer a conta.

Serviços e produtos podem coexistir em qualquer segmento. Estoque abre o catálogo de produtos físicos, com os controles existentes; Serviços abre o mesmo catálogo filtrado por serviço. A seleção não oculta abas nem altera permissões. Agenda, Encomendas, Entregas e gestão operacional de equipe ainda não têm módulos operacionais: aparecem como escolhas em desenvolvimento e avisos, sem links falsos. Convites e controles de conta existentes não foram alterados.

Na ausência de atendimentos, um perfil preenchido recebe uma orientação para preparar o catálogo, com ação funcional. Sem perfil, a Home mantém os atalhos anteriores e oferece preparar o perfil. Não foram criados indicadores, conversas, clientes, vendas ou compromissos com base na profissão. A demonstração pública conserva os exemplos anteriores e agora os identifica explicitamente na Home.

### Correção de inicialização comprovada

A verificação encontrou que contas autenticadas com módulos locais podiam herdar os exemplos comerciais de `DEFAULT_APP_DATA`. Agora a base inicial dessas contas contém listas vazias para Clientes, Produtos, Vendas e Financeiro, até que dados próprios sejam recuperados/carregados. A demonstração pública continua com seus exemplos. A correção não apaga nem reclassifica registros já persistidos e não altera autenticação ou contratos de backend.

## Produtos e Serviços

O catálogo apresenta sugestões a partir das escolhas de serviços e categorias do perfil; quando opcionais ficaram em branco, usa opções do segmento, sempre como sugestões. O filtro de tipo também filtra essas sugestões. Opções manuais continuam disponíveis.

- **Serviço:** Usar sugestão abre o formulário nativo com o nome escolhido e tipo Serviço. Preço fica vazio; estoque fica oculto e desabilitado. O registro confirmado utiliza estoque/mínimo nulos.
- **Produto:** uma categoria como Perfumes não é convertida em produto inventado. O formulário recebe o tipo Produto e a orientação com a categoria; o empreendedor informa o nome específico, preço, estoque e demais campos compatíveis.
- Abrir ou cancelar não salva nem faz requisição de criação. Salvar utiliza o fluxo nativo, inclusive o store remoto quando configurado, sem fallback local após recusa da API.
- Serviços já cadastrados não reaparecem como novas sugestões do mesmo nome/tipo. A comparação ignora diferenças de acentos, caixa e espaços. Categorias podem orientar vários produtos e continuam disponíveis até serem ignoradas.
- Ignorar e rever sugestões usam `ignoredSuggestions` no próprio perfil, com o mesmo escopo e versão compatível. Não há outro armazenamento de perfil.

O formulário/contrato atual suporta nome, tipo, preço, custo, estoque e mínimo. **Descrição livre e categoria persistida não são suportadas pelo contrato atual do catálogo** (`ProdutoFields`, em `python-service/catalog_data.py`); não foi criado campo que aparenta salvar uma informação que seria perdida. Custo/estoque/mínimo opcionais seguem os padrões existentes do formulário quando confirmados em branco. Preços nunca são preenchidos por sugestão.

## Estado e dados

`business-profile.js` continua sendo a fonte de verdade do perfil. A extensão adiciona funções puras para sugestões/ferramentas e um campo opcional de sugestões ignoradas; perfis anteriores são recuperáveis. `personalization.js` consome essa fonte, sem copiar respostas para outro cadastro.

Alterar o perfil atualiza a Home e as sugestões por evento e pela renderização das abas. Recarregar recupera as escolhas. Controles antigos são rejeitados se a identidade do navegador mudou. Regras de classificação e revisão de Oportunidades, inclusive a janela experimental de 24 horas, permanecem intactas.

O perfil é **local mesmo em conta autenticada**, isolado pelo vínculo usuário/workspace existente. Não sincroniza entre dispositivos ou membros. Registros comerciais seguem a configuração e a persistência de cada módulo. Os testes remotos usam uma API controlada, não produção; não demonstram integração nova com canais reais.

## Abrir e apresentar

Na raiz da branch: `python3 -m http.server 5500 --bind 127.0.0.1`. Abra `http://127.0.0.1:5500/frontend/socialmei-app.html`.

1. Faça o cadastro demonstrativo de uma barbearia, escolhendo serviços e ferramentas.
2. Na Home, confira contexto, atalhos e aviso de Agenda em desenvolvimento.
3. Abra Serviços e use uma sugestão. Confira nome/tipo/preço vazio; cancele e veja que nada foi cadastrado. Reabra, defina o preço e confirme.
4. Em Configurações → Perfil e ferramentas, experimente perfumaria, costura ou negócio misto. A Home e as sugestões acompanham as escolhas.
5. Ignore/reveja sugestões; abra uma categoria de produto e informe o produto específico. Nenhuma oferta vira registro sem confirmação.

## Capturas reais

Todas são do frontend oficial. A Home de barbearia foi capturada após o cadastro real do teste de onboarding; os demais perfis são fixtures sintéticas no repositório local de perfil. Conta remota utiliza sessão/API simuladas.

| Tela                                       | Desktop claro                                             | Desktop escuro                                           | Mobile 390 claro                                         | Mobile 390 escuro                                       |
| ------------------------------------------ | --------------------------------------------------------- | -------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------------------------- |
| Home após cadastro de barbearia            | [Abrir](personalization/home-barber-1440-light.png)       | [Abrir](personalization/home-barber-1440-dark.png)       | [Abrir](personalization/home-barber-390-light.png)       | [Abrir](personalization/home-barber-390-dark.png)       |
| Home de negócio misto                      | [Abrir](personalization/home-mixed-1440-light.png)        | [Abrir](personalization/home-mixed-1440-dark.png)        | [Abrir](personalization/home-mixed-390-light.png)        | [Abrir](personalization/home-mixed-390-dark.png)        |
| Sugestões de perfumaria                    | [Abrir](personalization/catalog-perfume-1440-light.png)   | [Abrir](personalization/catalog-perfume-1440-dark.png)   | [Abrir](personalization/catalog-perfume-390-light.png)   | [Abrir](personalization/catalog-perfume-390-dark.png)   |
| Sugestões de costura                       | [Abrir](personalization/catalog-tailoring-1440-light.png) | [Abrir](personalization/catalog-tailoring-1440-dark.png) | [Abrir](personalization/catalog-tailoring-390-light.png) | [Abrir](personalization/catalog-tailoring-390-dark.png) |
| Formulário nativo de serviço               | [Abrir](personalization/service-form-1440-light.png)      | [Abrir](personalization/service-form-1440-dark.png)      | [Abrir](personalization/service-form-390-light.png)      | [Abrir](personalization/service-form-390-dark.png)      |
| Formulário nativo de produto               | [Abrir](personalization/product-form-1440-light.png)      | [Abrir](personalization/product-form-1440-dark.png)      | [Abrir](personalization/product-form-390-light.png)      | [Abrir](personalization/product-form-390-dark.png)      |
| Conta autenticada sem registros comerciais | [Abrir](personalization/remote-profile-1440-light.png)    | [Abrir](personalization/remote-profile-1440-dark.png)    | [Abrir](personalization/remote-profile-390-light.png)    | [Abrir](personalization/remote-profile-390-dark.png)    |

## Validação e próxima etapa

Resultados locais: `npm test` — **194 passaram**; `CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser` — **88 estados e 24 fluxos passaram**. Os fluxos focados de personalização e contas também passaram após a correção final da base inicial autenticada. `npm run format:check` e `git diff --check` passaram. Cobertura: quatro cadastros e suas consequências, quatro perfis, serviços/produtos, formulário nativo, cancelamento, confirmação e recuperação local, ignorar/restaurar, edição, troca de identidade, ausência de perfil, conta autenticada vazia, recusa remota sem fallback, teclado/foco, ausência de erros JS e chamadas externas, 320/390/1440 claro/escuro. Regressões das Etapas 1/2 permanecem na suíte de navegador.

**Gate visual: PASS.** Capturas reais de Home, catálogo, formulário nativo e conta vazia foram inspecionadas. Desktop/mobile e claro/escuro mantêm hierarquia, seleções e controles legíveis, sem ações para módulos inexistentes. Zero agentes. Skill `interface-finish-gate` aplicada à revisão final. Sem merge, deploy ou alterações em AWS, banco, n8n, WAHA ou credenciais. Próxima etapa: Relatórios V2 no app oficial; integração ainda não iniciada. Sincronização de perfil e módulos futuros permanecem dependências explícitas.
