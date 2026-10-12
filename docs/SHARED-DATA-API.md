# API de dados compartilhados

Esta fase cria a primeira base real para o SocialMEI deixar de depender de `localStorage`.

## Estado

O frontend **ainda não usa esta API**. A integração começa por backend/local/staging para não arriscar os módulos atuais.

A API compartilhada fica desativada por padrão e só funciona quando:

```text
SOCIALMEI_SHARED_DATA_ENABLED=true
```

No `compose.dev.yaml`, ela é ativada apenas para desenvolvimento local.

## Endpoints iniciais

```text
GET    /health/db
GET    /api/v1/clientes
POST   /api/v1/clientes
GET    /api/v1/clientes/{id}
PATCH  /api/v1/clientes/{id}
DELETE /api/v1/clientes/{id}
```

## Workspace temporário

Enquanto autenticação real não existe, cada ambiente usa um workspace fixo por configuração:

```text
SOCIALMEI_WORKSPACE_SLUG
SOCIALMEI_WORKSPACE_NAME
```

O frontend não escolhe `workspace_id`.

Isso é suficiente para provar compartilhamento entre computadores em staging, mas **não é autenticação de produção**.

## Tabelas

A migration `002_shared_crm_foundation.sql` cria:

```text
workspaces
users
workspace_members
crm_clientes
```

`crm_clientes` é temporariamente separado da tabela `clientes` já usada pelo histórico da Caixa Unificada. Isso evita que um CRUD novo apague conversas antigas por causa das relações atuais do atendimento.

A unificação deve acontecer depois de definirmos identidade, autorização e migração do histórico.

## Desenvolvimento local

```bash
npm run dev
npm run db:migrate
```

Depois:

```text
http://localhost:8000/health/db
http://localhost:8000/docs
```

Exemplo de criação:

```json
{
  "nome": "Maria Silva",
  "telefone": "(81) 99999-0000",
  "instagram": "@maria",
  "status": "Ativo",
  "observacao": "Cliente de teste",
  "tags": ["Recorrente"],
  "legacy_local_id": 1
}
```

## Segurança

Esta API ainda não deve ser exposta como CRM de produção.

Antes disso faltam:

- autenticação real;
- autorização por usuário/workspace;
- CORS restrito;
- rate limiting;
- trilha de auditoria;
- política de exclusão/retensão;
- migração controlada dos dados locais.

## Contrato de Clientes e migration 003

`003_client_contract.sql` amplia `crm_clientes` sem alterar as migrations
anteriores nem as tabelas de atendimento. Registros existentes recebem
`versao: 1`; os novos campos são opcionais.

Além dos campos originais, o CRUD aceita e retorna:

| Campo público                  | Persistência / significado                                                                   |
| ------------------------------ | -------------------------------------------------------------------------------------------- |
| `cidade`, `desde`, `categoria` | Texto do perfil da Caixa; `desde` preserva o texto, sem assumir uma data                     |
| `criadoEm`                     | `cadastro_original_em`: timestamp original do navegador, separado de `criado_em` do servidor |
| `observacaoAtualizada`         | `observacao_atualizada_em`: timestamp da observação                                          |
| `avatarUrl`, `foto`            | Referências de imagem; não armazena o arquivo                                                |
| `ultima`, `total`, `pendente`  | Snapshots legados, não métricas calculadas pelo backend                                      |
| `versao`                       | Contador retornado pelo servidor para detectar edições concorrentes                          |

Datas com horário devem incluir fuso, por exemplo `2026-10-11T15:00:00Z`.
Tags têm até 50 itens, cada um com 1–80 caracteres após trim. Nome e status
não podem estar vazios ou nulos. Contatos e campos opcionais podem ser
limpos com `null` no PATCH. Campos desconhecidos retornam **422**, em vez de
serem descartados silenciosamente. A futura importação deverá mapear campos
legados e preservar extensões não reconhecidas no snapshot de origem;
não envie o objeto inteiro de `localStorage` diretamente ao POST.

GET da coleção continua retornando uma lista e as rotas antigas permanecem.
POST e PATCH existentes, com os campos válidos originais, continuam funcionando.

### Edições concorrentes

