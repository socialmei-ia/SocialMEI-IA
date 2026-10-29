# Corte aditivo v33 na VPS com RAM limitada

## Por que existe este caminho

O backup privado `team-auto-20261028-234141-5dc482` foi restaurado com
sucesso pelo operador em PostgreSQL 16 temporário, com as migrações 032/033
ensaiadas e preservação de contagens das 65 tabelas anteriores. O ensaio
retornou o fingerprint
`c0ace386cc88f2ea96ad1180e21a59b536e32026a40740d2f8bca81908490e15`,
limpeza completa e nenhuma modificação na produção.

Uma execução subsequente do migrador falhou na **verificação de capacidade**,
antes da gravação: `MemAvailable` ficou abaixo de 512 MiB. A inspeção
read-only confirmou **31 migrações na produção e zero tabelas novas**.
A VPS tem apenas 1,9 GiB RAM, 1 GiB de swap utilizada, com n8n e
WAHA/WebJS consumindo aproximadamente 400 MiB cada.

Não é recomendável derrubar n8n ou WAHA apenas para liberar memória.

## Execução excepcional e delimitada

`tools/team-v33-lowmem-cutover.py` reutiliza os scripts já revisados
`team-v33-migrate-guarded.py` e `team-v33-restore-rehearsal.py`,
baixados **da mesma revisão**. O novo fluxo **não repete o ensaio de restore**
que já foi comprovado pelo operador. A prova anterior é uma **atestação
operacional**, não uma evidência criptográfica automaticamente vinculada
ao dump; esse é o tradeoff excepcional, explícito, para esta VPS.

Por isso o script é **one-off**: só aceita o backup, stage, SHA da fonte,
checkout de produção e fingerprint de ensaio conhecidos. Ele não é um
publicador de propósito geral e deve falhar se qualquer um mudar.

O modo `--inspect` é somente leitura e não cria novos backups:

```bash
python3 tools/team-v33-lowmem-cutover.py --target team \
  --prior-restore-fingerprint c0ace386cc88f2ea96ad1180e21a59b536e32026a40740d2f8bca81908490e15 \
  --inspect
```

O modo `--apply` **modifica o esquema de produção** somente depois de
todos os gates, inclusive um **novo pg_dump+hash** para registrar o
estado imediatamente anterior à transação:

```bash
python3 tools/team-v33-lowmem-cutover.py --target team \
  --prior-restore-fingerprint c0ace386cc88f2ea96ad1180e21a59b536e32026a40740d2f8bca81908490e15 \
  --apply
```

### Proteções

- Checkout instalado continua em `6f4c8e1795cbb2e9074845edd9ac099a8ea3925b`,
  com **apenas** o hotfix local `deploy/team/Caddyfile` pendente.
- Backup original e stage `team-v33-c19d44b6ef6b` verificados por
  SHA-256, recibos privados e Git limpo.
- Banco e API existentes saudáveis, autenticação ativa, redes sem
  exposição do PostgreSQL e todos os canais Meta/WAHA/sentimento desligados.
- Histórico do banco igual às 31 versões esperadas e ausência das quatro
  tabelas novas; qualquer migração parcial impede a transação.
- Pelo menos 128 MiB disponíveis para a DDL leve e 2 GiB livres em disco.
  Não cria um segundo PostgreSQL.
- **Novo backup privado verificado**, feito pela rotina existente antes
  da primeira instrução SQL. Em caso de falha nesse backup, não escreve.
- Revalidação dos gates e aplicação de 032/033 em **uma transação
  PostgreSQL**, com advisory lock e limite de tempo. Ledger 33 e quatro
  tabelas novas confirmados após commit.
- Nenhum restart, troca de imagem, deploy, ativação de webhook, alteração
  do n8n, WAHA ou envio real.

Em caso de erro, o relatório indica a **fase**. Se a fase for
`transaction` ou `post_commit`, **não repetir --apply**: primeiro
conferir novamente o ledger e as tabelas com o diagnóstico read-only.

### Depois

Ainda falta publicar API/gateway de forma segura e homologar os provedores.
A migração da estrutura não atualiza o site. A VPS de 2 GiB deve ser
planejada para upgrade de memória antes de abrir o sistema a mais usuários.
