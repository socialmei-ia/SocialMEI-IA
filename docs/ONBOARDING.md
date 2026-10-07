# Onboarding da equipe — SocialMEI.IA

> Em poucos minutos, um integrante deve conseguir descobrir onde trabalhar, como testar e quem precisa aplicar mudanças de infraestrutura.

## Comece aqui

| Quero fazer | Vá para |
|---|---|
| Abrir o dashboard | https://socialmei-ia.github.io/SocialMEI-IA/ |
| Alterar interface | `frontend/socialmei-dashboard.html` + `index.html` |
| Trabalhar com automações | n8n + `n8n-workflows/` |
| Entender o banco | [BANCO-DE-DADOS.md](./BANCO-DE-DADOS.md) |
| Entender acessos | [ACESSOS.md](./ACESSOS.md) |
| Adicionar serviço Docker | [DOCKER.md](./DOCKER.md) |
| Entender arquitetura | [ARQUITETURA.md](./ARQUITETURA.md) |
| Alterar API Python | `python-service/` |

## Links do ambiente

- GitHub: https://github.com/socialmei-ia/SocialMEI-IA
- Dashboard: https://socialmei-ia.github.io/SocialMEI-IA/
- n8n: https://socialmei.54-94-213-7.sslip.io/home/workflows
- pgAdmin: https://db.54-94-213-7.sslip.io *(login necessário)*

## Fluxo padrão

```bash
git switch main
git pull origin main
git switch -c feat/minha-alteracao

# altere e teste

git status
git add .
git commit -m "feat: descreva a mudança"
git push origin feat/minha-alteracao
```

Depois abra Pull Request para `main`.

> Evite trabalhar diretamente em `main`. Para infraestrutura, banco e mudanças maiores, branch + PR é a regra.

## Fonte de verdade

| Área | Onde |
|---|---|
| Página publicada | `index.html` |
| Frontend editável | `frontend/socialmei-dashboard.html` |
| Workflow oficial | `n8n-workflows/producao/01-caixa-unificada-api-postgresql.json` |
| Banco | `database/` |
| Containers | `compose.yaml` / `compose.override.yaml` |
| HTTPS | `Caddyfile` |
| API Python | `python-service/` |
| Procedimentos | `docs/` |

## n8n

```text
Personal/
└── SocialMEI.IA/
    ├── 01 · Produção/
    ├── 02 · Testes/
    └── 03 · Revisar/
```

Teste ideias fora de Produção sempre que possível.

## Banco

```text
socialmei
├── clientes
├── conversas
└── mensagens
```

O acesso humano é preferencialmente pelo pgAdmin. PostgreSQL não deve expor 5432 na internet.

## Quero instalar outro programa

Você não precisa ter acesso à VPS para preparar a mudança:

1. crie uma branch;
2. adicione o serviço ao Compose;
3. atualize `.env.example` se houver variáveis novas;
4. valide `docker compose config`;
5. abra PR;
6. o responsável pela infraestrutura aplica.

Veja [DOCKER.md](./DOCKER.md).

## Preciso de VPS, Docker ou AWS

Acesso é concedido sob demanda e com identidade individual.

Não compartilhe chave SSH privada, conta root, senha administrativa ou `.pem`.

Veja [ACESSOS.md](./ACESSOS.md).

## Nunca envie ao GitHub

- `.env`;
- arquivos `.pem`;
- chaves privadas SSH;
- senhas;
- tokens;
- chaves de API;
- credenciais do n8n;
- dumps/backups sensíveis.
