# SocialMEI.IA — candidata de testes públicos dos protótipos V8/V4

**Situação:** preparada no código, NÃO publicada; PR #100 em Draft. A homologação visual e a operação em um domínio isolado são passos pendentes.

## Escopo pronto no Git

- Entrada estática: `frontend/testes-publicos.html`.
- Oportunidades fiel ao HTML do usuário: `frontend/reference/Oportunidades-V8-original.html`.
- Divulgação fiel ao HTML do usuário: `frontend/reference/Divulgacao-V4-original.html`.
- Testes automatizados de links e ausência de chamadas externas: `tests/public-demo-entry.test.cjs`.
- Não depende de banco, FastAPI, Docker, n8n, WAHA, Meta, login nem tokens.
- Todos os dados editados nestes HTMLs ficam no `localStorage` **do navegador/origem**; o protótipo de Oportunidades preenche oportunidades fictícias automaticamente. Não armazenar clientes reais. Nada é sincronizado.
- **Não é a aplicação autenticada**: os protótipos não fazem CRUD do CRM, não entram na Caixa Unificada e não publicam mídia.

## Hospedagem segura — decisão necessária

A opção prioritária é uma **origem HTTPS dedicada à demonstração**, diferente do host do CRM. O ambiente AWS/team e seus cookies, dados e APIs não devem ser usados nem referenciados.

A publicação na GitHub Pages atual é aceitável **apenas depois** de confirmar a configuração do Pages, origem, visibilidade e que nenhum link ou configuração compartilha sessão com a instância real. A configuração remota de Pages não foi confirmada nesta revisão.

O conteúdo a disponibilizar nessa origem é um subconjunto estático e mínimo:

```text
/
├── index.html                      ← cópia da entrada frontend/testes-publicos.html
└── reference/
    ├── Oportunidades-V8-original.html
    └── Divulgacao-V4-original.html
```

**Não copie** `compose.team.yaml`, `python-service`, `database`, `deploy/team/private`, `.env`, arquivos de clientes nem segredos. Não publique o frontend autenticado como se estivesse conectado quando não houver API real.

### Antes de publicar (gate humano)

1. Verificar o SHA exato da PR #100 e resultado CI validate/browser/preview nesse SHA. Após novas edições, repetir a matriz; CI verde anterior não vale para o HEAD novo.
2. Testar entrada, links, navegação, teclado, mobile 320/390, desktop 1440, temas claro/escuro, rascunho, mídia local, Agenda e Termômetro, com dados **fictícios**.
3. Confirmar ausência de chamadas externas no DevTools Network; arquivos de referência possuem scripts inline e `localStorage`.
4. Confirmar que a origem HTTPS de testes é separada da origem de produção (inclusive armazenamento e cookies) e enviar `Cache-Control: no-store` para evitar versão velha.
5. Identificar responsável pelo suporte aos testadores e um canal de feedback sem solicitar dados de clientes.
6. Autorizar especificamente **destino, versão SHA e publicação estática**. Não acionar o workflow de staging/produção genérico.

### Depois da aprovação de publicação

- Disponibilizar somente os três arquivos na origem HTTPS aprovada.
- Verificar links do celular e desktop em navegação anônima.
- Testar que API, Postgres, WhatsApp, n8n, Facebook e Instagram reais não aparecem na Network.
- Registrar URL real somente depois de a hospedagem responder e um usuário sem login conseguir abrir.
- Rollback imediato: trocar a versão estática publicada pelo conjunto anterior (ou retirar a rota). Não deve haver rollback de banco, pois o pacote é inteiramente estático.

## Caminho da aplicação conectada — etapa distinta

A PR #100 possui integração nativa parcial para o CRM, com CI de navegador e API real no preview isolado; esse CI **não demonstra** paridade 1:1 com os protótipos nem torna os HTMLs originais conectados. Retomar a integração 1:1 somente com adapters autenticados, regras de escopo e migrations específicas autorizadas.

## Instagram — próxima etapa, somente preparação

`docs/INSTAGRAM-META-INTEGRATION-READINESS.md` consolida a proposta de login profissional, scopes mínimos, webhooks com assinatura, isolamento por workspace e outbox de publicações. Não executar OAuth, obter credenciais, configurar webhook público, publicar mídia, iniciar Direct nem habilitar workers nesta rodada. Primeiro homologar a demonstração pública e o modelo de contas/conexões em staging separado.

**Liberação:** a aprovação específica para usar uma origem pública não autoriza atualização do CRM na AWS ou merge da PR #100.

## Continuidade da candidata — 23/10/2026

