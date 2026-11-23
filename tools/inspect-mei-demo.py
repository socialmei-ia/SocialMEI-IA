"""Read-only demo inventory. Run inside the API with its effective connection.

No customer identities, account emails, credentials or message content leave SQL.
The migration ledger records filenames, not checksums: this is not a hash audit.
"""
import json
import sys


def inspect():
    from database import connect
    from psycopg.rows import dict_row

    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout = '8s'")
        conn.execute("SET LOCAL lock_timeout = '1s'")

        def rows(query, params=()):
            return conn.execute(query, params).fetchall()

        identity = rows("SELECT current_database() AS database, current_user AS role, "
                        "current_setting('server_version') AS version, "
                        "inet_server_addr()::text AS server_address, "
                        "pg_database_size(current_database()) AS bytes")[0]
        migrations = rows("SELECT version FROM socialmei.schema_migrations ORDER BY version")
        expected = [f"{n:03}" for n in range(1, 41)]
        actual = [r["version"].split("_")[0] for r in migrations]
        workspaces = rows("SELECT id, nome FROM socialmei.workspaces ORDER BY id")
        counts = {}
        tables = ("crm_clientes", "crm_produtos", "crm_vendas", "crm_financeiro",
                  "agenda_resources", "agenda_appointments", "me_conversations",
                  "me_messages", "workspace_profiles", "workspace_members", "crm_canais")
        for table in tables:
            counts[table] = rows(f"SELECT workspace_id, count(*) AS count "
                                 f"FROM socialmei.{table} GROUP BY workspace_id ORDER BY workspace_id")
        names = {"brilho limpeza": "brilho limpeza", "brilho&limpeza service": "brilho limpeza",
                 "bella store": "bella store", "sorriaodonto": "sorriaodonto", "she style": "she style"}
        targets = []
        for w in workspaces:
            match = next((scenario for name, scenario in names.items() if name in w["nome"].casefold()), None)
            if match:
                targets.append({"id": w["id"], "scenario": match, "members": rows(
                    "SELECT m.user_id, m.role, c.ativo AS active, "
                    "c.administrador_plataforma AS platform_admin, "
                    "a.verified_at IS NOT NULL AS email_verified "
                    "FROM socialmei.workspace_members m "
                    "JOIN socialmei.auth_credenciais c ON c.user_id=m.user_id "
                    "LEFT JOIN socialmei.auth_email_activation a ON a.user_id=m.user_id "
                    "WHERE m.workspace_id=%s ORDER BY m.user_id", (w["id"],))})
        channels = rows("SELECT id, workspace_id, canal, provedor, ativo, envio_habilitado, "
                        "ingress_provisioned FROM socialmei.crm_canais ORDER BY workspace_id,id")
        roles = rows("SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin, "
                     "rolreplication, rolbypassrls FROM pg_roles "
                     "WHERE rolname=current_user OR rolname='socialmei_team_readonly'")
        stats = rows("SELECT schemaname,relname,n_live_tup,n_dead_tup,seq_scan,idx_scan, "
                     "last_autovacuum,last_autoanalyze FROM pg_stat_user_tables "
                     "WHERE schemaname='socialmei' ORDER BY n_live_tup DESC LIMIT 20")
        constraints = rows("SELECT contype,count(*) AS count FROM pg_constraint "
                           "WHERE connamespace='socialmei'::regnamespace GROUP BY contype ORDER BY contype")
        integrity = rows("SELECT count(*) AS unvalidated_constraints FROM pg_constraint "
                         "WHERE connamespace='socialmei'::regnamespace AND NOT convalidated")[0]
        activity = rows("SELECT state,wait_event_type,count(*) AS count, "
                        "max(EXTRACT(EPOCH FROM now()-xact_start))::bigint AS max_transaction_seconds "
                        "FROM pg_stat_activity WHERE datname=current_database() "
                        "GROUP BY state,wait_event_type")
        deadlocks = rows("SELECT deadlocks,stats_reset FROM pg_stat_database WHERE datname=current_database()")
        rls = rows("SELECT count(*) FILTER (WHERE c.relrowsecurity) AS enabled, count(*) AS tables "
                   "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                   "WHERE n.nspname='socialmei' AND c.relkind='r'")
        objects = rows("SELECT n.nspname AS schema,c.relname AS name,c.relkind AS kind, "
                       "pg_total_relation_size(c.oid) AS bytes FROM pg_class c "
                       "JOIN pg_namespace n ON n.oid=c.relnamespace "
                       "WHERE n.nspname='socialmei' AND c.relkind IN ('r','v','m') ORDER BY c.relname")
        indexes = rows("SELECT t.relname AS table_name,i.relname AS index_name,x.indisunique, "
                       "x.indisvalid,pg_relation_size(i.oid) AS bytes FROM pg_index x "
                       "JOIN pg_class i ON i.oid=x.indexrelid JOIN pg_class t ON t.oid=x.indrelid "
                       "JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='socialmei' ORDER BY t.relname,i.relname")
        orphan_checks = {}
        for child, field, parent in (("crm_vendas", "cliente_id", "crm_clientes"),
                                      ("crm_vendas", "produto_id", "crm_produtos"),
                                      ("me_conversations", "cliente_id", "crm_clientes"),
                                      ("agenda_appointments", "cliente_id", "crm_clientes"),
                                      ("agenda_appointments", "servico_id", "crm_produtos"),
                                      ("agenda_appointments", "resource_id", "agenda_resources")):
            orphan_checks[child + "." + field] = rows(
                f"SELECT count(*) AS count FROM socialmei.{child} c LEFT JOIN socialmei.{parent} p "
                f"ON p.workspace_id=c.workspace_id AND p.id=c.{field} "
                f"WHERE c.{field} IS NOT NULL AND p.id IS NULL")[0]["count"]
        queues = {}
        for table in ("auth_identity_mail", "auth_recovery_mail", "wa_bot_decisions", "ig_auto_menu_decisions"):
            exists = rows("SELECT to_regclass(%s) IS NOT NULL AS present", ("socialmei." + table,))[0]["present"]
            if exists:
                queues[table] = rows(f"SELECT status,count(*) AS count FROM socialmei.{table} GROUP BY status ORDER BY status")
        return {"mode": "read_only", "identity": identity, "migration_ledger": {
            "count": len(migrations), "versions": [r["version"] for r in migrations],
            "chain_001_040_exact": actual == expected, "checksums_available": False},
            "workspace_count": len(workspaces), "demo_matches": targets,
            "counts_by_workspace": counts, "channels": channels, "roles": roles,
            "table_statistics": stats, "constraints": constraints, "integrity": integrity,
            "activity": activity, "deadlocks": deadlocks, "row_security": rls,
            "objects": objects, "indexes": indexes, "orphan_checks": orphan_checks, "queues": queues,
            "limits": ["Name matching is an inventory hint, not authorization to seed.",
                       "No account, binding, record, sequence or migration was changed.",
                       "No message text, contact identity, email or secret is returned."]}


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    try:
        print(json.dumps(inspect(), default=str, ensure_ascii=True))
    except Exception as error:
        print(json.dumps({"mode": "read_only", "complete": False,
                          "error_type": type(error).__name__}))
        raise SystemExit(1)
