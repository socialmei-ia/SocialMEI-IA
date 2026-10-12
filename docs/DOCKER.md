# Docker

## Desenvolvimento local da equipe

Use `compose.dev.yaml` para desenvolvimento. Ele é separado do Compose de produção e cria volumes locais próprios.

```bash
npm ci
npm run setup
npm run dev
```

Serviços padrão:

- frontend em http://localhost:5500;
- PostgreSQL local na porta 5433;
- n8n em http://localhost:5678;
- FastAPI em http://localhost:8000.

Ferramentas opcionais:

```bash
npm run dev:tools   # inclui pgAdmin em http://localhost:5050
npm run dev:waha    # inclui WAHA em http://localhost:3000
```

Execute esses comandos dentro do repositório. O WAHA é uma imagem Docker definida no Compose; não precisa de uma pasta própria de código. Seus volumes ficam fora do repositório por decisão do Docker. Para atualizar uma instalação existente no Windows e conferir um WAHA instalado separadamente, siga [WAHA junto do projeto](ONBOARDING.md#waha-junto-do-projeto).

Diagnóstico:

```bash
npm run status
npm run logs
npm run dev:config
npm run stop
```

Não use as credenciais de desenvolvimento em staging ou produção. Cada integrante deve manter seus próprios volumes locais.

## Produção

O procedimento de preparação, publicação, atualização e rollback está em [DEPLOYMENT.md](../DEPLOYMENT.md).

`compose.yaml` define PostgreSQL, n8n, pgAdmin, Caddy, Python e WAHA. `compose.override.yaml` é uma entrada vazia de compatibilidade; não existe mais uma segunda definição WAHA.

## Diagnóstico

```bash
docker compose config --quiet
docker compose ps
docker compose logs --tail 100 NOME_DO_SERVICO
```

Para validar somente a estrutura com placeholders:

```bash
docker compose --env-file .env.example config --quiet
```

Evite publicar o resultado completo de `docker compose config`: ele pode conter valores do `.env`. A validação não verifica disponibilidade de imagens, credenciais, certificado ou saúde da VPS.

Caddy usa 80/443; PostgreSQL não publica 5432; o bind WAHA é `127.0.0.1:3000`. Username, password e API key WAHA são obrigatórios na configuração. A comunicação n8n → WAHA usa `http://waha:3000` e exige credencial conforme a versão instalada.

Não mude o project name nem apague volumes para aplicar uma revisão. `latest` ainda é dívida técnica; fixe versões depois de validá-las em teste. SQL/workflows não são inicializados automaticamente pelo Compose.

Mudanças seguem branch → PR → revisão → aplicação por responsável pela infraestrutura. Veja [ACESSOS.md](ACESSOS.md).
