# Publicação preparada do ambiente team

O publicador `tools/team-publish-prepared.py` atualiza somente API e gateway do checkout `/home/ubuntu/socialmei-team`. Não faz merge, não usa o workflow genérico de produção, não inicia workers e não comanda PostgreSQL, Caddy público, n8n ou WAHA.

## Gates e uso

Antes de cada atualização: aprovar o SHA exato e as migrations, conferir o CI desse SHA, construir as duas imagens, salvar o backup de rollback e preparar os overrides a partir dos arquivos Compose efetivamente usados por **cada** container. A preparação existente produz `source/`, `compose-commands.json`, `team-api.before.json`, `team-api.candidate.json`, equivalentes do gateway e os overrides. Nunca reutilizar manifestos de outra instalação ou editar os JSONs com segredos no chat.

A candidata V22 usa o SHA `47c3ba8fa65456ea16498a6e034798ba20bc7389`, cadeia 001–026. O script operacional pode estar em commit posterior, sem alterar o SHA das imagens publicadas. O publicador não verifica GitHub CI por conta própria: o operador deve confirmar o resultado no SHA das imagens antes de `--apply`.

```bash
cd /home/ubuntu/socialmei-team
python3 /caminho/privado/team-publish-prepared.py \
  --folder /home/ubuntu/socialmei-backups/prepare-VERSAO \
  --rollback-backup /home/ubuntu/socialmei-backups/pre-VERSAO \
  --sha SHA_COMPLETO
```

Sem flag é preflight: confere imagens/revisões, checksums do backup, containers, ambiente, redes, mounts, ausência de portas publicadas, Compose resolvido, fontes de migration e autenticação remota pública. Cria apenas log privado e um container efêmero sem rede para comparar o Caddy candidato com o instalado; não substitui serviços.

Adicionar `--apply` somente com autorização operacional. O comando executa backup novo e confere o recibo, aplica as migrations pelo runner transacional existente em um container efêmero usando a rede do banco e o ambiente privado atual, recria API e depois gateway com `--no-deps --no-build --pull never`, aguarda saúde e HTTP interno do gateway e confere HTTPS, limites anônimos e hashes dos arquivos publicados. Não troca o checkout antigo nem o `config.js` montado. Integrações reais/SMTP devem continuar desligados nesta rodada; caso estejam habilitados, a operação para para revisão.

Falha de migration interrompe antes de recriar serviços. Falha posterior tenta restaurar apenas os serviços cuja atualização foi tentada, usando as configurações e imagens anteriores. Se o rollback também falhar, interrompe e exige intervenção; não declara restauração concluída.

## Rollback manual

Repetir os mesmos argumentos com `--rollback`. O script verifica que configuração e imagem anteriores não foram alteradas antes de utilizá-las. As migrations aditivas permanecem; não executa down migrations, restore automático de dump ou remoção de volumes.

Não alterar/apagar a pasta preparada, arquivos Compose referenciados, imagens anteriores ou `.env.team` durante a janela de atualização e rollback. Estes arquivos têm dados privados. `publication-private.log`, `migration-private.env` temporário e backups nunca devem ser enviados ao GitHub/chat. O env-file temporário é removido ao concluir ou falhar a migration, mas após interrupção abrupta deve ser verificado pelo operador.

## Verificação humana

`installed.json` registra o SHA e deixa login visual como pendente. Depois da publicação: entrar em uma conta existente, conferir onboarding/edição, clientes/catálogo, Relatórios e as duas telas internas em desktop/mobile e claro/escuro. Não criar clientes fictícios em negócios reais. Recuperação de e-mail e canais não estão homologados por estes checks. Falha funcional crítica deve acionar rollback.

Para futuras versões, gerar nova pasta preparada e backups, manter o histórico anterior e reutilizar o mesmo publicador. A cadeia de migrations é intencionalmente limitada a 001–026: uma nova migration exige revisão/teste do publicador antes de liberar outra atualização.

## Retentativa após rollback

Na primeira tentativa V22, as migrations001–026 foram concluídas, mas o gateway foi validado antes de aceitar TCP/HTTP: a borda registrou conexão recusada,502, e o publicador restaurou as duas imagens anteriores. O operador confirmou raiz200, API401 e redes corretas após rollback. O publicador corrigido aguarda HTTP interno do gateway; na borda repete somente falhas transitórias de conexão e502/503/504, até12 tentativas com timeout5s e intervalo2s. Uma resposta final divergente, API desprotegida, erro de TLS ou hash errado continua interrompendo e acionando rollback.

O rollback recria containers: IDs novos são esperados. A flag explícita `--accept-recreated-baseline` permite revalidá-los somente com as mesmas imagens de rollback, ambiente, redes, mounts, portas e Compose já preparados; não autoriza drift de configuração. O recibo `revalidated-baseline.json` registra os IDs revalidados, sem sobrescrever o manifesto original. Sem a flag, a mudança de ID continua bloqueada.

A retentativa executa novo backup e o runner transacional lê o ledger: migrations já aplicadas são ignoradas, sem replay dos arquivos SQL001–026. Não apagar o ledger nem desfazer tabelas para repetir a publicação.
