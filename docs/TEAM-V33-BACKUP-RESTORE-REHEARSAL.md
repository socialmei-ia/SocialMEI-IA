# Ensaio privado de recuperação — SocialMEI.IA Team

O operador já confirmou que o backup de produção foi criado em
`/home/ubuntu/socialmei-backups/team-auto-20261028-234141-5dc482` e que
a release `c19d44b6ef6b8f125e6cafe60a7adfc0477cf454` foi preparada
em `team-v33-c19d44b6ef6b/source`, preservando o checkout modificado
do Caddy. Essas duas evidências **não** significam que o banco tenha sido
restaurado com sucesso.

## Ferramenta de recuperação (sem conexão ao banco real)

`tools/team-v33-restore-rehearsal.py` precisa ser executado no próprio
Ubuntu da AWS, com Docker local. Ele não exige senha de banco ou da API e
**não** lê o conteúdo do backup de configurações: apenas confere seus hashes.
O dump de produção permanece na máquina original.

Depois de verificar o arquivo na revisão aprovada do Git, execute:

```bash
python3 tools/team-v33-restore-rehearsal.py --target team \
  --backup team-auto-20261028-234141-5dc482 \
  --stage team-v33-c19d44b6ef6b --run
```

O comando faz, nesta ordem:

1. Valida pastas privadas, recibo, SHA-256 dos três arquivos do backup e
   os hashes das migrações 032/033 no Git worktree preparado.
2. Verifica se o backup está íntegro, se o stage não foi modificado e se
   há memória/disco suficiente. Requer pelo menos 4 GiB livres em disco,
   512 MiB disponíveis em memória e mais espaço conforme o tamanho do dump.
3. Cria **um volume e um container PostgreSQL 16 Alpine exclusivos**, com
   labels aleatórias, CPU/memória limitadas, rede Docker `none`, sem
   portas publicadas e sem privilégios extras.
4. Restaura o dump no PostgreSQL temporário com `pg_restore`, em transação.
   Confirma a existência das tabelas do CRM e a sequência exata das
   31 migrações anteriores.
5. Aplica as migrações 032/033 **somente nesse banco temporário** e compara
   as contagens de todas as tabelas anteriores. O ledger deve evoluir de
   31 para 33 e as novas tabelas devem existir.
6. Remove **somente** os recursos identificados pelos labels exclusivos
   do ensaio. Se a limpeza falhar, informa os dois nomes para intervenção
   controlada, sem executar `docker system prune` ou apagar volumes alheios.

Saída: somente relatório JSON sem senhas, mensagens, dumps ou dados pessoais.
`restore_verified=true`, `migration_032_033_rehearsed=true` e
`isolated_cleanup_verified=true` são os três critérios de sucesso.

## Atenções

- Uma restauração completa consome recursos temporários na VPS. A
  ferramenta recusa o ensaio se houver pouco disco/memória. Não executá-la
  durante pico de carga.
- Em caso de falha, **não** remover volumes por nome manualmente sem
  conferir labels e procedência.
- O ensaio de restore valida estrutura e preservação de contagens, mas
  **não valida as credenciais Meta/WAHA**, a publicação do frontend, a
  rede privada n8n, a recuperação das sessões pela aplicação, ou a
  atualização efetiva do servidor.
- Migrações de produção, ativação do bot, webhooks, respostas Direct e
  mudança do gateway **não acontecem** neste procedimento. Esses passos
  exigem um publicador Team 033 e validação do runtime instalado.
- O backup contém dados reais privados: nunca subir `equipe.dump`,
  `configuracao.tar.gz`, `concluido.json` ou `.env.team` ao GitHub
  nem enviá-los para a conversa.
