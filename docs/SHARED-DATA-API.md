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