Leia `versao` no GET/POST e envie `expected_version` no PATCH:

```json
{
  "nome": "Maria Silva Atualizada",
  "expected_version": 1
}
```

Uma atualização aceita incrementa `versao`. Se outra sessão já alterou o
registro, a API retorna **409** e preserva o dado atual. Um PATCH sem campos
alterados não incrementa a versão, mas verifica a precondição quando enviada.
DELETE aceita `?expected_version=2` e aplica a mesma proteção.

A precondição é opcional para compatibilidade com os consumidores antigos.
O futuro adapter remoto deve sempre enviá-la em alterações e exclusões;
requisições que a omitem ainda podem sobrescrever alterações anteriores.
O bloqueio de linha e a comparação ocorrem na mesma transação.

### Colisão de IDs locais

O índice único da migration 002 continua existindo. Repetir POST com o mesmo
`legacy_local_id` no mesmo workspace agora retorna **409**, sem sobrescrever
o cliente nem apresentar um erro SQL interno.

Isso **não implementa importação idempotente**. Dois computadores podem ter
registros diferentes com o mesmo ID local. A próxima PR deve criar uma
identidade de origem/dataset, prévia de importação e mapeamento
`(workspace, origem, id local) -> id remoto`. Não usar POST repetido como
mecanismo de migração nem deduplicar clientes automaticamente por nome.

### Health e aplicação local

`/health/db` verifica a consulta dos campos necessários ao contrato atual,
incluindo `versao`. Banco acessível com schema antigo retorna **503**, sem
expor o erro SQL. Isso não verifica autenticação nem todas as permissões de escrita.

Depois de atualizar o código, aplique as migrations somente no ambiente local:

```bash
npm run db:status
npm run db:migrate
```

Não executar essa migration em produção automaticamente. Antes de habilitar
o contrato em outro ambiente, validar backup, plano de aplicação e os testes.

Rollback de código: voltar a versão anterior da API e manter as colunas
aditivas no banco. Não apagar as novas colunas, pois podem conter dados.
O frontend continua usando localStorage nesta etapa.

## Próximo passo

Preparar importação idempotente e depois o adapter de Clientes por uma
configuração explícita. O modo remoto não deve trocar para escrita local
silenciosamente quando a API falhar.

Depois de validar a API em dois computadores usando o mesmo staging:

1. adicionar feature flag no frontend;
2. importar clientes do `socialmei-app-data-v2`;
3. manter snapshot local e, se necessário, cache de leitura identificado como desatualizado;
4. comparar local x remoto;
5. só então tornar o remoto a fonte principal.

## Importação de Clientes — migration 004

Rotas exclusivas para migração controlada:

```text
POST /api/v1/clientes/importacoes/preview
POST /api/v1/clientes/importacoes/confirmar
```

As duas recebem o mesmo lote:

```json
{
  "origem": "11111111-1111-4111-8111-111111111111",
  "itens": [
    {
      "local_id": 42,
      "cliente": {
        "nome": "Maria",
        "cidade": "Belo Jardim"
      },
      "extras": {
        "campoLegadoNaoMapeado": "valor preservado"
      }
    }
  ]
}
```

O futuro adapter deve gerar e persistir um UUID **por dataset**, antes da
primeira importação. Reutilize a mesma origem em novas tentativas, lotes e
cópias desse dataset em outro computador. Datasets independentes recebem
origens diferentes. Gerar uma origem a cada tentativa causa duplicatas;
a API não infere identidade de pessoas por nome, telefone ou computador.
Registros com mesmo nome em origens distintas permanecem separados.

`cliente` segue o contrato validado de Clientes. Não envie `legacy_local_id`:
use `local_id` no item. Campos adicionais devem ir em `extras`. A tabela
`crm_cliente_importacoes` guarda o snapshot normalizado completo do item e
o mapeamento `(workspace, origem, local_id) -> cliente_id`; os clientes
importados mantêm `legacy_local_id` nulo para evitar o índice legado global.
Clientes já criados pelo POST antigo não são associados automaticamente.
Preserve também o backup original do navegador antes de transformar os dados.

