# Segurança — SocialMEI.IA

O SocialMEI.IA é um projeto acadêmico em desenvolvimento, mas a infraestrutura deve seguir práticas básicas de produção.

## Nunca publique

- `.env`;
- `.pem`;
- chaves privadas SSH;
- senhas;
- tokens;
- chaves de API;
- credenciais do n8n;
- backups/dumps sensíveis.

Use somente placeholders em `.env.example`.

## Acesso individual

- use contas individuais sempre que aplicável;
- não compartilhe conta root da AWS;
- não compartilhe chave SSH privada;
- não use login administrativo do banco como credencial de automação;
- conceda Docker apenas a responsáveis pela infraestrutura.

Veja [docs/ACESSOS.md](./docs/ACESSOS.md).

## Rede

- PostgreSQL permanece sem 5432 pública;
- serviços web preferem HTTPS via Caddy;
- novas portas públicas exigem justificativa e revisão.

## Alterações sensíveis

Faça backup e planeje rollback antes de migrations destrutivas, remoção de volumes, troca de credenciais, mudança da chave de criptografia do n8n ou alterações de rede.

A chave de criptografia do n8n não deve ser trocada de forma improvisada, pois protege credenciais salvas.

## Credencial exposta

Se encontrar um segredo exposto:

1. não publique o valor em issue;
2. avise responsáveis por canal privado;
3. identifique consumidores;
4. planeje e execute rotação;
5. atualize dependências;
6. valide serviços;
7. remova o segredo de locais indevidos.
