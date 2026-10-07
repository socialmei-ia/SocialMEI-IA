# Docker e infraestrutura — guia da equipe

Este guia explica como integrantes podem propor mudanças na infraestrutura sem depender de acesso administrativo direto à VPS.

## Regra principal

Qualquer integrante pode **preparar** uma mudança no Docker pelo GitHub. Somente responsáveis autorizados pela infraestrutura devem **aplicar** essa mudança na VPS.

```text
integrante → branch no GitHub → Pull Request / revisão
                                   ↓
                          responsável pela VPS
                                   ↓
                           valida e aplica
```

Ter acesso ao Docker equivale, na prática, a ter poder administrativo elevado sobre o servidor. Por isso, não é recomendado dar acesso Docker a toda a equipe.

## Arquivos principais

- `compose.yaml`: PostgreSQL, n8n, pgAdmin e Caddy.
- `compose.override.yaml`: serviço Python/FastAPI.
- `Caddyfile`: proxy HTTPS.
- `.env.example`: nomes das variáveis, sem valores secretos.

## Como adicionar um serviço

1. Crie uma branch.
2. Edite `compose.yaml` ou `compose.override.yaml`.
3. Não coloque senhas no arquivo.
4. Adicione novas variáveis somente como `${NOME_DA_VARIAVEL}`.
5. Atualize `.env.example` com placeholders.
6. Valide localmente ou na VPS antes de aplicar:

```bash
docker compose config >/dev/null && echo "COMPOSE OK" || echo "ERRO NO COMPOSE"
```

7. Abra um Pull Request.
8. Após revisão, o responsável pela VPS aplica a mudança.

## Aplicar apenas um serviço novo/alterado

Sempre que possível, evite reiniciar toda a stack:

```bash
docker compose up -d --no-deps NOME_DO_SERVICO
```

Se for necessário recriar apenas aquele serviço:

```bash
docker compose up -d --no-deps --force-recreate NOME_DO_SERVICO
```

Antes de executar, confira o impacto e registre o estado atual com:

```bash
docker compose ps
```

## Logs

```bash
docker logs --tail 100 NOME_DO_CONTAINER
```

Para acompanhar ao vivo:

```bash
docker logs -f NOME_DO_CONTAINER
```

## O que não fazer

- não editar `compose.yaml` somente na VPS e esquecer de versionar no GitHub;
- não publicar `.env`, senhas, tokens, arquivos `.pem` ou dumps;
- não expor a porta 5432 do PostgreSQL diretamente à internet;
- não usar `docker compose down -v` em produção sem entender que `-v` remove volumes;
- não apagar volumes, containers ou dados sem backup e autorização;
- não reiniciar todos os serviços quando basta recriar um único serviço.

## Fluxo recomendado para rollback

Se uma mudança nova causar problema:

1. pare de fazer novas alterações;
2. confirme qual commit/arquivo mudou;
3. restaure a configuração anterior pelo GitHub;
4. rode `docker compose config`;
5. recrie somente o serviço afetado;
6. confira `docker compose ps` e os logs.

Mudanças destrutivas em banco ou volumes exigem backup antes de qualquer execução.
