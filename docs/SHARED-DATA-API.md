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
