# Atualização transacional do banco Team: 032/033

**Estado inicial confirmado pelo operador (28/10/2026):** backup
`team-auto-20261028-234141-5dc482` criado com dump, índice e hashes;
stage privado `team-v33-c19d44b6ef6b` preparado no SHA
`c19d44b6ef6b8f125e6cafe60a7adfc0477cf454`; restauração real em
PostgreSQL 16 temporário aprovada, 65 tabelas originais preservadas,
migrações 032/033 testadas e recursos de ensaio removidos.

**O banco de produção ainda está no ledger 001–031**, salvo atualização
posterior não informada. Esta entrega permite avançar **somente a estrutura
do banco**, não a API, o frontend, o gateway ou os envios de provedores.

## Ferramenta

`tools/team-v33-migrate-guarded.py` usa o módulo
`tools/team-v33-restore-rehearsal.py` da **mesma revisão** do Git;
os dois arquivos devem estar lado a lado no Ubuntu.

Primeiro, modo leitura e verificação, **sem escrever no banco**:

```bash
python3 tools/team-v33-migrate-guarded.py --target team \
  --backup team-auto-20261028-234141-5dc482 \
  --stage team-v33-c19d44b6ef6b --inspect
```

Depois de conferir o relatório, o modo `--apply` executa o corte aditivo
da estrutura do PostgreSQL **em produção**. O operador tem autorização
para essas mudanças, mas deve compreender que essa etapa é efetiva:

```bash
python3 tools/team-v33-migrate-guarded.py --target team \
  --backup team-auto-20261028-234141-5dc482 \
  --stage team-v33-c19d44b6ef6b --apply
```

### Gate automático do modo --apply

1. Confere recibo privado e hashes de backup, stage limpo e SHA esperado,
   33 migrações da fonte e ledger de produção estritamente igual ao prefixo
   conhecido 001–031 (ou 001–033 já instalado).
2. Inspeciona container da API e PostgreSQL existentes, saúde Docker,
   autenticação, redes/portas e **nega** aplicação quando ingresso/envio
   Instagram, publicação, bot WhatsApp ou sentimento estiverem ativos.
3. Executa novamente **o ensaio real de recuperação no banco temporário
   e offline**, com limites de memória e CPU. Só avança após verificar
   restauração, migrações e limpeza dos recursos pertencentes ao ensaio.
4. Reconfere containers e ledger para detectar alterações concorrentes.
5. Aplica exclusivamente o SQL revisado de 032 e 033 em **uma transação
   PostgreSQL**, com bloqueio advisory usado pelo migrador original,
   `lock_timeout`, `statement_timeout`, interrupção em erro e
   conferência final de ledger 001–033.
6. Não reinicia container, não troca imagem, não altera Caddy, não ativará
   ingressos/envios de Instagram ou WhatsApp e não copia segredos para o
   frontend. Informa somente resumo JSON de sucesso/falha.

O script é idempotente se a produção já tiver 33 migrações. O ledger exige
versões exatas: ele não aceita 032 desconhecida, buracos, outra base ou
migração aplicada parcialmente.

### Rollback e próximas etapas

As migrações são **aditivas**. Não existe downgrade automático: após a
aplicação, o banco passa a conter as novas tabelas, que são compatíveis
com a API anterior, mas ela não usa as funções novas. **Não apagar ou
reverter tabelas** para voltar à imagem anterior.

Se uma verificação após a transação falhar, o programa reporta
`production_may_have_changed`; o operador deve inspecionar o ledger
antes de repetir qualquer ação. O programa não promete uma restauração
automática do banco em produção.

Depois do banco, falta um corte separado do backend/gateway com rollback
das imagens atuais, configuração privada preservada, rotas e HTTPS.
A API anterior continuará rodando até esse corte. A ativação real dos
canais ainda exige conta/número de teste e um remetente único por canal.

Não executar `docker compose down`, `reset --hard`,
`git clean` nem usar o antigo publicador V25 limitado à migration 031.
