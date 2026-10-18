# Negócio — composição vertical para aprovação

> Registro da avaliação do protótipo. A composição foi posteriormente aprovada; a integração nativa na branch de desenvolvimento está em [ONBOARDING-BUSINESS-NATIVE.md](../../docs/ONBOARDING-BUSINESS-NATIVE.md). Merge e deploy permanecem sem autorização nesta rodada.

Protótipo isolado, sem integração oficial, merge ou deploy. Base local: `989e5dd`, com a mesma árvore do merge publicado `f07892f`. Branch: `feat/socialmei-native-integration`. A PR #57 já está encerrada; esta rodada não altera sua entrega em produção.

## Abrir e avaliar

Baixe [SocialMEI-Negocio-Avaliacao.zip](review/SocialMEI-Negocio-Avaliacao.zip), extraia e abra `SocialMEI-Negocio-Previa.html` no navegador. Escolha **Usar exemplo → Continuar**. `Comparacao-Negocio.html` apresenta as capturas lado a lado. O pacote inclui fontes, imagens, estilos e scripts; não requer bibliotecas, conexão ou instalação de Python. É uma cópia de avaliação gerada a partir do protótipo, não uma segunda implementação mantida.

No repositório, a prévia continua em `/experimental/onboarding-v3/`, servida localmente. Nenhum arquivo dentro de `frontend/` foi modificado.

## Diagnóstico e composição

A descoberta oficial separa seis áreas à esquerda e especialidades empilhadas à direita. Em 1440 px, com Beleza selecionada, a grade de áreas mede 293 px e as especialidades 442 px; a diferença entre os finais das colunas chega a 183 px, incluindo o título da lista. Reduzir gaps não elimina essa assimetria.

A proposta organiza a leitura em sequência:

1. Título editorial, explicação curta e nome do negócio.
2. Busca e seis áreas em três colunas no desktop, duas no tablet e uma no celular.
3. Especialidades abaixo, usando a mesma largura, com três, duas ou uma coluna conforme o espaço. Descrições completas e radios nativos.
4. Escolha atual, lista completa, produtos/serviços, detalhes opcionais e rodapé no fluxo do documento.

Somente a área usa cards. As especialidades são linhas de seleção, sem acrescentar um painel lateral. As linhas não recebem alturas fixas para preencher a viewport. O rodapé da etapa Negócio segue o conteúdo, sem sobreposição; as outras etapas mantêm sua navegação anterior.

### Densidade medida

Capturas de página completa, viewport de 1000 px de altura, mesmo nome e Barbearia selecionada. O “antes” é a aplicação oficial local; o “depois” é o protótipo. Cabeçalho e avisos de demonstração diferem, portanto altura total é uma medida descritiva, não um benchmark isolado de CSS.

| Largura | Altura antes | Altura depois | Organização depois                              |
| ------- | -----------: | ------------: | ----------------------------------------------- |
| 1440 px |      1549 px |       1250 px | Áreas 3×2; especialidades em três colunas       |
| 768 px  |      2025 px |       1491 px | Áreas e especialidades em duas colunas          |
| 390 px  |      2099 px |       2092 px | Linhas largas, uma coluna, descrições completas |

No mobile, o benefício principal é legibilidade e sequência, não redução significativa da rolagem. Não se oculta conteúdo para produzir uma tela artificialmente curta.

## Comportamentos

- Mantidos seis grupos e os 23 IDs de especialidades do modelo compartilhado, sem alterar esse modelo.
- Busca com acentos normalizados e aliases do seletor oficial, resultados vazios e alternativa para Outra atividade.
- Lista completa adicionada à prévia para representar a alternativa já existente no aplicativo.
- Explorar áreas ou pesquisar não muda a especialidade selecionada nem apaga respostas.
- Reescolher a mesma atividade preserva a oferta mista. Na prévia, escolhas explícitas de ofertas e dados preenchidos em etapas seguintes também são mantidos ao mudar de especialidade; sugestões iniciais continuam disponíveis antes dessas escolhas. Essa proteção deve ser validada contra o controlador nativo na integração, sem mudar contratos.
- Foco permanece no botão de área; não há `scrollIntoView` automático nessa seleção. Navegar por radios mantém foco no item escolhido. Encurtar a página pode naturalmente limitar a rolagem ao novo fim do documento.
- Entrada das especialidades em 180 ms, deslocamento de 4 px e opacidade parcial. Uma nova seleção cancela a animação anterior. Busca não reinicia a animação a cada letra. Movimento reduzido desativa o efeito.
- Dados apenas em memória, sem autenticação, armazenamento de perfil, API ou registros comerciais. O rodapé distingue a memória da prévia do perfil local do aplicativo.

## Testes executados

