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

## Próximo passo

Depois de validar a API em dois computadores usando o mesmo staging:

1. adicionar feature flag no frontend;
2. importar clientes do `socialmei-app-data-v2`;
3. manter fallback local;
4. comparar local x remoto;
5. só então tornar o remoto a fonte principal.
