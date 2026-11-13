# Análise inicial de polling e consumo — 12/11/2026

**Escopo:** inspeção estática da candidata, sem SSH nesta etapa, sem coleta
nova do Prisma Console e sem leitura ou escrita no banco de produção.

## Achado importante: menu automático do Instagram

Em tools/instagram-auto-menu-worker.py, na condição **sem mensagem**, o loop
chama next_source e depois dorme **15 segundos**. O método next_source, em
python-service/instagram_auto_menu.py, abre conexão, define a transação somente
leitura e executa um SELECT com filtros de mensagens e subconsultas de limite.

Se **um worker estiver ativo 24 horas por dia**:

- 4 verificações de fila por minuto.
- 5.760 por dia.
- **172.800 verificações em 30 dias por worker.**
- **345.600 em 30 dias com dois workers ativos**, antes de contabilizar
  outros serviços e instruções de transação.

São cálculos de _iterações de polling_, não uma medição do ambiente nem
conversão comprovada para operações faturadas pelo Prisma. Em especial,
cada iteração executa ao menos um SELECT e o driver também gerencia a
transação. A documentação da otimização anterior reserva 20.000 operações
mensais para "outros consumidores, backups e testes": essa reserva **não
contempla sequer um único worker com polling a cada 15 segundos** caso
cada SELECT conte como uma operação. O orçamento deve ser revisto antes da
ativação desses workers.

**Não foi comprovado neste levantamento se um ou ambos os workers estão
ativos na produção, nem se o Prisma conta essas operações da forma
assumida no exemplo.** O diagnóstico não atribui a eles o limite já
esgotado.

## Segundo risco: recuperação por e-mail

python-service/recovery_worker.py usa o modo --watch com padrão de 15 s.
O override compose.team-recovery.yaml também seleciona --interval 15.
Quando habilitado, o worker verifica a fila com process_one mesmo vazia;
isoladamente isso poderia produzir outras 172.800 verificações em 30 dias.

No relatório de produção de 12/11, o modo de recuperação SMTP estava
**desabilitado**, portanto esse risco é **futuro/condicional**, e não causa
comprovada do gasto anterior.

## O que já foi otimizado

O documento docs/PRISMA-24H-RECOVERY.md registra:

- Healthcheck/reconhecimento de esquema com cache de 300 s, sonda curta
  e sem varredura completa a cada requisição normal.
- Caixa Unificada com leituras em lote, evitando uma consulta por
  conversa e por job sintético.
- Polling visível da Caixa em 30 s e capacidades em 60 s.
- Status WhatsApp em 60 s com recuo após erros.

**Não remover essas melhorias nem reativar verificações antigas.**
A configuração instalada pode divergir da documentação/branch; conferir
os overlays privados antes de publicar. A contagem anterior de 214
healthchecks por hora aponta amplificação histórica, mas não estabelece
a participação exata no faturamento.

## Plano de correção sem degradar a experiência do cliente

1. **Antes de ativar novos workers**, inspecionar em modo somente leitura
   quantas instâncias/contas estão efetivamente operando, timers, retries
   e intervalos atuais. Não ativar dois respondedores para a mesma conta.
2. Com PostgreSQL acessível, capturar linha de base em períodos ociosos
   e em testes controlados. A ferramenta
   tools/postgres-workload-baseline.py já está preparada para isso.
3. Para obter respostas rápidas **sem SELECT contínuo em fila vazia**,
   avaliar aviso ao worker após a persistência do webhook (sinal
   transacional, como LISTEN/NOTIFY, ou fila durável equivalente).
   Manter varredura periódica de reconciliação: a notificação isolada
   pode ser perdida em desconexões e não substitui a fila persistida.
4. Testar latência da primeira mensagem, mensagens simultâneas, queda
   de rede, replays, retomada, pausa humana e isolamento dos dois
   negócios antes de mudar o motor de atendimento.
5. Rever a periodicidade da fila de e-mails quando SMTP for habilitado.
   A entrega deve continuar resiliente, mas não precisa fazer polling
   a cada 15 s indefinidamente se não houver mensagens.
6. Acompanhar conexões, transações, leitura e escrita no PostgreSQL da
   AWS. Correções devem proteger CPU, RAM, I/O e latência, ainda que
   deixem de existir os limites de operações do Prisma.

## Bloqueios que permanecem

- A API de produção segue dependendo da origem Prisma com
  planLimitReached, até recuperação/exportação oficial.
- O PostgreSQL isolado na AWS contém backup histórico schema038;
  **não** deve substituir produção sem dump atual e validação do
  schema039.
- A instância atual t3.small tinha apenas cerca de 0,5 GiB de RAM
  disponível no ensaio. Não ativar todos os workers nessa máquina
  sem ensaio de capacidade e orçamento.
- Alterações do runtime, migrations, tokens e configurações de envio
  reais continuam fora do escopo desta análise.

**Resultado:** hipótese forte de custo estrutural em polling contínuo,
com componentes e intervalos concretos identificados; ainda faltam
medidas do Prisma Console, confirmação do runtime ativo e correlação
dos consumidores para concluir a causa do limite esgotado.

## Continuação verificada

A coleta posterior confirmou um workerInstagram nomeado ativo em polling,
SMTP desabilitado e nenhum worker de recuperação nomeado ativo. Cache de
readiness300s instalado foi confirmado; healthcheckDocker configurado15s,
sem equivalência automática entre chamadas HTTP e SQL. O consumo histórico
faturado continua sem atribuição comprovada.

A correção opt-in, testes transacionais reais e medições isoladas estão
registrados em [linha de base](POSTGRES-WORKLOAD-BASELINE-20261112.md).
Não foi ativada em produção; exige imagens novas e flaglisten coerente nos
produtores/consumidores, conexão PostgreSQL direta e capacidade para uma
conexão persistente por listener. Não usar LISTEN por pool transacional.