```sh
CAPTURE_NATIVE=1 node tests/onboarding-business-layout-browser.cjs
node tests/onboarding-business-layout-browser.cjs
node tests/onboarding-v3-browser.cjs
node --test tests/business-profile.test.cjs tests/repository.test.cjs
```

- **18 estados da composição passaram:** áreas com 2, 3 e 6 especialidades, 1440/768/390 px, claro/escuro. Geometria confirma especialidades abaixo da grade, mesma largura, descrições sem corte e ausência de overflow horizontal.
- **84 estados do fluxo completo e seis cenários passaram**, incluindo as outras etapas do protótipo. O teste do rodapé foi adaptado para verificar alcance e posição após o conteúdo em Negócio; as demais etapas conservam a exigência de ação fixa visível.
- **25 testes Node passaram:** catálogo/modelo, isolamento de armazenamento compartilhado e integridade do repositório. Isso não equivale a testar persistência autenticada na nova interface, pois a prévia não persiste.
- Testados: todos os 23 IDs pelas seis áreas; busca, lista completa, estado vazio, validação e foco no erro; Tab, Shift+Tab, Enter, setas dos radios; retorno de etapa, preservação de ofertas/serviços; seleções rápidas; movimento normal/reduzido; texto ampliado 200% em 320 px.
- Zero erros JavaScript, requisições externas/APIs ou gravações de perfil nos testes da prévia. Marcador de armazenamento oficial permaneceu intacto.
- Contraste calculado em 28 amostras de títulos, nomes, descrições e aviso por tema: mínimo **4,57:1 no claro** e **5,68:1 no escuro**. Amostragem, não auditoria integral WCAG.
- HTML autossuficiente validado em servidor HTTP local, sem buscar recursos adicionais. A política do Chromium gerenciado bloqueou navegação `file://`; abertura direta no Windows não foi executada neste ambiente.
- Capturas revisadas visualmente em desktop, tablet, mobile e ambos os temas. Não houve teste manual com leitor de tela ou dispositivo físico.

Também verificados sintaxe, formatação dos arquivos alterados e `git diff --check`. Nenhuma suíte de backend/produção foi executada; não houve mudanças nesses componentes.

## Capturas reais

Todas são capturas completas do navegador. No “antes”, o rodapé fixo permanece na posição da primeira viewport e pode aparecer sobre a composição da captura longa; isso não significa que o conteúdo era inacessível por rolagem.

| Largura | Antes claro                                                | Depois claro                                                     | Antes escuro                                              | Depois escuro                                                   |
| ------- | ---------------------------------------------------------- | ---------------------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------- |
| 1440    | [Abrir](screenshots/business-layout/before-1440-light.png) | [Abrir](screenshots/business-layout/after-beauty-1440-light.png) | [Abrir](screenshots/business-layout/before-1440-dark.png) | [Abrir](screenshots/business-layout/after-beauty-1440-dark.png) |
| 768     | [Abrir](screenshots/business-layout/before-768-light.png)  | [Abrir](screenshots/business-layout/after-beauty-768-light.png)  | [Abrir](screenshots/business-layout/before-768-dark.png)  | [Abrir](screenshots/business-layout/after-beauty-768-dark.png)  |
| 390     | [Abrir](screenshots/business-layout/before-390-light.png)  | [Abrir](screenshots/business-layout/after-beauty-390-light.png)  | [Abrir](screenshots/business-layout/before-390-dark.png)  | [Abrir](screenshots/business-layout/after-beauty-390-dark.png)  |

Outros estados: [duas especialidades](screenshots/business-layout/after-fashion-1440-light.png), [três especialidades](screenshots/business-layout/after-food-768-dark.png), [busca](screenshots/business-layout/search-1440-light.png), [sem resultados](screenshots/business-layout/empty-390-dark.png), [erro](screenshots/business-layout/error-390-dark.png), [texto ampliado](screenshots/business-layout/text-200-320-dark.png). A pasta contém também todas as combinações de 2/3/6 especialidades e temas.

## Integração pendente de aprovação

Após aprovação visual explícita: reorganizar apenas o HTML da etapa 2 em `frontend/socialmei-app.html`; adaptar os estilos correspondentes em `frontend/styles/business-profile.css`; ajustar motion/foco no seletor de `experience.js`. Preservar os IDs nativos, incluindo os identificadores de área em português, os eventos e a fonte de verdade do perfil. Não transplantar o controlador demonstrativo nem o HTML autossuficiente para a aplicação.

Validar novamente cadastro e edição, seis etapas, ofertas mistas, persistência/isolamento, temas, mobile, teclado e regressões do aplicativo real. Sem mudança de autenticação, schema ou integração remota. Aprovação deste protótipo não autoriza merge ou deploy.

Execução direta: nenhum agente. Uma skill: brainstorming, aplicada ao escopo delimitado e à composição solicitada.
