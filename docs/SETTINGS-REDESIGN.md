# Configurações: revisão visual e funcional

Revisão de 13/10/2026, iniciada na base `66b6a9d0fba4ce4785cd66d2f4c4dffee906b4a8`. Esta etapa altera Configurações e o editor de temas relacionado. Não muda contratos de API, regras de acesso, migrations ou integrações. A publicação desta revisão exige uma etapa própria; commit e CI não comprovam runtime na AWS.

## Problemas encontrados

- O checklist de preparação ocupava o topo de todos os painéis, antes da tarefa escolhida.
- Nove destinos sem agrupamento e a mesma apresentação genérica para perfil, segurança e aparência.
- Duas ações de salvar: uma no cabeçalho e outra no formulário.
- `accountSettingsNotice` estava na seção Automações, embora o código de Configurações o atualizasse. O aviso correto não aparecia em Configurações e o texto de simulação podia ser sobrescrito em Automações.
- Segurança dizia que autenticação externa estava indisponível mesmo em conta remota. A alteração de senha real já existia em Conta.
- Dados afirmava que o financeiro era local; a fonte efetiva depende da configuração de cada store.
- Equipe e Plano usavam descrições de demonstração também no ambiente conectado.

## Direção aplicada

Uma abertura editorial curta, seguida de controles de trabalho. O azul existente continua indicando seleção e ação; superfícies neutras, espaçamento e alinhamento fazem a separação principal.

- Cabeçalho “Seu espaço, do seu jeito.” e miniatura que usa a paleta efetivamente selecionada.
- Navegação em Pessoal, Negócio e Organização, com ícones existentes, seleção visível e rolagem horizontal no mobile.
- Perfil com superfície de contraste, iniciais reais e monograma decorativo oculto para tecnologia assistiva.
- Checklist recolhido em `details`, mantendo progressão e as seis ações originais.
- Uma ação nativa de salvar por formulário, junto dos campos; validação, CSRF e persistência permanecem nos handlers existentes.
- Nome, iniciais e miniatura atualizados após salvar, sem substituir o formulário nem apagar a confirmação.
- Segurança reutiliza o formulário real de Conta quando a autenticação remota está habilitada. Na demonstração mantém controles indisponíveis e informação explícita.
- Dados identifica separadamente Clientes, Produtos, Vendas e Financeiro como API ou navegador. Isso descreve o modo configurado, não confirma disponibilidade ou sincronização do servidor.
- Exportação, importação e limpeza mantêm comportamento e confirmação existentes. A limpeza é apresentada como local; não se confunde com exclusão de conta remota ou restauração PostgreSQL.
- Editor de temas com campos, grupos e rodapé mais claros; criação, validação de contraste, aplicação, importação e exportação continuam no mecanismo existente.

As regras de Configurações substituem o bloco original no CSS; o editor teve seletores existentes revisados no lugar. A dívida geral do CSS monolítico não foi resolvida nem ampliada com uma segunda folha de overrides.

## Referências consultadas

O MCP do 21st não estava disponível neste ambiente. A descoberta de plugins não encontrou uma integração 21st instalável. Foram consultadas páginas públicas e conteúdo de registry; nenhuma chave anterior foi reutilizada. A adaptação permanece em HTML, CSS e JavaScript puro, sem copiar componentes React, assets ou marca.

