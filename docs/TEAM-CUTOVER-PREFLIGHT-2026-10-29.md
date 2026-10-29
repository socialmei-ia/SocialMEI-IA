# Pré-corte SocialMEI Team — 29/10/2026

O candidato de código de frontend V25, Instagram, WhatsApp e n8n foi integrado
pela PR #143 na branch release/socialmei-functional-integrations-20261026,
commit 4e374aa4772221e8869ccc0dda1e5394fbc46207.

**O merge foi apenas no GitHub. Não houve deploy da AWS.**

## Inspeção automatizada somente leitura

Na instância Ubuntu, no checkout /home/ubuntu/socialmei-team, com o candidato
Git já presente, use:

    python3 tools/team-cutover-inspect.py --target team --expected-sha 4e374aa4772221e8869ccc0dda1e5394fbc46207

A ferramenta usa apenas Git read-only, Docker inspect e SELECT em transação
PostgreSQL read-only. Não lê mensagens, prompts, tokens, n8n executions ou
dados pessoais. Não modifica Docker, Git, banco, Meta, WAHA ou Caddy.
NÃO compartilhar saídas completas de docker inspect, variáveis de ambiente
ou arquivos privados. Somente o JSON sanitizado é seguro para a revisão.

Inspeciona automaticamente:

- checkout limpo e SHA completo esperado;
- Team API, Team gateway, Team PostgreSQL, n8n e WAHA ativos;
- saúde da API, portas privadas e redes Docker;
- autenticação, flags de ingresso e envio Instagram;
- flags WhatsApp e sentimento com segredo e allowlist explícitos;
- engine WAHA declarada (WEBJS/GOWS);
- ledger de migrações e tabelas de 032 e 033;
- falhas inseguras como PostgreSQL na rede de automação.

A propriedade preflight_unblocked significa apenas ausência dos bloqueios
sintáticos/operacionais inspecionados. Não comprova fluxo real, suporte da Meta,
segurança completa, backup ou autorização de envio.

## Bloqueio de publicação que deve ser resolvido

Os scripts antigos instagram-release-prepare.py e v25-release-publish.py foram
concebidos para migrações 001–031. O candidato agora adiciona 032 e 033 e
novas flags, redes e volumes. Não forçar migrações extras nesses scripts
nem usar o workflow genérico manual-production-deploy.yml: ele atualiza o
stack legado compose.yaml, não o Team compose.team.yaml.

Antes de publicar:

1. Conferir o runtime instalado, labels, imagens, Caddy ativo, redes e flags.
2. Fazer backup verificado do banco e das imagens/configurações, com
   restauração ensaiada e rollback planejado.
3. Validar 032 e 033 em banco descartável; manter as migrações aplicadas imutáveis.
4. Usar publicador Team adequado, que preserve os serviços e não faça down,
   prune, reset de volumes ou substituição de credenciais.
5. Validar login, origem HTTPS, Caixa por workspace, ingestão e recibos.
6. Testar Direct com conta autorizada e um único proprietário de envio.
   Não publicar rascunho duplicado de 17 nós do n8n.
7. Testar WAHA com número autorizado; checar WEBJS vs GOWS, assinatura HMAC,
   catálogo por workspace e remetente único.
8. Ativar sentimento apenas com allowlist de negócio, segredo interno e
   rede privada homologada. Não habilitar respostas automáticas por essa ponte.

Esta entrega é preparação, não faz deploy ou testes de entrega real.