Limites: 1–500 itens e até 2 MB de JSON serializado por lote. IDs devem ser
inteiros seguros de JavaScript, sem repetição no lote. A validação ocorre
antes de escrever no banco. `extras` fica apenas no snapshot de importação,
sem participar do perfil exibido pelo CRUD.

A prévia não escreve no banco nem cria workspace. Cada resultado contém
`local_id`, `cliente_id` e `acao`:

| Ação        | Significado                                            |
| ----------- | ------------------------------------------------------ |
| `criar`     | Não existe mapeamento para essa origem e ID            |
| `existente` | O mesmo snapshot já foi importado; devolve o ID remoto |
| `conflito`  | A origem e o ID já existem com outro snapshot          |
| `excluido`  | O cliente remoto foi excluído após a importação        |

`pode_importar` indica se não há conflitos ou exclusões na prévia. A prévia
não reserva dados: a confirmação sempre verifica novamente na transação.

A confirmação importa o lote inteiro ou retorna **409** sem importar
nenhum item. Repetir um lote idêntico devolve os mesmos IDs sem alterar
clientes, versões ou snapshots. Alterações feitas pelo CRUD remoto continuam
preservadas. Um snapshot local modificado retorna conflito e exige resolução
explícita; esta etapa não sincroniza nem mescla edições locais.

Excluir um cliente mantém o mapeamento como tombstone (`cliente_id: null`),
impedindo recriação silenciosa em novas tentativas. Não troque a origem para
contornar esse conflito. Clientes e mapeamentos são gravados na mesma
transação; chamadas concorrentes do workspace são serializadas pelo bloqueio
de `ensure_workspace`. A resposta é enviada depois do commit.

A migration 004 é aditiva. O health check agora exige também a tabela de
importação. Aplicação e rollback seguem as instruções locais acima; manter
a tabela no rollback evita perder snapshots e identidade de importação.
O frontend e a produção continuam sem ativação remota nesta etapa.

## Frontend: Clientes no modo remoto

O padrão em `frontend/config.js` continua sendo `mode: "local"`. Em uma
cópia de desenvolvimento/staging, após aplicar as migrations e verificar
`/health/db`, configure explicitamente:

```js
clientes: {
  mode: "remote",
  apiBaseUrl: "http://localhost:8000/api/v1",
  workspaceKey: "development"
}
```

`workspaceKey` identifica os vínculos do navegador e deve corresponder ao
workspace fixo configurado na API. Não escolhe nem autoriza um workspace no
servidor. Ao trocar o workspace no backend, troque também essa chave. Dois
computadores precisam apontar para a **mesma API acessível pela rede**, com
a mesma chave; `localhost` em computadores distintos significa APIs distintas.
Esta configuração não torna a API apropriada para exposição pública.

Para frontend em outra origem, configure no backend
`SOCIALMEI_CORS_ORIGINS` com origens exatas separadas por vírgula. O Compose
de desenvolvimento permite `http://localhost:5500` e
`http://127.0.0.1:5500`; ajuste para portas diferentes. CORS não autentica
usuários. Wildcard é rejeitado, credenciais do navegador não são enviadas
e nenhuma credencial privada deve entrar em `config.js`.

No modo remoto:

- a lista começa vazia e é carregada da API, sem mostrar a demonstração como
  se fosse compartilhada;
- falhas de rede, respostas inválidas e conflitos aparecem no painel de
  Clientes; a última lista da sessão pode continuar visível, mas alterações
  ficam bloqueadas até recarregar;
- criar, editar, excluir, observar e etiquetar passam pela API. PATCH e
  DELETE enviam a versão lida antes da edição/confirmação;
- a criação usa a confirmação idempotente de importação, com uma origem
  persistida por cadastro. Após perda da resposta, recarregue a lista e
  reenvie os mesmos campos. Um cadastro pendente com outros campos é
  bloqueado para evitar duplicação; erro 422 permite corrigir os campos;
- mensagens recebidas do n8n não criam clientes automaticamente. Cadastre
  o perfil explicitamente pela Caixa;
- os vínculos remotos das conversas são separados de `clientId` local, por
  API e workspace. Nomes iguais não são associados automaticamente ao servidor;
