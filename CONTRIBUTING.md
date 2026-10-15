# Como contribuir com o SocialMEI.IA

O objetivo é permitir que qualquer integrante contribua sem precisar editar produção diretamente.

Escolha o [ambiente](docs/ENVIRONMENTS.md), localize a área no [mapa da estrutura](docs/PROJECT-STRUCTURE.md) e defina o contrato antes de alterar. O mesmo mapa explica como adicionar endpoint, tela, teste ou migration sem trocar o framework ou duplicar regras no n8n.

## Ambiente local

Antes de criar sua branch:

```bash
npm ci
npm run setup
npm run dev
```

O ambiente padrão é local e isolado. Veja [docs/ONBOARDING.md](./docs/ONBOARDING.md).

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
- `refactor/` — manutenção da implementação sem mudar contratos ou comportamento
- `ui/` — visual/interface
- `docs/` — documentação
- `chore/` — manutenção
- `infra/` — Docker, Caddy, servidor/deploy

## Antes do PR

- rode `npm test` e `npm run format:check`;
- rode `npm run test:browser` para validar frontend (veja [DEVELOPMENT.md](./DEVELOPMENT.md));
- execute os testes Python e de backup quando alterar essas áreas;
- teste o app em desktop/mobile se alterou UI;
- valide a Caixa Unificada se mexeu no atendimento;
- revise SQL se alterou banco;
- rode `docker compose config --quiet` se alterou infraestrutura;
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

## Revisar uma refatoração

Separe formatação de mudanças de lógica quando possível. Compare a baseline com o resultado, explique o que foi simplificado e o que permaneceu por compatibilidade. Mantenha testes de erro, conflito, isolamento e recuperação; não ajuste expectativas apenas para tornar o CI verde. Migrations históricas e exports n8n não devem ser reescritos por preferência de estilo.