O laboratório existente e os golden masters foram preservados. O ZIP revisado
`SocialMEI-Frontend-PR100-prototipos.zip` não está disponível nos arquivos do
workspace; não foi presumida equivalência com um ZIP desconhecido.

### Pacote reproduzível, sem publicação

```sh
node tools/package-public-demo.mjs
python3 -m http.server 5500 --bind 127.0.0.1 --directory test-results/public-demo
```

Abrir `http://127.0.0.1:5500/`. No Windows, usar `py` no lugar de `python3`.
A ferramenta copia somente três HTMLs autorizados, adiciona CSP `connect-src 'none'`,
aviso de demonstração e link de volta nas cópias distribuídas. Os originais do Git
permanecem byte a byte intactos. A cópia pública V8 recebe exclusivamente um ajuste
para quebrar a barra superior em linhas em celulares estreitos (sem esconder controles).
O manifesto registra SHA Git e hashes dos arquivos de entrada e saída. O diretório
não contém config.js, API, credenciais, mídia de usuário ou arquivos do CRM.

Workflow `Package public demonstration (no deployment)` somente gera artifact;
não possui permissão Pages/deploy nem publica automaticamente. O CI da PR também gera o mesmo artifact automaticamente. Conferir `manifest.json`
e baixá-lo pelo Actions do HEAD final. O workflow manual só aparece na interface
do GitHub quando registrado na branch padrão; não é necessário alterar main para
obter o artifact gerado pelo CI desta PR.
`_headers` é uma configuração de cabeçalhos para provedores compatíveis, não prova
que uma hospedagem aplicou esses cabeçalhos. GitHub Pages não lê `_headers`; a CSP
meta já bloqueia conexões, mas `frame-ancestors` exige cabeçalho no provedor escolhido.

### Destino proposto e aprovação pendente

Preferir **projeto estático separado**, por exemplo repositório dedicado de
laboratório com origem `socialmei-lab.github.io` (nome/disponibilidade não confirmados),
ou projeto estático equivalente com domínio HTTPS exclusivo. Não usar o Pages atual
do repositório sem verificar seu conteúdo e configuração: ele pode atender outra
versão e é uma origem compartilhada entre projetos do mesmo usuário GitHub.
Não criar hospedagem, repositório, DNS, secrets ou publicação nesta rodada.

O domínio escolhido não pode receber cookies com atributo Domain do CRM. A demo
usa localStorage da própria origem, não identifica contas; dois testadores no mesmo
perfil de navegador compartilham esses dados demonstrativos. Usar perfil/anônimo
separado quando necessário. Não inserir dados reais. Sem cookies de sessão, servidor,
analytics, formulários externos ou sincronização.

**Rollback:** manter artifact+manifest anterior; restaurar os arquivos desse artifact
ou retirar a hospedagem de testes. Nenhum banco/serviço deve ser restaurado ou reiniciado.
A autorização final deve indicar origem/provedor e SHA exato; não abrange merge ou AWS.

### Integração nativa separada

A composição extraída está também dentro das abas oficiais, sem iframe. CRM de
Oportunidades usa o store autenticado existente; valores, notas e retornos continuam
locais e isolados por usuário/negócio/oportunidade. Divulgação reutiliza o repositório
de rascunhos e a preparação existente. Thumb JPEG limitado é local; mídia bruta não
é sincronizada nem incluída no backup. Agenda compartilhada depende de API habilitada;
simular3publicações permanece desabilitado quando não há transação segura disponível.
Não confundir estas limitações com as capacidades do protótipo público independente.

### Proposta concreta de primeira hospedagem (não executada)

**Cloudflare Pages, projeto novo `socialmei-lab`**, usando exclusivamente o artifact
estático desta PR. Nome/disponibilidade e URL `*.pages.dev` ainda não confirmados;
nenhum projeto foi criado ou conta conectada. A origem precisa ser independente
inclusive do GitHub Pages atual. Não configurar domínio próprio nem DNS nesta fase.

Após autorização de origem+SHA: criar o projeto de upload estático, conferir manifesto,
subir somente o conteúdo de `test-results/public-demo/`, verificar os cabeçalhos e
repetir smoke sem login em desktop/celular. Sem comandos de API, containers ou banco.
Para atualizações futuras, pode-se configurar build GitHub com comando
`node tools/package-public-demo.mjs` e saída `test-results/public-demo`, somente depois
de autorizar essa vinculação. Não usar outro workflow de produção do repositório.

Rollback do projeto novo: desabilitar a hospedagem se for a primeira publicação;
nas seguintes, promover o deployment estático anterior e conferir seu manifesto.
O CRM atual permanece no endereço existente, sem alteração de autenticação.