- vendas, financeiro, preferências e conversas continuam locais. Renomear
  um cliente atualiza vínculos locais inequívocos depois da aceitação remota.
  Falha ao salvar esses vínculos locais é informada sem desfazer o servidor.

### Importação pelo navegador

Em Clientes, escolha **Importar clientes locais**, confira a prévia e
confirme. Esse fluxo importa até 500 clientes do snapshot local. Campos
conhecidos são enviados em `cliente`; extensões ficam em `extras`.
Origem e mapeamento são persistidos com as chaves
`socialmei-client-origin-v1` e `socialmei-client-links-v1`, incluídas no backup.
Não apague essas chaves nem gere uma nova origem para repetir a importação.
Copiar um backup preserva a identidade do dataset.

O snapshot local de Clientes permanece na chave principal. Salvar outros
módulos no modo remoto não substitui esse snapshot pelos clientes do servidor.
O backup exporta o snapshot local e, separadamente, `remoteClientsSnapshot`,
identificado com a API/workspace e data de exportação. Essa cópia remota é
apenas uma exportação, não cache de leitura nem mecanismo de restauração.
Restaurar backup local exige modo local; depois confira a prévia antes de
importar para a API.

O botão **Recarregar** busca alterações feitas em outro computador. Não há
polling de Clientes nem sincronização offline nesta etapa. Uma recarga da
página sempre consulta o servidor. Para rollback, volte a configuração para
`mode: "local"`: o snapshot local é recuperado, mas alterações remotas não
são mescladas automaticamente. Preserve o backup com o snapshot remoto.

Validação: testes de adapter cobrem falhas, conflitos, criação idempotente e
separação dos IDs. Os fluxos de navegador usam uma API simulada para testar
UI, duas sessões, importação, CRUD e Caixa. Os testes Python com PostgreSQL
validam a persistência real; um ensaio em dois computadores no mesmo staging
continua necessário antes de habilitar esse modo para a equipe.

### Teste em outro dispositivo na mesma rede local

Use uma rede privada de confiança e clientes fictícios: a API de desenvolvimento
não autentica usuários. Não encaminhe portas no roteador nem use esse modo para
publicar na internet. O notebook precisa ficar ligado e ambos os dispositivos
precisam acessar a mesma rede sem isolamento entre clientes Wi-Fi.

Para um notebook com IPv4 `192.168.0.3` (substitua pelo IP da sua interface),
configure em `.env.development`:

```dotenv
DEV_BIND_HOST=192.168.0.3
SOCIALMEI_CORS_ORIGINS=http://192.168.0.3:5500,http://localhost:5500,http://127.0.0.1:5500
```

Em `frontend/config.js`, mantenha modo remoto e a chave do workspace, mudando
`apiBaseUrl` para `http://192.168.0.3:8000/api/v1`. Execute `npm run dev` para
recriar os serviços. Acesse `http://192.168.0.3:5500` no notebook e no celular.
Caso o Windows solicite liberação de firewall, permita somente na rede privada.

A opção `DEV_BIND_HOST` afeta somente frontend e API. PostgreSQL, n8n, pgAdmin
e WAHA continuam vinculados a loopback. Ela é opt-in e o padrão continua
`127.0.0.1`. Se o IP mudar, atualize a configuração e reinicie os serviços.
O adapter usa UUID criptográfico também em navegadores HTTP sem `randomUUID`.

Ao mudar de `localhost` para o IP, o armazenamento do navegador muda de origem.
Exporte o backup local antes da troca se precisar importar dados antigos. O banco
remoto permanece o mesmo. Vínculos locais da Caixa não são migrados automaticamente
entre essas origens. Ao concluir, restaure `DEV_BIND_HOST=127.0.0.1`, a URL da API
para localhost e as origens CORS anteriores, e execute `npm run dev` novamente.

## Catálogo compartilhado — migration 005

`005_shared_catalog.sql` cria `crm_produtos` e `crm_produto_importacoes` sem
alterar o cadastro local, Clientes ou as tabelas de atendimento. O health check
passa a exigir também essas tabelas. Aplique com `npm run db:migrate` somente
no desenvolvimento local; aplicação em outro ambiente exige preparação própria.

