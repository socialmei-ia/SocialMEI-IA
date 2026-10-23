# Demonstração V8/V4 — Cloudflare Pages

**Preparada, não publicada.** PR #100 permanece Draft. Nenhuma conta Cloudflare,
publicação, domínio, DNS, cookie do CRM ou conexão externa foi criada.

## Candidata e limites

- Origem proposta: **https://socialmei-lab.pages.dev/**, projeto `socialmei-lab`.
  Nome e disponibilidade ainda não confirmados. Se indisponível, escolher outro
  nome e revisar a allowlist do smoke antes de publicar.
- `wrangler.public-demo.toml`: configuração local de build/saída; não cria recursos.
- A demonstração distribui os HTMLs originais V8/V4 e uma entrada estática.
  **Não é a aplicação autenticada**: não faz CRUD do CRM, não recebe mensagens,
  não publica mídia nem usa FastAPI, PostgreSQL, Meta, n8n ou WAHA.
- Dados são fictícios e locais à origem/navegador. Pessoas usando o mesmo perfil
  do navegador compartilham os exemplos locais. Usar janela anônima ou perfil
  separado; nunca inserir clientes, mensagens ou mídia privados.
- Golden masters permanecem intactos. As cópias recebem CSP, aviso/backlink e,
  no V8, somente contenção da barra superior em larguras até 980 px.
- O ZIP revisado `SocialMEI-Frontend-PR100-prototipos.zip` não está disponível;
  a origem utilizada é o Git, sem presumir equivalência com esse ZIP.

## Build e conferência local

Em checkout limpo do **SHA aprovado**, com Node 22:

```sh
npm ci
npm run demo:build
npm run demo:verify -- test-results/public-demo SHA_APROVADO
python3 -m http.server 5500 --bind 127.0.0.1 --directory test-results/public-demo
```

No Windows, usar `py -m http.server ...` em lugar de `python3`. Abrir
`http://127.0.0.1:5500/`. O servidor Python serve para inspeção visual; não aplica
`_headers`. O teste de navegador do projeto usa servidor local que aplica esses
cabeçalhos e a página 404, sem backend.

O pacote tem **oito arquivos**: `index.html`, os dois HTMLs em `reference/`,
`manifest.json`, `_headers`, `404.html`, `robots.txt` e `README.txt`.
O manifesto informa SHA, checkout limpo/sujo, hashes dos originais e dos arquivos
entregues. A verificação rejeita arquivos extras, symlinks e alterações de bytes.
Não copiar o repositório inteiro, `.env`, config.js, banco ou infraestrutura.

O CI gera artifact `SocialMEI-public-demo-SHA` e executa o smoke em origem local
com os cabeçalhos reais. O workflow manual de empacotamento também só gera artifact;
não tem credenciais nem permissão de deploy. Baixar o artifact do HEAD verde e
conferir o manifesto. A versão publicada deve ter `workingTreeDirty: false`.

## Cabeçalhos e isolamento

Cloudflare Pages interpreta `_headers`: CSP com scripts inline autorizados por
hash, `connect-src 'none'`, `form-action 'none'`, `frame-ancestors 'none'`,
`Cache-Control: no-store`, `nosniff`, `no-referrer`, COOP/CORP `same-origin` e
Permissions-Policy restritiva. A CSP meta também bloqueia conexões na inspeção local.
`404.html` impede fallback de SPA para URLs como `/api/` e `/.env`. `robots.txt` e
meta noindex desencorajam indexação, mas **não são controle de acesso**.

Não habilitar Analytics/Beacon, Rocket Loader, transformação de HTML ou injeção de
scripts: os hashes e o smoke devem detectar qualquer diferença do artifact.
Não configurar Functions, redirects para o CRM, domínio personalizado, login ou
cookies. Não vincular um domínio que receba cookies Domain do CRM. O subdomínio
`pages.dev` dedicado mantém outra origem e outro armazenamento.

## Aprovação necessária e publicação posterior

