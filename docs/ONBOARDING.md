# Onboarding da equipe — SocialMEI.IA

Este documento existe para que um integrante consiga começar a trabalhar sem depender de outro membro para explicar a estrutura do projeto.

## 1. Links principais

- GitHub: https://github.com/socialmei-ia/socialmei
- Dashboard público: https://socialmei-ia.github.io/socialmei/
- n8n: https://socialmei.54-94-213-7.sslip.io/home/workflows
- Banco / pgAdmin: https://db.54-94-213-7.sslip.io (login necessário)

## 2. Onde modificar cada coisa

| Quero alterar | Onde |
|---|---|
| Dashboard | `frontend/socialmei-dashboard.html` |
| Página publicada | `index.html` |
| Workflows | n8n + export em `n8n-workflows/` |
| Estrutura do banco | `database/` |
| API Python | `python-service/` |
| Containers | `compose.yaml` / `compose.override.yaml` |
| HTTPS / proxy | `Caddyfile` |
| Instruções | `docs/` e `README.md` |

## 3. Fluxo de colaboração

```bash
git pull origin main
git checkout -b feat/minha-alteracao
# altere e teste
git status
git add .
git commit -m "feat: descreva a mudança"
git push origin feat/minha-alteracao
```

Depois, abra um Pull Request para `main`.

## 4. Regra importante

Nunca envie para o GitHub:

- `.env`
- arquivos `.pem`
- senhas
- tokens
- API keys
- credenciais do n8n
- dumps/backups do banco

## 5. Antes de modificar produção

1. Entenda qual serviço será afetado.
2. Faça a alteração em branch.
3. Teste.
4. Peça revisão quando possível.
5. Faça backup antes de mudanças destrutivas de banco/infraestrutura.
6. Só então aplique no servidor.

## 6. n8n

Estrutura atual:

```text
Personal/
└── SocialMEI.IA/
    ├── 01 · Produção/
    ├── 02 · Testes/
    └── 03 · Revisar/
```

Novos workflows devem entrar na pasta correspondente e ter nomes claros.

## 7. Banco

A estrutura do banco deve ser reproduzível a partir dos arquivos em `database/`.

O painel web do banco será o pgAdmin; o PostgreSQL não deve ser aberto diretamente à internet.
