-- SocialMEI.IA - bootstrap administrativo do banco
-- Execute uma única vez com um usuário administrador do PostgreSQL.
-- Substitua o nome da role somente se a equipe adotar outra convenção.
-- Este arquivo não contém senhas.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'socialmei_admin') THEN
    RAISE EXCEPTION 'A role socialmei_admin ainda não existe. Crie a role e defina sua senha fora do GitHub.';
  END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS socialmei AUTHORIZATION socialmei_admin;
GRANT CONNECT ON DATABASE n8n TO socialmei_admin;
