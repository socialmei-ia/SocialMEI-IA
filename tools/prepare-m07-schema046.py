"""Freeze the exact 041-to-046 PostgreSQL transaction for operator review."""
import argparse
import hashlib
import json
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[1]
EXPECTED_DATABASE = 'socialmei_candidate040_20261114'


def build(database):
    files = sorted((REPO/'database/migrations').glob('*.sql'))[:46]
    names = [p.name for p in files]
    if ([name[:3] for name in names] != [f'{i:03d}' for i in range(1,47)]
        or not all(re.fullmatch(r'\d{3}_[a-z0-9_]+\.sql', n) for n in names)
        or not re.fullmatch(r'[a-z][a-z0-9_]{1,62}', database)):
        raise ValueError('Unexpected migration chain or database identity')
    approved_previous = ','.join("'" + name + "'" for name in names[:41])
    sql = f"""BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='55s';
SELECT pg_advisory_xact_lock(72426001);
DO $release$
BEGIN
    IF current_database() <> '{database}' OR pg_is_in_recovery()
       OR current_setting('server_version_num')::int NOT BETWEEN 170000 AND 179999 THEN
        RAISE EXCEPTION 'Unexpected database for the 046 release';
    END IF;
    IF (SELECT array_agg(version ORDER BY version) FROM socialmei.schema_migrations)
       IS DISTINCT FROM ARRAY[{approved_previous}]::text[] THEN
        RAISE EXCEPTION 'Unexpected starting ledger';
    END IF;
END
$release$;
"""
    hashes = {}
    for path in files[41:]:
        raw = path.read_bytes()
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
        sql += raw.decode('utf-8') + "\nINSERT INTO socialmei.schema_migrations(version) VALUES ('" + path.name + "');\n"
    sql += """
DO $gate$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM unnest(ARRAY['socialmei.me_inbox_preferences','socialmei.me_inbox_hidden']) AS t(relation)
        CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE']) AS a(privilege)
        WHERE NOT has_table_privilege('socialmei_candidate040',t.relation,a.privilege)
    ) THEN
        RAISE EXCEPTION 'The application role is missing required inbox grants';
    END IF;
END
$gate$;
COMMIT;
"""
    return sql.encode(), hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--isolated-database', help='Database name for disposable rehearsal only')
    args = parser.parse_args()
    db = args.isolated_database or EXPECTED_DATABASE
    sql, hashes = build(db)
    with args.output.open('xb') as out:
        out.write(sql)
    print(json.dumps({'sql_sha256': hashlib.sha256(sql).hexdigest(),
                      'migrations': hashes, 'database': db, 'executed': False}))


if __name__ == '__main__':
    main()
