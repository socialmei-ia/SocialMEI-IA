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
