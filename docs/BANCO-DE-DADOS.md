# Banco de dados — SocialMEI.IA

## Objetivo

O PostgreSQL já faz parte da infraestrutura do projeto. Na Sprint 3 ele passa a guardar o histórico da Caixa Unificada de forma persistente.

A equipe não deve depender do computador de um integrante para acessar o banco. O acesso será feito pelo servidor, usando **pgAdmin no navegador** e contas individuais sempre que possível.

## Arquitetura

```text
Equipe
  ↓ HTTPS
pgAdmin
  ↓ rede Docker
PostgreSQL
  ↑
 n8n
  ↑
Webhooks
```

A porta 5432 do PostgreSQL continua **sem ser publicada diretamente na internet**.

## Estrutura inicial

O arquivo versionado em `database/schema.sql` cria o schema `socialmei` com:

- `socialmei.clientes`
- `socialmei.conversas`
- `socialmei.mensagens`

As tabelas internas do n8n continuam separadas.

## Como acessar

O endereço do pgAdmin é definido por `PGADMIN_HOST` no `.env` do servidor.

Acesso web atual:

```text
https://db.54-94-213-7.sslip.io
```

Endereço confirmado no ambiente atual: `https://db.54-94-213-7.sslip.io`.

Nunca coloque usuário ou senha real no GitHub.

## Primeiro acesso

1. Um administrador define `PGADMIN_DEFAULT_EMAIL` e `PGADMIN_DEFAULT_PASSWORD` no `.env` da VPS.
2. A infraestrutura é atualizada.
3. O administrador entra no pgAdmin.
4. Registra o servidor PostgreSQL usando host `postgres`, porta `5432`, banco e credenciais do ambiente.
5. Cria contas individuais de pgAdmin para os integrantes que precisam de acesso.

## Alterando a estrutura

Mudanças de tabela devem ficar registradas no GitHub.

Não faça uma alteração estrutural importante somente pelo painel sem também criar/atualizar um arquivo de migração no repositório.

Fluxo recomendado:

```text
branch → arquivo SQL → revisão → teste → merge → aplicar no banco
```

## Permissões

Para evitar compartilhar o usuário administrador do PostgreSQL, a equipe deve criar roles individuais conforme necessidade.

Sugestão:

- leitura: consultas e inspeção;
- desenvolvimento: leitura e escrita no schema `socialmei`;
- administração: somente para responsáveis pela infraestrutura.

As senhas dessas contas nunca devem ser salvas no repositório.

## Segurança

- não expor a porta 5432;
- não publicar `.env`;
- não salvar senha em documentação;
- não usar o mesmo login para toda a equipe;
- fazer backup antes de migrations destrutivas;
- revisar SQL antes de aplicar em produção.