```text
GET    /api/v1/produtos
POST   /api/v1/produtos
GET    /api/v1/produtos/{id}
PATCH  /api/v1/produtos/{id}
DELETE /api/v1/produtos/{id}?expected_version=1
POST   /api/v1/produtos/{id}/estoque
POST   /api/v1/produtos/importacoes/preview
POST   /api/v1/produtos/importacoes/confirmar
```

Contrato: `nome`, `tipo` (`Produto` ou `Serviço`), `preco`, `custo`, `estoque`,
`minimo` e `status`. GET inclui `id`, `versao`, `criado_em` e `atualizado_em`.
Nome/status não podem estar vazios; valores monetários são finitos e não negativos.
Estoque e mínimo são inteiros seguros não negativos. Produtos exigem ambos;
quando omitidos na criação, começam em zero. Serviços possuem ambos nulos e
rejeitam valores de estoque. A conversão entre tipos exige enviar explicitamente
estoque/mínimo válidos para o novo tipo.

PATCH exige `expected_version`, mantém campos omitidos e valida o registro
completo antes de salvar. DELETE também exige versão. Conflitos retornam 409.
Ajustes de estoque recebem `{ "delta": -1, "expected_version": 2 }`: bloqueio,
comparação e gravação ocorrem na mesma transação. Uma operação aceita incrementa
a versão; estoque negativo ou acima do limite é rejeitado, sem arredondar para
zero. Repetir a mesma requisição com a versão anterior não aplica o delta duas
vezes. Serviços rejeitam ajustes. Ainda não há reserva de estoque ou movimentação
automática por vendas: essa transação será implementada na etapa de Vendas.

Importação usa `{ "origem": "UUID", "itens": [{ "local_id": 1, "produto":
{ "nome": "Camiseta", "tipo": "Produto", "preco": 30, "custo": 10,
"estoque": 5, "minimo": 2 }, "extras": {} }] }`. Mantém os mesmos limites e
semântica de Clientes: prévia sem escrita, lote atômico, mapeamento por origem,
snapshot normalizado, tombstones e conflito para conteúdo local modificado.
Datasets distintos podem usar o mesmo ID local. Não associa automaticamente
itens por nome. A criação pela interface usa essa confirmação idempotente com
uma identidade persistida por cadastro.

O catálogo permanece local por padrão, inclusive quando `produtos` não existe
na configuração. Para ativar explicitamente, acrescente à configuração pública:

```js
produtos: {
  mode: "remote",
  apiBaseUrl: "http://192.168.0.3:8000/api/v1",
  workspaceKey: "development"
}
```

Use a URL do seu ambiente e a chave que corresponde ao workspace fixo da API.
Clientes e Catálogo podem ser ativados independentemente. Não há credenciais
privadas no frontend; a API continua limitada a testes em rede privada.

O painel de Produtos e Serviços informa conexão, falhas e oferece Recarregar
ou Importar catálogo local. As duas ações de ajuste de estoque da interface
usam o endpoint transacional. Edição/exclusão usam a versão capturada ao abrir
os formulários. Falhas não trocam a fonte para escrita local e não alteram o
estoque mostrado como se a operação tivesse sido aceita.

O snapshot de produtos locais permanece na chave principal, mesmo ao salvar
Clientes, preferências ou outros módulos. Backup inclui `remoteProductsSnapshot`
separado, com origem e data. Identidade de dataset, mapeamento e cadastro pendente
usam `socialmei-product-origin-v1`, `socialmei-product-links-v1` e
`socialmei-product-create-pending-v1`. Não apague essas chaves para repetir operações.
Restaurar backup exige Clientes e Catálogo locais; cópias remotas exportadas não
são importadas automaticamente.

Vendas locais continuam registrando nome/preço como snapshots. Editar ou excluir
um item remoto não reescreve vendas passadas. IDs entre módulos serão vinculados
na etapa de Vendas; o financeiro continua local. Para rollback, desative somente
`produtos` e preserve as tabelas/mapeamentos, evitando perda de dados remotos.

Validação cobre produtos/serviços, conversão de tipo, conflitos de versão,
ajuste concorrente e negativo, importação repetida e isolamento por workspace.
Os testes de UI usam API simulada em duas sessões; os testes Python validam
persistência e transações no PostgreSQL. Validar notebook/celular com a API real
antes de habilitar para a equipe.

