-- SocialMEI.IA - permissões do usuário técnico das automações
-- Não contém senha. Defina a senha fora do GitHub.
-- Pré-requisitos: role socialmei_admin, schema socialmei e tabelas criadas.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'socialmei_app') THEN
    CREATE ROLE socialmei_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;

GRANT CONNECT ON DATABASE n8n TO socialmei_app;
GRANT USAGE ON SCHEMA socialmei TO socialmei_app;

GRANT SELECT, INSERT, UPDATE
ON ALL TABLES IN SCHEMA socialmei
TO socialmei_app;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA socialmei
TO socialmei_app;

ALTER DEFAULT PRIVILEGES
FOR ROLE socialmei_admin
IN SCHEMA socialmei
GRANT SELECT, INSERT, UPDATE ON TABLES TO socialmei_app;

ALTER DEFAULT PRIVILEGES
FOR ROLE socialmei_admin
IN SCHEMA socialmei
GRANT USAGE, SELECT ON SEQUENCES TO socialmei_app;

-- Depois, defina a senha de forma interativa no psql:
-- \password socialmei_app
