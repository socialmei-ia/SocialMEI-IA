# Linha de base de consumo do PostgreSQL (sem Prisma)

## Por que isso existe

O erro do provedor Prisma Postgres foi planLimitReached, mas a contagem
exata por consumidor **não foi demonstrada**. Uma coleta anterior encontrou
214 healthchecks em aproximadamente uma hora; isso mostrou amplificação de
monitoramento, **não** que os healthchecks tenham causado toda a cota.
A branch candidata já reduz frequência do healthcheck e consultas da Caixa;
não reaplicar alterações antigas sem medir.

Na AWS, consultas não são limitadas pela mesma franquia do Prisma, porém podem
sobrecarregar CPU, memória, disco e conexões, especialmente na EC2 t3.small
que tinha aproximadamente 0,5 GiB de RAM disponível durante a preparação.

## Ferramenta adicionada

tools/postgres-workload-baseline.py faz **uma leitura de
pg_catalog.pg_stat_database por amostra**, apenas no banco efetivo da conexão
explicitamente informada. Não acessa dados de clientes, tabelas do SocialMEI,
texto de consultas, conteúdo de mensagens, parâmetros ou senhas. Não cria
tabelas, índices, extensões nem migrations; não envia mensagens.

- Conexão com transações somente leitura e timeout SQL de 3 s.
- Timeout de conexão de 5 s; duração limitada a 2–12 amostras,
  espaçadas por 10–300 segundos, padrão duas amostras com 60 segundos.
- A variável obrigatória é SOCIALMEI_PG_METRICS_DSN: não há fallback
  automático para DATABASE_URL ou para outra base local.
- Falhas são sanitizadas; não imprimimos DSN nem mensagens brutas do driver.
- Contadores reiniciados ou reduzidos invalidam a comparação.
- Saída JSON agregada em stdout; nenhum dado é enviado para serviço externo.
- Mesmo uma consulta de monitoramento conta como atividade no banco.

Executar **somente** quando o responsável tiver autorizado uma conexão privada
de leitura para a base que deseja observar. O PostgreSQL 17 precisa ter psycopg
3 instalado no ambiente de execução. Preparar a variável no arquivo de
ambiente privado, sem colocá-la no shell history, logs, GitHub ou chat:

```bash
python tools/postgres-workload-baseline.py --interval 60 --samples 2
```

Para executar os testes offline, que **não** conectam a banco:

```bash
python -m unittest discover -s tests -p 'test_postgres_workload_baseline.py'
```

## Como interpretar com segurança

- xact_commit / xact_rollback: transações, **não** número de instruções SQL
  e **não** unidades de cobrança do Prisma.
- tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted:
  atividade geral de leitura e escrita. Contadores de linhas não equivalem a
  registros únicos ou chamadas da API.
- blks_read / blks_hit: leituras de disco versus acertos de cache.
- temp_bytes, deadlocks: sinais de pressão que merecem investigação.
- connections_first e connections_last: número pontual de conexões.
- per_minute: taxa **apenas na janela observada**, nunca previsão de um mês.

Coletar em três contextos autorizados, comparando janelas equivalentes:
**ocioso**, **Caixa aberta**, **conversa WhatsApp/Instagram e agendamento de
teste**. Identificar e registrar separadamente quantidade de workers/processos,
intervalos configurados e reinícios. Comparar a evolução de carga em vez de
concluir a causa pela presença de uma consulta isolada.

O acumulado pg_stat_database não atribui operações a endpoints, bots ou
consultas individuais. Para investigar a origem detalhada, correlacionar
métricas do Prisma Console (quando acessível) e métricas de aplicação; antes
de habilitar extensões como pg_stat_statements, solicitar revisão de
capacidade, privacidade e permissões. Nunca coletar SQL contendo tokens ou
dados pessoais como evidência pública.

## Limites e segurança do projeto

Esta ferramenta **não resolve** o bloqueio da origem atual no Prisma, não
exporta o banco, não autoriza deploy e não diagnostica consumo real sem amostras.
O destino da AWS contém somente o snapshot histórico schema038; a migração
definitiva exige obter o dump atual, validar schema039, backups externos
independentes e a capacidade do servidor. O monitor deve ser executado de
forma pontual, não como polling em segundo plano.

Branch preparada separadamente da produção para evitar workflows de PR que
executam migrations em fixtures. Nenhuma alteração do Prisma ou do runtime foi
necessária para este diagnóstico.

## Continuação implementada — 12/11, coleta UTC em 13/11

- Candidata única `release/functional-completion-20261112`, descendente de
  `ea413f6`, preservando preparação AWS e correções anteriores.
- Commit `683b61c`: `SOCIALMEI_QUEUE_WAKEUP_MODE=listen` opt-in; produtores API
  e consumidores precisam da mesma flag. LISTEN antes da leitura, sinal vazio
  transacional, fila persistida autoritativa e reconciliação: Instagram60s,
  recuperação300s. Falhas de listener mantêm polling de segurança e backoff.
  O padrão continua `poll`; nenhuma redução foi ativada em produção.
- Heartbeat Instagram em arquivo separado, sem SQL, valida prontidão de leitura,
  container e validade temporal. Não limpa o latch de envio incerto/em andamento.
- 11 testes focados de fila/saúde aprovados, incluindo commit/rollback e
  desconexão/reconexão em PostgreSQL descartável real. Sete testes existentes
  do worker de recuperação e dois contratos JS também aprovados.
- Em janela virtual900s, scans de fila vazia: Instagram60→15 (−75%);
  recuperação60→3 (−95%), mais um LISTEN inicial. Não é cobrança do Prisma.
- Ensaio real curto na AWS isolada, com janela escalada de seis segundos,
  comparou seis consultas vazias/conexões com uma consulta e espera LISTEN.
  O monitor existente observou xact_commit14→6, incluindo overhead dos
  observadores e setup do listener. Sem registros escritos, deadlocks ou
  arquivos temporários. Não equivale a fluxo completo de atendimento ou carga
  de produção. Sinal transacional acordou o consumidor: espera total0,221s com
  disparo programado após0,200s; inclui conexão e commit do produtor.
- Amostra ociosa separada: duas consultas de monitoramento em11,301s,
  duas transações observadas, zero escritas de registros e zero deadlocks.
- Runtime lido sem alterações: um worker Instagram nomeado ativo em `poll`,
  nenhum worker de recuperação nomeado ativo e SMTP desabilitado. Sender
  WhatsApp nomeado usa GOWS. Healthcheck da API configurado em15s; presença
  do cache de readiness e TTL300s confirmados no código/ambiente instalados.
  Isso não atribui historicamente a cota a um consumidor específico.
- Origem novamente recusou pg_dump com `planLimitReached`. Não foi ativada a
  janela24h, nem alterada conexão, plano, dados ou configuração de produção.