## Vendas compartilhadas — migration 006

A migration `006_shared_sales.sql` cria vendas, identidade de operações e
mapeamento de importação. O health check passa a exigir as três tabelas.
Vendas preservam os nomes, preço, quantidade, desconto, data e pagamento como
snapshots históricos, junto com IDs de cliente/produto quando disponíveis.

```text
GET   /api/v1/vendas
POST  /api/v1/vendas
GET   /api/v1/vendas/{id}
PATCH /api/v1/vendas/{id}
POST  /api/v1/vendas/{id}/registrar
POST  /api/v1/vendas/{id}/pagar
POST  /api/v1/vendas/{id}/cancelar
POST  /api/v1/vendas/{id}/excluir
POST  /api/v1/vendas/importacoes/preview
POST  /api/v1/vendas/importacoes/confirmar
```

### Contrato e efeitos de estoque

Criação recebe `operation_id` (UUID), `cliente_id`, `produto_id`, `data`,
`quantidade`, `preco`, `desconto`, `pagamento`, `observacao` e `status` inicial
(`Pendente` ou `Rascunho`). Quantidade é inteiro seguro positivo. Valores
monetários usam Decimal e NUMERIC(15,2), são não negativos e têm até duas casas.
O servidor calcula `valor = preco * quantidade - desconto`, rejeitando desconto
acima do subtotal ou total acima do limite. Cliente e produto precisam pertencer
ao workspace fixo do ambiente. Não são associados por nome.

| Operação                  | Efeito de estoque                                                        |
| ------------------------- | ------------------------------------------------------------------------ |
| Criar pendente            | Baixa unidades de um Produto; Serviço não movimenta estoque              |
| Criar/duplicar rascunho   | Nenhuma movimentação                                                     |
| Registrar rascunho        | Aplica a baixa uma vez e passa a Pendente                                |
| Marcar pendente como paga | Mantém a baixa existente                                                 |
| Marcar rascunho como paga | Aplica a baixa uma vez e passa a Pago                                    |
| Editar pendente           | Ajusta a diferença de quantidade ou estorna item anterior e baixa o novo |
| Editar rascunho           | Não movimenta estoque                                                    |
| Cancelar/excluir          | Estorna somente a quantidade aplicada por essa venda                     |
| Importar histórico        | Nunca movimenta estoque                                                  |

Todos os efeitos, a venda e o registro de operação usam a mesma transação.
O bloqueio do workspace serializa alterações de vendas/catálogo. Linhas de
produto também são bloqueadas. Estoque insuficiente, saldo negativo, estorno
acima do limite ou vínculo inválido rejeitam a operação inteira.

Produtos com vendas que aplicaram estoque não podem ser excluídos nem convertidos
em Serviço antes de cancelar essas vendas. Serviços e clientes excluídos deixam
os snapshots históricos preservados. Alterar preço/nome do catálogo não altera
vendas passadas. Vendas pagas/canceladas ou importadas não permitem edição dos
campos; duplique como rascunho para iniciar outra venda com vínculos atuais.
Canceladas não são reativadas.

PATCH envia todos os campos editáveis e exige `expected_version`; ações exigem
`operation_id` e `expected_version`. Uma versão desatualizada retorna 409.
Excluir é lógico: a venda fica cancelada e oculta na lista, mantendo histórico
e identidade. Não existe DELETE físico de vendas nesta API.

### Idempotência e resposta perdida

A chave `(workspace, operation_id)` guarda hash de rota, ação e payload, mais
resposta aceita. Repetir a mesma operação retorna essa resposta, sem repetir
baixa ou estorno, mesmo com a versão antiga. Reutilizar o UUID com outros campos
retorna 409. Duas vendas concorrentes com UUIDs distintos também não podem vender
mais unidades do que o saldo disponível.

Uma resposta repetida representa a aceitação original, podendo anteceder outra
edição da venda. Após uma operação, o adapter recarrega a lista atual e o catálogo.
A interface mantém a identidade pendente em `socialmei-sale-operation-pending-v1`
antecedendo a chamada de escrita. Após falha de rede, use **Recuperar operação
pendente**; não gere outra identidade para tentar de novo. Rejeições definitivas
404/409/422 liberam a identidade. Falha numa leitura posterior é informada como
operação já salva, sem desfazer ou repetir a escrita.

