# Como contribuir com o SocialMEI.IA

O objetivo é permitir que qualquer integrante contribua sem precisar editar produção diretamente.

## Fluxo recomendado

```bash
git switch main
git pull origin main
git switch -c feat/nome-da-tarefa
```

Depois das alterações:

```bash
git status
git add .
git commit -m "feat: descreva a mudança"
git push origin feat/nome-da-tarefa
```

Abra um Pull Request para `main`.

## Branches

- `feat/` — funcionalidade
- `fix/` — correção
- `ui/` — visual/interface
- `docs/` — documentação
- `chore/` — manutenção
- `infra/` — Docker, Caddy, servidor/deploy

## Antes do PR

- teste o dashboard em desktop/mobile se alterou UI;
- valide a Caixa Unificada se mexeu no atendimento;
- revise SQL se alterou banco;
- rode `docker compose config` se alterou infraestrutura;
- atualize documentação;
- explique como testar;
- explique rollback se houver impacto em produção;
- confira que nenhum segredo entrou no diff.

## Infraestrutura

```text
branch → PR → revisão → responsável pela VPS → validação → aplicação
```

Veja [docs/DOCKER.md](./docs/DOCKER.md) e [docs/ACESSOS.md](./docs/ACESSOS.md).

## Nunca faça commit de

`.env`, `.pem`, chave privada SSH, senhas, tokens, chaves de API, credenciais exportadas ou dumps sensíveis.
