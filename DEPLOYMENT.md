# Publicação e operação

## Frontend: GitHub Pages

O repositório contém `index.html` na raiz e `.nojekyll`. A entrada encaminha para `frontend/socialmei-app.html`; a antiga URL `frontend/socialmei-dashboard.html` continua válida. Publique a raiz com a pasta `frontend/` completa e `tools/` se quiser disponibilizar o DevHub.

Confira o ramo/diretório em **Settings → Pages**. O endereço adotado é https://socialmei-ia.github.io/SocialMEI-IA/. Não há workflow `deploy-pages` no código. `repository-checks.yml` testa o checkout, não publica o frontend nem a VPS. Não foi verificado nesta revisão se Pages está habilitado ou qual modo está configurado.

Depois de publicar, confira as duas entradas, ausência de 404 para CSS/scripts/fonte, cadastro/onboarding, módulos e console. `localStorage` pertence à origem; mudar host/protocolo exige exportar/importar dados. Em deploy sob outra URL, ajuste canonical/JSON-LD/OG do HTML e os links da documentação.

## VPS: Docker Compose e Caddy

Os guias existentes registram uma VPS em `/home/ubuntu/socialmei` e hosts `*.54-94-213-7.sslip.io`. São referências históricas do ambiente, não evidência de disponibilidade. Não há pipeline AWS, Terraform ou deploy automático versionado.

### Ambiente novo de teste

Pré-requisitos: Docker/Compose, domínios com DNS correto, portas 80/443 disponíveis e responsável autorizado.

```bash
cp .env.example .env
# Configure localmente valores reais, domínios e URLs.
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Caddy precisa alcançar os domínios definidos e emitir certificados. O WAHA exige username, password e API key no `.env`; não use flags que desativam autenticação. PostgreSQL não publica 5432; WAHA tem bind em localhost. A API Python é publicada pelo Caddy, mas ainda não autentica requisições: não a use para dados sensíveis.

Todos os serviços estão em `compose.yaml`; o override versionado é vazio e existe por compatibilidade. Nenhum novo segredo é necessário para o fallback dos hosts antigos, mas ambientes próprios devem configurar `WAHA_HOST` e `PYTHON_API_HOST`. `WHATSAPP_HOOK_URL` mantém o destino histórico; revise payload e caminho do webhook antes de conectar uma sessão.

### Banco e workflows

1. Crie a role administrativa e defina senhas interativamente, fora do Git.
2. Aplique bootstrap, schema como proprietário `socialmei_admin` e permissões na ordem de [docs/BANCO-DE-DADOS.md](docs/BANCO-DE-DADOS.md).
3. Importe o export PostgreSQL inativo e selecione a credencial `socialmei_app` em ambos os nós SQL.
4. Teste POST/GET com dados fictícios em banco isolado, inclusive reenvio e UTF-8.
5. Só depois configure o endpoint público em `frontend/config.js` e ative o workflow de teste.

Antes de conectar canais reais, resolva autenticação do atendimento, origem CORS permitida, IDs estáveis e deduplicação de mensagens. A consulta legada retorna até 50 mensagens de entrada. Os scripts de bootstrap citam o banco `n8n`; nomes diferentes exigem revisão explícita dos grants. As migrations de gestão e o servidor da equipe têm procedimentos próprios; não há envio externo do composer.

### Atualizar um ambiente existente

Não rode `up` com um novo nome de projeto sem conferir os volumes: isso pode criar um banco vazio ao lado do banco atual. Preserve diretório, project name, `.env` e volumes; confirme o valor usado por `docker compose ls` e pelos labels dos containers. A revisão não renomeia volumes nem altera schemas.

```bash
git status --short
git fetch origin
git diff HEAD..origin/main -- compose.yaml compose.override.yaml Caddyfile python-service database
docker compose ps
```

Preserve qualquer trabalho local antes de atualizar. Faça backup pelo processo existente e confira restauração em ambiente isolado. Após revisão/merge:

```bash
git pull --ff-only origin main
docker compose config --quiet
# Aplique somente o serviço afetado; adicione --build para python-api.
docker compose up -d --no-deps NOME_DO_SERVICO
docker compose ps
docker compose logs --tail 100 NOME_DO_SERVICO
```

Não use `down -v` para aplicar manutenção. Se Caddyfile mudou, valide/recarregue pelo container. Se migração for necessária, siga um plano específico; os scripts de bootstrap não são rollback.

## Backup

`bash backup.sh` usa o diretório do próprio script; `SOCIALMEI_PROJECT_DIR`, `SOCIALMEI_BACKUP_DIR`, `SOCIALMEI_POSTGRES_CONTAINER` e `SOCIALMEI_N8N_CONTAINER` permitem alvos explícitos. Descobre o volume do n8n pela montagem `/home/node/.n8n`; falha antes da parada se não encontrar volume nomeado.

Gera dump PostgreSQL, arquivo privado de configuração (inclui `.env`, override, Python, SQL e workflows) e arquivo de dados n8n. O último interrompe temporariamente n8n; em falha há tentativa de reinício. Arquivos parciais são limpos e retenção de 14 dias só ocorre após sucesso. Um erro de restart retorna falha e exige intervenção.

O backup não inclui volumes WAHA, pgAdmin ou Caddy e não é um snapshot atômico entre banco e filesystem. Não execute cópias simultâneas. Não foi feito backup/restauração real nesta revisão. Planeje armazenamento fora da VPS e ensaio de restore antes de depender dessa rotina.

## Rollback

Frontend/código: reverta o commit pelo Git e publique a revisão anterior completa. Infraestrutura: mantenha o mesmo project name/volumes, restaure a configuração revisada e recrie apenas serviços afetados. Não troque a chave de criptografia n8n. Alterações de banco precisam de plano próprio e backup restaurável.

## Deploy pelo GitHub Actions

O repositório agora inclui `.github/workflows/manual-production-deploy.yml`.

Ele **não faz deploy automático após cada merge**. O objetivo inicial é substituir o processo de abrir SSH manualmente por um deploy controlado e auditável no GitHub.

Antes de usar:

1. proteja a branch `main`;
2. crie o environment `production`;
3. configure required reviewers;
4. cadastre os secrets descritos em [docs/GITHUB-SETUP.md](docs/GITHUB-SETUP.md);
5. crie uma chave SSH exclusiva do robô de deploy;
6. confirme que o checkout da VPS está limpo e aponta para o repositório correto.

Depois:

```text
Actions
→ Manual production deploy
→ Run workflow
→ main
→ confirmation: DEPLOY
```

O workflow bloqueia deploy quando existem alterações locais não commitadas na VPS e usa `git pull --ff-only`.

Nesta etapa ele ainda executa `docker compose up -d --build` sobre a pilha existente. O próximo estágio será publicar imagens versionadas e fazer a VPS consumir imagens específicas, reduzindo dependência de build no servidor.

## Staging

O ambiente de staging ainda não deve compartilhar volumes nem banco com produção.

Antes de automatizá-lo, a equipe deve decidir:

- host/subdomínios de staging;
- banco e volumes próprios;
- sessão WAHA separada ou WAHA desabilitado;
- secrets próprios;
- política de limpeza de dados fictícios.

Não use o banco de produção para testes de desenvolvimento ou homologação.

## Servidor compartilhado da equipe

A instalação opcional com site/API protegidos e banco separado está em
[docs/SERVIDOR-EQUIPE.md](docs/SERVIDOR-EQUIPE.md). Merge não publica essa pilha.
O workflow de deploy antigo não aplica o overlay da equipe.
