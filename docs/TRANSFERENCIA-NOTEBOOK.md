# Transferência inicial do notebook para a equipe

A proteção por senha permanece ativa. A decisão sobre demonstração pública fica
pendente; este fluxo não modifica Caddy, credenciais ou configuração de acesso.

A transferência copia Clientes, Catálogo, Vendas e Financeiro do PostgreSQL do
workspace `development` para `team`. Não copia preferências, contas, conversas,
workflows n8n, registros apenas no navegador, arquivos de imagem externos nem
histórico de operações pendentes. Não restaure o dump do n8n no banco da equipe.

## Garantias e limites

- O exportador lê os quatro módulos numa transação PostgreSQL somente de leitura,
  com isolamento repeatable read. Não exporta páginas ou snapshots desatualizados
  do navegador. Encerre edições no notebook antes de exportar e durante a mudança.
- Novos IDs são criados e vínculos são remapeados pelos IDs originais, sem procurar
  por nomes. Registros atuais do destino são preservados; nomes iguais não são
  mesclados. O cliente de teste do servidor continuará existindo.
- Estoque atual é copiado, sem nova baixa. Vendas operacionais mantêm
  `estoque_aplicado`: cancelar depois estorna uma única vez, conforme a API normal.
  Vendas importadas continuam importadas; cancelamento delas não estorna estoque.
- Snapshots de nomes, valores, datas, versões e exclusões lógicas são preservados.
  `legacy_local_id` de clientes fica no snapshot de auditoria, sem reutilizar a
  identidade antiga no destino. Datas de pagamento ausentes continuam ausentes.
- Clientes, itens, vendas, financeiro e comprovante são gravados na mesma transação.
  Falha em qualquer módulo desfaz todos. A prévia é somente de leitura e inclui
  um token do estado do destino; alteração concorrente exige uma nova prévia.
- Um workspace recebe uma única transferência inicial. Mesmo arquivo/origem
  recupera o comprovante; arquivo alterado ou outra origem gera 409. Isso evita
  duplicar o banco se o exportador for executado novamente com outra identidade.
  Não é sincronização contínua, atualização incremental ou mesclagem de empresas.
- Limites: 500 registros por área e pacote até 2 MB. Arquivos maiores ou dados fora
  do contrato são recusados, sem truncar. Valores são preservados com Decimal;
  catálogo e totais legados têm limite de 50 dígitos/20 casas neste pacote.
- A confirmação aceita somente o workspace `team`, com o controle de acesso do
  gateway. O app de transferência exige os quatro módulos na mesma API/origem.

## Atualização no servidor instalado em worktree

Após aprovação e merge, o administrador faz um novo backup privado do banco da
equipe e guarda `.env.team` e `deploy/team/private/`, incluindo os arquivos de proxy
específicos da instalação. Confirme exit status e índice do dump; copie backups
para armazenamento privado fora da instância. Não envie os arquivos pelo chat.

No ambiente confirmado `/home/ubuntu/socialmei-team`, preserve arquivos privados e
confira alterações rastreadas antes de trocar o código:

```bash
cd /home/ubuntu/socialmei-team
git status --short
git fetch origin main
git checkout --detach origin/main
```

Migrations antes da API nova, usando somente o projeto da equipe:

```bash
docker compose --env-file .env.team -f compose.team.yaml run --rm --build team-migrate
COMPOSE_PARALLEL_LIMIT=1 docker compose --env-file .env.team -f compose.team.yaml up -d --build --wait --wait-timeout 180
docker compose --env-file .env.team -f compose.team.yaml ps --all
```

A migration `008_workspace_transfer.sql` cria o registro de transferência. Este
update recria API/gateway da equipe e pode interromper brevemente o site da equipe;
não recria o Caddy público nem os containers antigos do n8n. O gateway novo continua
montando os arquivos privados já criados. Não faça `git pull` no checkout antigo
modificado, não apague volumes e não use o workflow de produção antigo.

## Exportar no notebook Windows

No PowerShell, dentro de `C:\Users\richa\SocialMEI-IA`, após encerrar edições:

```powershell
git pull --ff-only origin main
npm.cmd run dev
npm.cmd run db:migrate
npm.cmd run data:export
```

O arquivo é criado em:

```text
C:\Users\richa\SocialMEI-Transferencia\socialmei-transferencia-notebook.json
```

A pasta fica fora da raiz publicada pelo servidor local. Também contém
`origem.json`, identidade estável do notebook. Preserve os dois arquivos. O comando
não sobrescreve um snapshot existente. `SOCIALMEI_TRANSFER_DIR` permite uma pasta
privada própria; escolha uma pasta fora da raiz servida pelo frontend.

O exportador usa Node/Docker já instalados; Python executa dentro da API local.
Ele não solicita a senha online, não envia dados pela internet e não lê `.env` do
servidor. Se falhar, confira API/migrations e repita mantendo a identidade. Não
apague a identidade para contornar conflitos. Se a fonte mudou depois do export,
pare e revise a passagem para o servidor; não confirme um snapshot antigo por hábito.

## Prévia e confirmação protegidas

Abra a página de transferência no endereço do site da equipe:

```text
https://app.54-94-213-7.sslip.io/frontend/transferencia.html
```

1. Entre com a credencial do navegador já configurada.
2. Selecione o JSON exportado no notebook; não selecione backup do navegador.
3. Clique **Conferir prévia** e confira fonte, destino, contagens e estoque.
4. Confirme que guardou os backups e encerrou as edições no notebook.
5. Clique **Confirmar transferência**. As quatro áreas são gravadas juntas.
6. Baixe o comprovante com os mapas de IDs e recarregue o SocialMEI.

Se a resposta se perder, use o mesmo arquivo e confira outra prévia. A página
recupera o comprovante sem reaplicar o estoque nem recriar registros. Se o destino
mudar depois da prévia, ela será recusada até uma nova revisão. Não edite o JSON ou
use outra origem para forçar a transferência.

Ao concluir, use a URL online como fonte principal. O banco local continua
preservado como referência/backup, mas alterações nele não serão sincronizadas.
Confira contagens e um vínculo cliente/venda/item; não registre uma nova venda
para testar saldo durante a conferência da migração.

## API

`POST /api/v1/transferencias/preview` recebe `TransferPacket`: formato
`socialmei-workspace-transfer`, versão 1, origem UUID, workspace de origem
`development`, timestamp de exportação e arrays `clientes`, `produtos`, `vendas`,
`financeiro`. Cada linha traz ID original, versão e timestamps, além do contrato
completo da área. Vínculos faltantes, IDs repetidos, estado de estoque inconsistente,
valores inválidos e excesso de tamanho são recusados antes de gravar.

`POST /api/v1/transferencias/confirmar` recebe `{ pacote, preview_token }`. Retorna
origem, workspace de destino, contagens, mapa de IDs e `ja_transferido`. A identidade
é registrada em `socialmei.crm_transferencias`, junto do snapshot e resposta, sob
lock do workspace. Timestamp de exportação e ordem das linhas não fazem um snapshot
novo; mudanças nos dados fazem. A resposta perdida é recuperável mesmo após outros
usuários editarem ou excluírem dados no destino, sem desfazer essas alterações.

Rollback exige revisão do administrador: restaure o backup da equipe em ambiente
isolado e confira o alvo antes de substituir qualquer banco. Não exclua somente o
comprovante para reaplicar a origem; isso pode duplicar registros. Não há exclusão
automática dos dados originais do notebook.
