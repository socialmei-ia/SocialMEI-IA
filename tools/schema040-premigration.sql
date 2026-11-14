-- Read-only gate for an approved 039 source/copy. No migration or business data output.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '2s';
DO $$
BEGIN
    IF (SELECT array_agg(left(version, 3)::integer ORDER BY version)
        FROM socialmei.schema_migrations) IS DISTINCT FROM ARRAY(SELECT generate_series(1,39)) THEN
        RAISE EXCEPTION 'Expected exact schema039 migration ledger';
    END IF;
    IF to_regclass('socialmei.auth_email_activation') IS NOT NULL
        OR to_regclass('socialmei.auth_identity_mail') IS NOT NULL THEN
        RAISE EXCEPTION 'Unexpected identity structures require review';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE connamespace='socialmei'::regnamespace AND NOT convalidated) THEN
        RAISE EXCEPTION 'Unvalidated constraints require review';
    END IF;
    IF NOT has_schema_privilege(current_user, 'socialmei', 'CREATE') THEN
        RAISE EXCEPTION 'Migration role lacks schema CREATE';
    END IF;
END $$;
SELECT id, email FROM socialmei.users LIMIT 0;
SELECT user_id, senha_hash FROM socialmei.auth_credenciais LIMIT 0;
SELECT token_hash, user_id, workspace_id FROM socialmei.auth_sessoes LIMIT 0;
SELECT workspace_id, user_id, role FROM socialmei.workspace_members LIMIT 0;
SELECT 'schema039_readonly_precheck_passed' AS result;
ROLLBACK;
