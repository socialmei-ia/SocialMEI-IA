# Etapa isolada de release 033 para AWS Team

Esta ferramenta prepara **somente uma cópia limpa do código** para o corte do
SocialMEI.IA, preservando totalmente o checkout atual da AWS. Foi criada porque
o diagnóstico de 29/10 mostrou checkout em SHA `6f4c8e1795cbb2e9074845edd9ac099a8ea3925b`,
com alterações locais, enquanto o candidato estava no commit
`179a0342547bc7b8ec31dbc9f17023f969b0ea8d`.

O runtime instalado mantém os serviços saudáveis, 31 migrações, WAHA WEBJS e
todos os ingressos/envios novos desativados. Ainda faltam as migrações
`032_whatsapp_bot_conversations.sql` e
`033_provider_sentiment_jobs.sql`.

## Preparação (não é publicação)

Depois que a PR de staging for aprovada e incorporada na branch de release,
use o SHA **final** dessa release:

```bash
curl -fLsS https://raw.githubusercontent.com/socialmei-ia/SocialMEI-IA/COMMIT_APROVADO/tools/team-v33-stage.py -o /tmp/socialmei-team-v33-stage.py
python3 /tmp/socialmei-team-v33-stage.py --target team --stage --candidate-sha COMMIT_APROVADO
```

O comando verifica o origin oficial, busca objetos Git do branch de release
sem checkout/reset no diretório atual, confirma a origem exata de 33 migrations
e que o banco tem uma sequência compatível de 31–33 versões. Em seguida,
cria o stage **novo** em
`/home/ubuntu/socialmei-backups/team-v33-<SHA inicial>/source` como worktree
Git destacada e bloqueada (lock). O recibo é salvo em pasta privada `0700`
com arquivo `0600`. Não são copiados `.env.team`, credenciais, banco de dados,
arquivos não versionados nem hotfixes locais. Se o diretório já existir, o
script falha de forma segura, sem sobrescrevê-lo.

O relatório mostra apenas a contagem de arquivos alterados/desconhecidos,
o indicador de que o único diff seria o Caddyfile revisável (quando aplicável),
os hashes das duas novas migrações, o plano 032/033 e a confirmação de que o
checkout original permaneceu idêntico. Não imprime caminhos particulares
alterados nem conteúdo de arquivos locais.

Modo somente leitura (sem fetch, worktree ou gravação):

```bash
python3 /tmp/socialmei-team-v33-stage.py --target team --inspect
```

## O que a etapa não faz

- Não faz backup do PostgreSQL, não restaura backup e não roda as migrações.
- Não altera Docker, volumes, Caddy, n8n, WAHA, Meta nem flags da API.
- Não substitui o release publisher anterior: este ainda suporta somente
  migrações até 031 e continua intencionalmente bloqueando 032/033.
- Não permite envios reais por Direct ou WhatsApp. Nenhum remetente é ligado.
- Não libera a publicação automaticamente. É necessário validar **backup e
  restauração**, diff efetivo do compose e dos mounts, rede privada da API,
  aplicação de migration 032/033 em banco descartável e smoke tests.

## Próximo passo após o stage

Construir e revisar um **publicador Team v33** com baseline das imagens
instaladas, compose resolvido por serviço, contas/segredos privados, rollback
sem apagar migrações e validação de saúde. Não reutilizar `up --build`
genérico, `docker compose down`, `prune`, `git clean`, `reset --hard`
nem o workflow manual de produção legado.

A aprovação do usuário cobre a preparação, mas não substitui provas de que o
envio real usará uma conta de teste autorizada e um único remetente por canal.