| Fonte                                                                                                                                                        | Ideia adaptada                                                                                                   | Limite da observação                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| [21st: guia de componentes de Configurações](https://mcp.21st.dev/blog/react-settings-page-components)                                                       | Agrupamento de assuntos, diferença entre salvar explicitamente e aplicar imediatamente, ação destrutiva separada | Guia textual; não é medição de motion ou referência de runtime                                       |
| [21st: Settings Tabbed Sections](https://21st.dev/@felipemenezes098/components/settings-1) e [registry público](https://ui.flexnative.com/r/settings-1.json) | Índice separado do conteúdo e superfície contínua por assunto                                                    | Página parcialmente extraída; estrutura/conteúdo do registry consultados, código React não integrado |
| [21st: categoria Settings](https://21st.dev/community/components/s/settings)                                                                                 | Biblioteca de padrões para organizar preferências                                                                | Extração principalmente do catálogo; não afirmar revisão visual completa de todos os componentes     |
| [Attio: Account settings](https://attio.com/help/reference/account-settings/account-settings)                                                                | Separar informações pessoais de organização                                                                      | Documentação atual consultada; SocialMEI mantém seu salvamento explícito                             |
| [Attio: Personalize appearance](https://attio.com/help/reference/account-settings/personalize-attios-appearance)                                             | Aparência tratada como parte do espaço de trabalho                                                               | Guia público, sem acesso autenticado ao aplicativo Attio                                             |
| [Coss UI](https://coss.com/ui)                                                                                                                               | Composição com campos, grupos e navegação previsível                                                             | Destino atual do link Origin UI consultado; sem instalar biblioteca                                  |

A página de preferências do Linear não pôde ser acessada nesta rodada; não foi usada como evidência. Não houve cópia de screenshots de referência nem comparação de FPS com sites externos.

## Motion e acessibilidade

- Troca de painel: opacity e translateY de 8px, `--motion-medium` (340ms).
- Seleção e hover: `--motion-fast` (150ms), sem blur em campos operacionais.
- `prefers-reduced-motion` elimina a animação do painel. Não há WebGL, loop permanente ou nova dependência de motion.
- Navegação conserva `aria-current`, botões nomeados, foco existente e acionamento por teclado.
- Checklist e alteração de senha usam disclosure nativo; inputs conservam rótulos, autocomplete e limites.
- Botões principais e campos têm alvo mínimo de 44px na área revisada. Nem todos os controles legados do aplicativo foram convertidos nesta etapa.

## Verificação reproduzível

```bash
npm test
npm run format:check
npx playwright install chromium
npm run test:browser
node tests/stability-browser.cjs
node tests/visual-browser.cjs
node tests/settings-browser.cjs
```

Se utilizar o Chromium instalado pelo sistema, defina `CHROMIUM_EXECUTABLE` antes dos comandos de navegador.

`settings-browser.cjs` verifica os nove painéis, modos local e remoto controlado, onze larguras (360–1920px) e cinco condições de tema: claro, escuro, automático claro/escuro e custom. Também confere envio único do perfil, CSRF da fixture, persistência local, atualização da identidade, checklist por teclado, aplicação de tema, editor sem overflow, senha remota disponível e origem dos quatro módulos. Os testes bloqueiam requisições externas e não usam contas ou segredos de produção.

O workflow `Repository checks` inclui essa suíte e guarda as capturas em `frontend-regression`. As capturas de comparação representam o frontend real com dados controlados, não uma sessão autenticada no servidor.

Na validação local: 63 testes Node, 88 estados e 16 fluxos da regressão existente, 825 estados da matriz geral, 22 estados de geometria da Home e 22 do Financeiro, além de 990 estados específicos de Configurações passaram. Foram capturados os nove painéis em claro/escuro, desktop/mobile, local/conectado, com zero `pageerror`. A regressão de contas teve uma espera de reload corrigida para consultar `window.SocialMEIAuth?.remote` sem lançar `ReferenceError` enquanto o script ainda carrega; as condições de logout e isolamento continuam exigidas.

## Limites e próxima etapa

Não houve deploy, consulta ao banco vivo, ativação n8n/WAHA, abertura de cadastro ou implementação de recuperação por e-mail. O Docker local não dispõe de daemon para reproduzir a pilha; o CI tem seu ambiente isolado de validação.

Depois da aprovação visual e do CI, preparar publicação apenas do gateway, com novo backup e imagem anterior preservada. A implantação anterior em `66b6a9d` continua sendo a última confirmada até essa operação. A revisão com leitor de tela real, alto contraste do sistema e celular físico continua complementar à matriz automatizada.
