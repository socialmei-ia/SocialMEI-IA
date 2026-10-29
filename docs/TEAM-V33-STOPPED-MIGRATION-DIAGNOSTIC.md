# Diagnóstico após corte 032/033 interrompido

Se `team-v33-migrate-guarded.py --apply` retornar
`action: stopped`, **não repita --apply**: a resposta antiga sempre dizia
`production_may_have_changed: true` como aviso conservador, sem verificar
se a transação PostgreSQL chegou a ser executada.

O comando read-only `team-v33-diagnose-stopped.py` verifica:
- O recibo e os SHA-256 do backup privado de produção.
- A integridade do stage Git e os hashes das duas migrations.
- Ledger real (31 ou 33) e existência das quatro tabelas novas.
- Saúde Docker, rede privada da API/PostgreSQL, autenticação e flags
  de ingresso/envio desligadas.
- Espaço livre/memória para um eventual ensaio isolado.
- Quantidade de containers/volumes de ensaios anteriores com label
  `socialmei.team.backup_restore_trial`, sem apagá-los.

O diagnóstico não lê dados de clientes, não executa restauração,
não aplica migrations e não muda o Docker. Só produz nomes de fases
e códigos de erro sanitizados.

## Comando do Ubuntu

Baixe os três scripts **da mesma revisão aprovada** para uma pasta temporária:

```bash
d="$(mktemp -d /tmp/socialmei-v33-diagnose.XXXXXX)"
sha="SHA_REVISAO_APROVADA"
base="https://raw.githubusercontent.com/socialmei-ia/SocialMEI-IA/$sha/tools"
for f in team-v33-diagnose-stopped.py team-v33-migrate-guarded.py team-v33-restore-rehearsal.py; do
  curl -fLsS "$base/$f" -o "$d/$f" || exit 1
done
python3 "$d/team-v33-diagnose-stopped.py" --target team \
  --backup team-auto-20261028-234141-5dc482 \
  --stage team-v33-c19d44b6ef6b
```

**Se o banco ainda estiver em 031 e sem as novas tabelas**, o
diagnóstico não atribuirá falsamente uma migração bem-sucedida.
**Se estiver em 033 com quatro tabelas novas**, não reaplicar SQL.
Se o ledger e as tabelas não corresponderem, investigar manualmente,
sem modificar produção.

Caso todos os preflights read-only passem mas o banco ainda esteja em
031, a falha anterior poderá ter ocorrido durante o segundo ensaio de
restore ou no comando SQL. **Não existe informação suficiente para
identificar retroativamente qual foi o erro**: a ferramenta antiga
descartou as mensagens. A investigação deve continuar sem novo --apply
até identificar a etapa e proteger o backup.
