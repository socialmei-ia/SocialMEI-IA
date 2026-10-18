# Relatórios V2.1 — integração para revisão

Data: 18/10/2026. Branch: `feat/reports-v21-native`.
HEAD inicial: `09ac45297962d7c56b32f7d05747c92f1d2a1faf` (protótipo aprovado).
`main` remota conferida: `a045b157b8ea65230c2f2b9e0a90b8e819a14375`.
A branch do protótipo não existia no remoto; seu commit local foi preservado.

## Resultado

A experiência aprovada está em `frontend/socialmei-app.html`, na navegação
**Relatórios**, com sidebar e header oficiais. Não há shell experimental,
sandbox, dados do Ateliê Aurora ou bloqueios de rede na aplicação. Os exemplos
das capturas existem somente nos testes com API interceptada.

- Composição e estilos consolidados em `reports-v2.css`, restritos a Relatórios.
  Indicadores, abas, situação, ranking e histórico mantêm a organização aprovada.
- Datas visíveis em formato brasileiro, inclusive títulos antigos do histórico,
  detalhes e impressão. Datas ISO, chaves, versão, snapshots e títulos salvos não
  foram migrados. Busca aceita datas brasileiras e o título ISO anterior.
- O seletor mobile usa **Período selecionado**. O intervalo completo fica abaixo,
  ligado ao campo por `aria-describedby`; não depende de texto cortado no select.
- Faturamento destacado no KPI; o gráfico mantém evolução, eixos, tooltip e tabela,
  sem apresentar outro total competindo com o indicador.
- Textos de apoio principais em 14 px no celular e metadados em 13 px, alvos de
  toque preservados e números ajustados também em 320 px.
- `report-motion.js` integra somente a interpolação visual aprovada, com estado
  separado por fonte e limpeza na troca de identidade. Linhas e pontos acompanham
  a transição; tema não reinicia o desenho; movimento reduzido termina sem animar.
  Atualizar o mesmo SVG durante a transição não a congela. Os alvos dos pontos se
  adaptam ao espaçamento, sem sobrepor vizinhos em séries densas.
- Geração continua local, com três operações reais. Fechar durante a preparação
  cancela antes da persistência. O único ajuste em `dialogs.js` é a notificação
  de fechamento do modal de Relatórios; os demais diálogos mantêm seu fluxo.
- Dados e avisos do histórico continuam acessíveis em detalhes expansíveis.
  Falhas de fonte/armazenamento abrem os avisos automaticamente; avisos transitórios
  de carregamento voltam a recolher quando as fontes ficam disponíveis.

## Preservação e testes

O motor financeiro (`data-and-backup.js`), snapshots/CSV (`report-data.js`),
contratos, autenticação, configuração e perfil comercial não foram alterados.
Não há alteração em AWS, migrations, serviços ou armazenamento remoto.
CSV segue a sanitização nativa e usa as mesmas datas internas. PDF continua
**Imprimir / salvar PDF** pelo navegador, com os mesmos valores do snapshot.

Comandos de verificação:

```sh
npm test
npm run format:check
CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser
node tests/reports-v21-browser.cjs
```

Resultados: **214 testes Node**, formatação aprovada e **88 estados/26 fluxos**
na suíte global de navegador, sem erros JavaScript. V2: 12 layouts; V2.1 nativa:
oito layouts (incluindo 320 px); protótipo: dez layouts/15 grupos de verificações.
A regressão global também passou em 484 estados de layout e 936 pontos de gráfico.
A regressão de atualização repetida do SVG foi confirmada falhando na versão
anterior e passou com a correção. Revisão `interface-finish-gate`: **PASS**.

A suíte global inclui V2 e a nova `reports-v21-native-browser.cjs`, além das
regressões de cadastro/login, onboarding, personalização, Oportunidades e gestão.
Ela verifica modo local/API, falhas, histórico por identidade/workspace, CSV/PDF,
snapshots, privacidade, teclado e movimento reduzido. A suíte histórica do
protótipo permanece isolada e recebeu somente uma guarda para reutilizar o
markup integrado sem duplicar os controles de período.

Os testes de origem dos dados agora abrem o detalhe antes de ler sua informação;
as verificações de fonte foram mantidas. O teste de ordem dos scripts reconhece
o helper de movimento antes da UI, mantendo a validação dos scripts clássicos.
Durante QA foram corrigidos conflitos da cascata antiga em números a 320 px,
texto auxiliar e avisos que permaneciam abertos após carregar.
O teste do indicador acompanha os 240 ms aprovados na V2.1, preservando as
verificações de foco e ausência de fade. Uma ação de teclado da Home passou a
usar o controle diretamente e aguardar sua abertura, sem mudanças na Home.

Capturas reais e resultados: [reports-v21-native](reports-v21-native/), em
**1440, 768 e 390 px**, claro/escuro; 320 px também exercitado. Cabeçalho e
navegação são os oficiais. Todos os registros usados em QA são sintéticos.

## Limites e próxima ação

Histórico permanece local, isolado por usuário/negócio/fonte, sem sincronização
entre dispositivos. Não foi criado backend novo. Os testes são Chromium com
emulação de viewport, não homologação em Safari ou aparelho físico.

Revisão pela skill `interface-finish-gate`, sem agentes. Aguardamos autorização
específica para merge/publicação; a Calculadora V3 não foi iniciada.
