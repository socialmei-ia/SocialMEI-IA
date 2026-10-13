-- Perfil para consulta interna autorizada; NÃO é isolamento de MEIs por sessão.
-- Aplicação administrativa manual no banco team, após backup de dados e roles.
-- Nenhum login ou senha é criado; membros individuais são concedidos separadamente.

DO $access$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'socialmei_team_readonly') THEN
        CREATE ROLE socialmei_team_readonly NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
    -- Não reaproveita silenciosamente um perfil já elevado ou usado como login.
    IF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'socialmei_team_readonly'
          AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION 'Perfil readonly existente incompatível; revisar manualmente.';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO socialmei_team_readonly', current_database());
END;
$access$;

GRANT USAGE ON SCHEMA socialmei TO socialmei_team_readonly;
GRANT SELECT (id, slug, nome, criado_em, atualizado_em)
    ON socialmei.workspaces TO socialmei_team_readonly;
GRANT SELECT ON
    socialmei.schema_migrations,
    socialmei.crm_clientes,
    socialmei.crm_produtos,
    socialmei.crm_vendas,
    socialmei.crm_financeiro,
    socialmei.crm_canais,
    socialmei.crm_conversas_canal,
    socialmei.crm_mensagens_canal,
    socialmei.crm_eventos_canal
    TO socialmei_team_readonly;

-- Sem ALL TABLES, default privileges, hashes, sessões, convites ou auditoria auth.
-- Grants preexistentes precisam de conferência; este script não os revoga.