### Histórico local e frontend

Ativação explícita em `config.vendas`, com a mesma URL/workspace de Clientes e
Catálogo. Os três precisam estar remotos para criar/editar vendas vinculadas.
Sem a configuração, Vendas continua local. O formulário remoto seleciona IDs,
exibe o nome e identificador para distinguir cadastros com nomes iguais, preenche
o preço atual do item como sugestão e permite conferir o preço antes de salvar.
Rascunhos têm ação explícita **Registrar venda**.

```js
vendas: {
  mode: "remote",
  apiBaseUrl: "http://192.168.0.3:8000/api/v1",
  workspaceKey: "development"
}
```

A importação recebe `{ origem, itens: [{ local_id, venda, extras }] }`. Em `venda`,
`cliente`, `item`, `data`, `valor` e status preservam o registro histórico;
quantidade ausente é 1 e preço ausente é nulo. O valor histórico não é recalculado.
IDs opcionais só são preenchidos a partir dos mapeamentos das importações de
Clientes/Catálogo e de nomes locais inequívocos. Sem mapeamento, o histórico fica
sem vínculo remoto. Importe as bases antes das vendas, sem inventar IDs.
O original completo fica em `extras.original_local` na importação da interface.

Prévia não escreve; confirmação é atômica, com até 500 itens/2 MB, conflitos,
origens separadas e tombstone para venda excluída. Vendas importadas são sinalizadas
como histórico e não baixam/estornam estoque ao pagar, cancelar ou excluir.
Isso evita movimentar novamente um saldo que já pode refletir vendas antigas.

O snapshot local permanece na chave principal. Exportação inclui
`remoteSalesSnapshot`, identificado por API/workspace e data, separado do backup
local. Restauração exige todos os módulos em modo local. Origem/mapeamento usam
`socialmei-sale-origin-v1` e `socialmei-sale-links-v1`; preserve essas identidades.

**Financeiro continua local e separado**: marcar como paga registra o status da
venda; não cria recebimento. Cancelar/excluir não apaga lançamentos financeiros.
Não associe uma venda remota a lançamentos locais apenas porque têm o mesmo número.
A migração e transação de recebimentos ficam para a próxima etapa.

Rollback: volte `vendas` para local, mantendo tabelas e registros remotos. Estoque
já movimentado não é revertido pelo rollback de configuração; preserve backups e
reconcilie os dados antes de retomar operações locais. Não apague volumes ou tabelas.

Validação automática inclui baixa/estorno único após replay, concorrência sem
overselling, edição com troca de item, rollback por estoque insuficiente, serviços,
rascunhos, pagamentos, importação sem estoque e isolamento por workspace. UI é
exercitada com API simulada em duas sessões; persistência real usa PostgreSQL.
O ensaio manual principal é registrar e cancelar uma venda entre notebook/celular,
conferindo que o estoque muda uma única vez.

## Financeiro compartilhado (opt-in)

A migration `007_shared_finance.sql` cria lançamentos, operações e importações. A
configuração `SOCIALMEI_CONFIG.financeiro` aceita `mode: "remote"`, `apiBaseUrl` e
`workspaceKey`, exigindo Clientes remotos na mesma API/workspace. Sem essa chave,
o Financeiro permanece local. A configuração padrão do repositório não ativa o
modo remoto nem altera produção.

