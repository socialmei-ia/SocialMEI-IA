# Integração V25

Fonte: SocialMEI-Frontend-v25.zip SHA256 d7c93b73f2a75f979ed78fdc8c84af90a2a0f2df14f5e820eb89f23a698d0c35

O HTML/CSS do app e das telas Oportunidades/Divulgação são iguais ao pacote V22 original. Mantêm-se os adaptadores e proteções da versão funcional. As alterações visuais novas estão em entrada.html/entrada.css e no controlador da entrada. Não copiar config.js local nem versões antigas dos stores do ZIP para o servidor.

A branch integra as propostas132–135 por ancestralidade, sem duplicar seus commits ou mesclar PRs no GitHub/main. Nenhum deploy executado. Recuperação remota usa o contrato de código existente; login por WhatsApp não foi implementado no backend e permanece indisponível no modo remoto.

Os hashes de entrada.css e hero-wall.js nos testes de fidelidade passam a usar os bytes do ZIP V25 aprovado, mantendo comparação estrita. Os hashes dos assets, sections-anim e o CSS original do app continuam inalterados.

## Verificação

475 testes backend com PostgreSQL16 descartável,337Node,286 estadosV22 e18 capturasV25 em1440/768/390 claro/escuro aprovados. Cadastro/login/onboarding e recuperação nativa testados com API controlada, incluindo ausência de token e bloqueio do login WhatsApp remoto. Confirmação de e-mail real depende de SMTP/worker; nenhum envio externo foi realizado.

A revisão corrigiu a privacidade descrita na landing para o modo remoto; os textos locais demonstrativos permanecem no modo local. CI deve ser conferido no último HEAD da PR. Produção permanece inalterada.

## Preparação na VPS: hotfix local preservado

O operador confirmou API/gateway650ee5e, ledger001–026 e restauração do backup real em PostgreSQL temporário sem rede, limitado a384MB. Na cópia,027–031 passaram. Isso não aplica migrations no banco oficial.

O preparador aceita opcionalmente `--preserved-caddy-sha256` somente para a única alteração não staged em deploy/team/Caddyfile, com hash exato e arquivo regular não montado por API/gateway/Caddy público. Qualquer outra alteração, symlink, hash divergente ou montagem continua bloqueando. O arquivo não é resetado/stashado: cópia privada verificada e política ficam no recibo. Os overlays, fonte Caddy realmente montada, credenciais e flags permanecem preservados.

A candidata de aplicação continua1b28e84eacc5a782504b810114ba19775a1df58e, com CI aprovado; esta alteração adicional é operacional. Preparar não faz build, SQL ou deploy. Não usar o publicador genérico antigo para o corte: suas premissas de26 migrations/integrações desligadas não atendem este runtimeconnect e precisará de fluxo dedicado revisado.
