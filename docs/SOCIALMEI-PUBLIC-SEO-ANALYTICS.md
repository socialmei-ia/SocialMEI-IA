# SEO, descoberta e métricas da página pública — SocialMEI.IA

**Escopo:** implementação dos sete itens citados no vídeo enviado: favicon, meta tags, dados estruturados, arquivos de descoberta, Search Console, Google Analytics 4 e Microsoft Clarity. A página pública é `/sobre.html`. O painel existente em `/` e `/frontend/socialmei-app.html` permanece funcional e não é monitorado por essas novas métricas.

## 1. Favicon

O ícone SVG `frontend/assets/socialmei-favicon.svg` substitui a referência anterior a um PNG não encontrado no repositório. A página pública e o aplicativo usam o ícone e o gateway já publica `/assets/*`.

## 2. Meta tags e imagem social

`frontend/sobre.html` possui `title`, descrição, `canonical`, Open Graph (WhatsApp, redes sociais), Twitter Card, `og:locale` e imagem PNG real 1200 × 630 em `/assets/socialmei-og.png`, reaproveitada do banner existente do projeto. Testar as URLs públicas e o compartilhamento após implantação. O aplicativo autenticado recebeu `noindex,nofollow`; dados privados não devem aparecer em resultados de busca.

O endereço canônico provisório é `https://socialmei-ia.54-94-213-7.sslip.io/sobre.html`. Ao migrar para domínio próprio, atualizar **em conjunto** canonical, Open Graph, JSON-LD, sitemap, robots, llms.txt e propriedade Search Console. Não criar duas versões canônicas concorrentes.

## 3. Schema Markup

O JSON-LD da página pública descreve somente `WebSite`, `Organization` e `WebApplication`, com nome, URL e categoria de negócio. Não publica avaliações, ratings, preços, promessas de plano gratuito ou `Offer` não confirmados. A marcação não garante rich result no Google. Validar em [Rich Results Test](https://search.google.com/test/rich-results) e em [Schema Markup Validator](https://validator.schema.org/).

## 4. Sitemap, robots e llms

O gateway serve `/sitemap.xml`, `/robots.txt`, `/llms.txt` e `/sobre.html` a partir de `frontend/`. O sitemap lista **apenas a página pública**, enquanto robots impede a descoberta solicitada de caminhos privados `/api/`, `/internal/`, `/webhooks/`, `/media/` e a rota duplicada `/frontend/`. **Robots não é controle de segurança**: autenticação, assinaturas de webhook e regras de proxy continuam obrigatórias. `llms.txt` é informativo e voluntário, não fornece permissões de treinamento nem acesso a dados.

## 5. Google Search Console — requer proprietário do site

1. Acessar [Google Search Console](https://search.google.com/search-console/) com uma conta controlada pelo projeto.
2. Como `sslip.io` não pertence ao projeto para configuração de DNS, **preferir propriedade do tipo prefixo de URL** usando `https://socialmei-ia.54-94-213-7.sslip.io/`. Para domínio próprio com DNS sob controle, pode-se usar propriedade de domínio.
3. Selecionar o método de verificação **arquivo HTML**. Obter o arquivo real fornecido pelo Google, colocar na pasta `frontend/` e incluir somente o arquivo de verificação correspondente, com rota explícita no gateway. **Nenhum token fictício deve ser gerado**. Alternativamente usar outro método permitido e validado pelo Google.
4. Somente após colocar o arquivo no domínio correto, clicar em Verificar. Enviar `https://socialmei-ia.54-94-213-7.sslip.io/sitemap.xml` na seção Sitemaps.
5. Inspecionar `/sobre.html`, conferir resposta HTTP 200, canonical, robots, indexabilidade e erros de rastreamento. A indexação pode depender do Google e não acontece apenas por adicionar arquivos.

**Estado:** o código está preparado, mas ainda **não há evidência de verificação da propriedade ou sitemap enviado**.

## 6. Google Analytics 4 — desativado até configuração e consentimento

Na conta Google Analytics do projeto, criar a propriedade e fluxo Web da página pública; copiar o **Measurement ID** `G-...`. Somente após revisão de privacidade e autorização, configurar o `config.js` público efetivamente montado no gateway com:

```js
siteMetrics: {
  enabled: true,
  ga4MeasurementId: "G-XXXXXXXXXX",
  clarityProjectId: "",
}
```

O código `frontend/scripts/site-metrics.js` não faz download de scripts externos até o visitante clicar em **Aceitar métricas** na página `/sobre.html`; escolha é revogável por **Preferências de privacidade**. Ad storage, personalização e uso publicitário continuam negados. O script não é incluído no dashboard autenticado. IDs são identificadores públicos de propriedade, não credenciais ou segredos; não adicionar API keys ao `config.js`.

## 7. Microsoft Clarity — desativado até configuração e consentimento

Criar um projeto em [Microsoft Clarity](https://clarity.microsoft.com/), usando apenas a URL pública. Copiar o Project ID e colocá-lo em `siteMetrics.clarityProjectId` depois da revisão de privacidade. O rastreamento **não roda em páginas de CRM, Caixa, clientes, financeiro ou mensagens** para reduzir a exposição de dados pessoais e empresariais. Avaliar a necessidade de termo/política de privacidade, ocultação de informações e retenção de dados antes de habilitar. Se o consentimento for retirado após carga de scripts, a página é recarregada; excluir cookies de terceiros e dados já coletados pode exigir controles adicionais dos provedores.

## Gate de implantação

- O checkout da AWS e o Caddyfile privado montado no gateway contêm alterações locais e **não devem ser substituídos** diretamente pelo arquivo do Git. Antes de atualizar, confirmar backup restaurável, SHA de origem, Caddy efetivo e mounts, reconciliar a rota `@public_discovery` e preparar rollback da API/gateway.
- Conferir `GET /sobre.html`, `/robots.txt`, `/sitemap.xml`, `/llms.txt`, `/assets/socialmei-favicon.svg`, `/assets/socialmei-og.png` no host **público**, com Content-Type correto. Confirmar que `/api/v1/`, webhooks e painel seguem protegidos.
- Em ambiente de teste, inspecionar a aba Network: **0 requisições para Google/Clarity antes do consentimento**, 0 em telas autenticadas mesmo com consentimento da página pública e IDs configurados. Confirmar rejeição e revogação.
- Não ativar IDs reais na configuração de produção, verificar Search Console, submeter sitemap, ou afirmar indexação/publicação até operador autorizado executar essas etapas no domínio e nas contas correspondentes.

**Estado desta entrega:** código e testes no GitHub. Sem acesso a contas Google/Microsoft, mudança de AWS ou envio de dados de visitantes.
