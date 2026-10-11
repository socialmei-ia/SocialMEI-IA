# Migração de persistência — localStorage → API + PostgreSQL

Este documento prepara a próxima fase do SocialMEI: fazer os dados do negócio deixarem de depender de um navegador específico.

## Problema atual

Hoje existem dois tipos de estado:

```text
Estado local do navegador
  -> clientes
  -> vendas
  -> produtos
  -> financeiro
  -> preferências
  -> rascunhos
  -> parte do estado da Caixa

Estado remoto já existente
  -> histórico de atendimento via n8n/PostgreSQL
```

Isso significa que dois computadores podem abrir o mesmo frontend e enxergar dados de gestão diferentes.

A meta é chegar a:

```text
PC A ─┐
PC B ─┼─> API SocialMEI ─> PostgreSQL
PC C ─┘
```

## Chaves locais que existem hoje

As chaves abaixo foram identificadas no frontend atual.

### Gestão principal

- `socialmei-app-data-v2`
  - `clientes`
  - `vendas`
  - `produtos`
  - `financeiro`
  - `prefs`

### Caixa / atendimento local

- `socialmei-inbox-local-v3`
- `socialmei-inbox-drafts-v1`
- `socialmei-inbox-quick-v3`
- `socialmei-inbox-sort-v3`
- `socialmei-inbox-tag-v3`
- `socialmei-inbox-details-v3`

### Experiência / automações / assistente

- `socialmei-experience-profile-v1`
- `socialmei-experience-screen`
- `socialmei-current-view`
- `socialmei-ai-drafts-v1`
- `socialmei-automation-drafts-v1`
- `socialmei-automation-tests-v1`

### Preferências locais

- `socialmei-active-theme`
- `socialmei-custom-themes`
- `socialmei-theme`
- `socialmei-hide-money`
- `socialmei-sidebar-compact-v2`
- `socialmei_public_theme`

Nem tudo precisa ir para o servidor. Tema, sidebar e preferências puramente visuais podem continuar locais.

## Dados principais a migrar

### Clientes

Contrato atual aproximado:

```json
{
  "id": 1,
  "nome": "Maria Silva",
  "telefone": "(81) 99981-2040",
  "instagram": "@maria.silva",
  "status": "Ativo",
  "ultima": "Hoje",
  "total": 1840,
  "pendente": 0,
  "observacao": "Prefere atendimento pelo WhatsApp.",
  "tags": ["Cliente recorrente"]
}
```

No backend, campos derivados como `total`, `pendente` e `ultima` não devem necessariamente ser armazenados como fonte de verdade. Eles podem ser calculados a partir de vendas, lançamentos e interações.

### Produtos / serviços

```json
{
  "id": 1,
  "nome": "Camisa Tech SocialMEI",
  "tipo": "Produto",
  "preco": 89.9,
  "custo": 46,
  "estoque": 3,
  "minimo": 5,
  "status": "Ativo"
}
```

### Vendas

```json
{
  "id": 1042,
  "item": "Conjunto Essentials",
  "quantidade": 2,
  "cliente": "Maria Helena Costa",
  "data": "2026-10-06",
  "valor": 380,
  "pagamento": "Pix",
  "status": "Pago"
}
```

A API futura deve substituir referências por nome por IDs estáveis de cliente/produto.

### Financeiro

```json
{
  "id": 1,
  "descricao": "Venda #1042",
  "pessoa": "Maria Helena Costa",
  "tipo": "receita",
  "valor": 380,
  "vencimento": "2026-10-06",
  "status": "pago"
}
```

## Decisão que vem antes do CRUD remoto

Antes de criar tabelas definitivas para gestão, precisamos definir a fronteira de identidade:

```text
usuário
  pertence a
negócio/workspace
  possui
clientes, produtos, vendas, financeiro
```

Mesmo que o projeto comece com um único negócio, a estrutura do banco não deve assumir que todos os dados do sistema pertencem para sempre a uma única pessoa.

A proposta para a próxima fase é usar:

```text
workspaces
users
workspace_members

clientes          -> workspace_id
produtos          -> workspace_id
vendas            -> workspace_id
lancamentos       -> workspace_id
conversas         -> workspace_id
```

Autenticação real ainda precisa ser definida antes de produção.

## Ordem de migração recomendada

### Fase A — infraestrutura de API

Criar:

- conexão da FastAPI com PostgreSQL;
- configuração por environment variables;
- health check incluindo banco;
- camada simples de acesso a dados;
- migrations para identidade/workspace;
- testes HTTP e SQL em banco isolado.

Nada do frontend muda nesta fase.

### Fase B — Clientes

Primeiro módulo remoto:

```text
GET    /api/v1/clientes
POST   /api/v1/clientes
GET    /api/v1/clientes/{id}
PATCH  /api/v1/clientes/{id}
DELETE /api/v1/clientes/{id}
```

O frontend continua com fallback local durante a transição.

Critério de aceite:

1. criar cliente no computador A;
2. abrir computador B;
3. o mesmo cliente aparece;
4. editar no B;
5. recarregar no A;
6. alteração permanece.

### Fase C — Produtos

Depois que Clientes estiver estável:

```text
GET/POST/PATCH/DELETE /api/v1/produtos
```

### Fase D — Vendas

Vendas passam a usar IDs de cliente e produto.

### Fase E — Financeiro

Lançamentos passam a poder referenciar vendas e clientes.

### Fase F — Caixa / contexto

Unificar o histórico já persistido com IDs estáveis de workspace/cliente/conversa.

## Estratégia para não perder dados existentes

Não vamos apagar `socialmei-app-data-v2` de uma vez.

A transição deve ser:

```text
1. usuário continua com dados locais
2. frontend detecta backend disponível
3. oferece importar dados locais
4. API valida payload
5. servidor grava e devolve resumo
6. frontend confirma importação
7. localStorage fica como fallback/backup temporário
8. depois de uma versão estável, deixa de ser fonte principal
```

O backup JSON atual deve continuar funcionando durante a migração.

## Feature flag

Durante a implementação, usar uma configuração explícita:

```js
dataMode: "local" | "remote"
```

ou equivalente.

Não misturar silenciosamente dados locais e remotos.

A interface deve deixar claro quando está em:

- demonstração local;
- staging remoto;
- produção.

## O que continua local

Preferências visuais podem continuar no navegador:

- tema;
- sidebar compacta;
- esconder valores;
- filtros momentâneos;
- estado visual de painéis.

## O que deve virar remoto

Prioridade:

1. clientes;
2. produtos/serviços;
3. vendas;
4. financeiro;
5. identidade do negócio;
6. contexto persistente necessário para automações.

## Regras de segurança

Antes de expor CRUD remoto:

- não confiar em `workspace_id` enviado pelo frontend;
- autenticar usuário;
- autorizar acesso ao workspace;
- validar payloads no servidor;
- limitar tamanho de campos;
- registrar erros sem dados pessoais desnecessários;
- não colocar senha/token em `frontend/config.js`;
- não usar CORS `*` em produção para dados privados.

## Próxima PR funcional

A próxima PR de backend deve ser pequena:

**"Criar fundação de persistência compartilhada"**

Escopo recomendado:

- conexão FastAPI → PostgreSQL;
- migrations `workspaces`, `users`, `workspace_members`;
- endpoint de health do banco;
- CRUD de clientes em staging/local;
- testes;
- sem remover o localStorage ainda.

Assim conseguimos provar compartilhamento real sem migrar quatro módulos de uma vez.