| Operação  | Endpoint                                        | Contrato                                                                   |
| --------- | ----------------------------------------------- | -------------------------------------------------------------------------- |
| Listar    | `GET /api/v1/financeiro`                        | Apenas lançamentos não excluídos do workspace configurado no servidor      |
| Consultar | `GET /api/v1/financeiro/{id}`                   | 404 para ID inexistente, excluído ou de outro workspace                    |
| Criar     | `POST /api/v1/financeiro`                       | Campos, `operation_id` UUID e `status` aberto/pago                         |
| Editar    | `PATCH /api/v1/financeiro/{id}`                 | Campos completos, `expected_version` e `operation_id`; apenas não quitados |
| Quitar    | `POST /api/v1/financeiro/{id}/pagar`            | `expected_version` e `operation_id`; receita recebida ou despesa paga      |
| Excluir   | `POST /api/v1/financeiro/{id}/excluir`          | Mesmo contrato de ação; exclusão lógica, fora da lista e dos totais        |
| Prévia    | `POST /api/v1/financeiro/importacoes/preview`   | `origem` UUID e `itens` com `local_id`, `lancamento` e `extras`            |
| Importar  | `POST /api/v1/financeiro/importacoes/confirmar` | Reavalia e aplica o lote inteiro em uma transação                          |

Campos: `descricao` (1–240 caracteres), `pessoa` (até 160), `tipo`
(`receita`/`despesa`), `valor` (Decimal não negativo, até 13 inteiros e 2 casas),
`vencimento` (data válida) e `cliente_id` opcional. Novos vínculos são validados
no workspace; o servidor copia o nome do cliente em `pessoa`. Exclusão do cliente
remove só o vínculo, mantendo o nome histórico. Não se infere vínculo por nome
nem por texto `Venda #...` quando Financeiro ou Vendas são remotos.

Todas as escritas exigem uma identidade UUID. O workspace é bloqueado para
serializar alterações: a mesma identidade e os mesmos dados retornam a resposta
original; UUID reutilizado com outros dados dá 409. Versão desatualizada também dá 409. A alteração e o registro da resposta são atômicos. Quitar um lançamento já
quitado com a versão atual é uma operação sem alteração de versão. Quitados não
permitem edição ou reabertura. Exclusão preserva os dados e a resposta original
no servidor, mas retira o valor dos totais exibidos.

`data_pagamento` é a data de quitação registrada pelo servidor; importação aceita
uma data histórica explícita e mantém `null` quando ela não existia, sem inventar
uma data. Importação preserva `aberto`, `atrasado` e `pago`, além dos campos extras
no snapshot. A UI deriva atraso de vencimento/status, como no modo local. Gráficos
existentes continuam agrupando por vencimento; não representam fluxo de caixa
por data de pagamento. Não há geração automática de recebimentos, alteração de
vendas ou movimentação de estoque por ações do Financeiro.

Importações têm até 500 itens/2 MB por lote, IDs locais únicos e mapa por
workspace/origem/ID local. Repetir a importação não duplica; dados alterados ou
registro previamente excluído bloqueiam todo o lote. O frontend mapeia clientes
somente pelo mapa de importação local conhecido e por nome local inequívoco;
sem esse mapa, mantém `pessoa` sem vínculo. Recomenda-se importar Clientes antes.
Snapshots e identidades de cada navegador precisam ser mantidos: usar uma nova
origem para o mesmo histórico pode duplicá-lo.

O frontend preserva os lançamentos locais ao salvar preferências e outras áreas;
backup exporta `remoteFinanceSnapshot` separado. Resposta perdida mantém a
operação original em `socialmei-finance-operation-pending-v1`, inclusive após
reabrir a página: **Recuperar operação pendente** reenvia o UUID original. Uma
outra escrita fica bloqueada até resolver a operação. Falha de leitura posterior
à confirmação não desfaz a gravação; exibe aviso e bloqueia novas escritas até
recarregar. Falha da API não ativa fallback local.

Restaurar backup completo exige todos os módulos em modo local. Voltar o
Financeiro para local apenas mostra o snapshot local preservado; não copia,
reabre ou apaga lançamentos remotos. Teste no notebook/celular após ativação:
criar uma entrada, recarregar no segundo aparelho e marcar recebida; o primeiro
aparelho deve ver a mesma quitação após recarregar. Não execute implantação em
produção como parte dessa ativação local.

## Transferência inicial entre workspaces

A migration 008 e `/api/v1/transferencias/preview` / `confirmar` permitem uma
transferência inicial do banco development para team, com preservação de estados
operacionais de estoque e remapeamento de IDs. O contrato, os limites e os passos
de aplicação estão em [TRANSFERENCIA-NOTEBOOK.md](TRANSFERENCIA-NOTEBOOK.md).
