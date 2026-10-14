# Apresentação do repositório

O README funciona como entrada para conhecer o produto, explorar as telas e chegar aos guias. Esta revisão altera somente documentação e imagens; não modifica o frontend nem publica serviços.

## Referências consultadas

Consulta em 14/10/2026. Referências de organização, sem copiar textos, marca ou assets:

| Referência                                                                                                                                                                  | O que foi observado                                                        | Adaptação no SocialMEI                                                        |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| [Twenty](https://github.com/twentyhq/twenty)                                                                                                                                | Tour do produto com imagens por capacidade e links para aprofundar.        | Tour com seis áreas, capturas próprias e guia associado a cada tela.          |
| [Appwrite](https://github.com/appwrite/appwrite)                                                                                                                            | Navegação por tópicos e separação entre produto, instalação e arquitetura. | Atalhos de entrada e caminhos distintos para explorar, executar e contribuir. |
| [GitHub Docs: seções recolhíveis](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/organizing-information-with-collapsed-sections) | `details`/`summary`, incluindo abertura inicial com `open`.                | Home aberta por padrão, outros módulos e perguntas frequentes expansíveis.    |

## Assets e edição

- `docs/assets/readme/banner-*.svg`: composição autoral, duas cores de tema e duas proporções para desktop/mobile. Fonte de sistema e SVG estático, sem scripts, animação obrigatória, fontes remotas ou assets de terceiros.
- `docs/assets/readme/{explore,start,contribute}-*.svg`: imagens dos atalhos. Os links ficam no HTML do README, não dentro dos SVGs; assim funcionam no GitHub.
- `docs/assets/screenshots/`: capturas próprias da demonstração em `92d4c20`, com dados fictícios e chamadas externas bloqueadas. Preservar a origem e a data ao substituir imagens.
- O banner ilustra relações entre módulos. Não é um screenshot nem uma alegação de integração viva.

Edite os SVGs diretamente, preservando `viewBox`, títulos e descrições. Ao trocar um asset, confira ambos os temas, os dois formatos de banner e os caminhos do README. Não coloque credenciais, cookies, QR ou dados de contas reais em screenshots.

## Interações compatíveis

O tour, as perguntas e a documentação avançada usam elementos nativos. A navegação usa âncoras e links para arquivos reais. `picture` seleciona o tema e, no banner, a variante mobile. O badge de CI aponta para a branch `main` e não comprova saúde do servidor.

Não há botões falsos de login, widgets externos, contadores, iframes ou JavaScript no README. As ações levam a conteúdo do repositório; elas não executam comandos ou alteram dados.

## Conferência

Confira referências locais, âncoras, contraste/leitura e abertura de cada `details` em desktop/mobile. Valide a formatação com `npm run format:check` e os contratos do repositório com `npm test`. A aparência final do GitHub tem sua própria sanitização e estilos; uma prévia local serve para checar a estrutura, não para prometer uma renderização idêntica.