Apresentar ao proprietário: provedor **Cloudflare Pages**, origem proposta acima,
SHA completo, CI no SHA, hashes/manifesto e este rollback. A autorização precisa
cobrir **criação do projeto e publicação estática**. Não abrange AWS ou merge.
A conta Cloudflare ainda não está conectada neste ambiente. Utilizar conexão
segura da plataforma ou login local autorizado; não enviar token/senha pelo chat.

**Os comandos abaixo são procedimento posterior à aprovação, não foram executados.**
Com autenticação autorizada e checkout limpo do SHA aprovado:

```sh
npx wrangler@4.152.0 pages project create socialmei-lab --production-branch beta
npm run demo:build
npm run demo:verify -- test-results/public-demo SHA_APROVADO
npx wrangler@4.152.0 pages deploy test-results/public-demo --project-name socialmei-lab --branch beta --commit-hash SHA_APROVADO
npm run demo:smoke -- https://socialmei-lab.pages.dev/ SHA_APROVADO
```

Usar upload direto; nenhuma vinculação GitHub automática é necessária. Confirmar
no painel que `beta` é a branch de produção do projeto isolado. Não confundir com
`main` do SocialMEI. Registrar ID do deployment, SHA, URL e resultado do smoke.
Não publicar se CI, integridade ou isolamento falharem.

O smoke exige o artifact local verificado do mesmo SHA, compara seus hashes e
manifesto com a hospedagem, testa cabeçalhos/404, rejeita cookies e redirecionamentos
para outra origem. Em seguida repete os fluxos V8/V4 com Playwright, em seis larguras
(320/360/390/768/1024/1440), claro/escuro, apenas armazenamento local do contexto
descartável. Não envia gravações nem autentica no CRM. Instalar Chromium/Playwright
conforme `npm run test:browser`. Não executar contra produção.

## Atualizar e reverter

1. Nova versão: novo SHA revisado, CI verde, build limpo e manifesto arquivado.
   Publicar só após autorização da versão/destino; repetir o smoke no link real.
2. Manter deployment anterior e seu artifact/manifesto; registrar o ID antes de
   cada atualização. Não excluir deployments anteriores durante a homologação.
3. Falha: no painel Pages, promover novamente o deployment anterior; conferir o
   manifesto e rodar o smoke com seu SHA e artifact. Alternativamente, reenviar
   exatamente o artifact anterior à mesma branch `beta`.
4. Primeira publicação sem versão anterior: retirar a hospedagem/projeto de testes.
   Não tocar em API, banco, DNS do CRM, AWS, n8n ou WAHA.

Rollback estático não apaga nem migra rascunhos locais do navegador. Para comparação
limpa, usar perfil anônimo; não limpar armazenamento de usuários sem explicar.

## Compartilhar e recolher feedback

Compartilhar **somente depois** de o link real passar no smoke, com aviso:
“Demonstração com dados fictícios; nada é enviado nem sincronizado. Use exemplos.”
O proprietário escolhe seu canal de retorno; nenhum formulário externo ou analytics
foi integrado. Pedir um registro curto por problema:

- Tela e ação (Lista/Termômetro/Semana; Story/Feed/Reel/Rascunhos/Agenda).
- Dispositivo, navegador, largura aproximada e tema.
- Passos, resultado esperado e observado; captura somente com dados fictícios.
- SHA visível em `manifest.json` e se ocorre também em janela anônima.

## Aplicação nativa e Instagram: entregas separadas

As abas oficiais permanecem em `frontend/socialmei-app.html`, sem iframe. CRM usa
store autenticado; valor, nota e retorno V8 continuam locais por usuário/negócio/
oportunidade. Divulgação usa seus rascunhos; mídia bruta não é sincronizada. Isso
não transforma os HTMLs públicos em operações autenticadas.

O laboratório Instagram será uma PR dependente, desligado por padrão e restrito a
ambiente descartável. Não faz parte do pacote estático. Consulte
`docs/INSTAGRAM-META-INTEGRATION-READINESS.md` para pendências de integração real.
