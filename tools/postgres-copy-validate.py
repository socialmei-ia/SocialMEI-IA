#!/usr/bin/env python3
"""Read-only PostgreSQL copy manifests. DSNs are read only from environment.

This verifies a snapshot, not backup freshness or permission to cut over.
Sequences are not MVCC: quiesce all writers before a final comparison.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone


USER_SCHEMA = "n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'"


class LargeObjectsUnsupported(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest_rows(rows):
    """Rows must arrive sorted by their canonical PostgreSQL JSON text."""
    digest = hashlib.sha256()
    count = 0
    for row in rows:
        value = row[0]
        if not isinstance(value, str):
            raise ValueError('Unexpected row representation')
        raw = value.encode('utf-8')
        digest.update(len(raw).to_bytes(8, 'big'))
        digest.update(raw)
        count += 1
    return {'rows': count, 'sha256': digest.hexdigest()}


def private_json(path, value):
    """Create a new private manifest; never replace an existing snapshot."""
    path = Path(path)
    if not path.parent.is_dir():
        raise ValueError('Output directory must already exist')
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def catalog(conn):
    queries = {
        'schemas': f"SELECT n.nspname FROM pg_namespace n WHERE {USER_SCHEMA} ORDER BY 1",
        'relations': f"""SELECT n.nspname,c.relname,c.relkind,c.relpersistence,c.relrowsecurity,
            c.relforcerowsecurity,COALESCE(pg_get_partkeydef(c.oid),''),
            COALESCE(pg_get_expr(c.relpartbound,c.oid),''),c.relispartition
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE {USER_SCHEMA} AND c.relkind IN ('r','p','m','v','f') ORDER BY 1,2""",
        'columns': f"""SELECT n.nspname,c.relname,a.attnum,a.attname,
            format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,
            COALESCE(pg_get_expr(d.adbin,d.adrelid),''),
            COALESCE(cn.nspname || '.' || col.collname,'')
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
            LEFT JOIN pg_collation col ON col.oid=a.attcollation
            LEFT JOIN pg_namespace cn ON cn.oid=col.collnamespace
            WHERE {USER_SCHEMA} AND c.relkind IN ('r','p','m','v','f')
            AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2,3""",
        'constraints': f"""SELECT n.nspname,c.relname,k.conname,k.contype,k.convalidated,
            k.condeferrable,k.condeferred,pg_get_constraintdef(k.oid,true)
            FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE {USER_SCHEMA} ORDER BY 1,2,3""",
        'indexes': f"""SELECT n.nspname,c.relname,i.relname,x.indisvalid,x.indisready,
            x.indisunique,pg_get_indexdef(i.oid)
            FROM pg_index x JOIN pg_class c ON c.oid=x.indrelid
            JOIN pg_class i ON i.oid=x.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE {USER_SCHEMA} ORDER BY 1,2,3""",
        'views': f"""SELECT n.nspname,c.relname,pg_get_viewdef(c.oid,true)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE {USER_SCHEMA} AND c.relkind IN ('v','m') ORDER BY 1,2""",
        'triggers': f"""SELECT n.nspname,c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid,true)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE {USER_SCHEMA} AND NOT t.tgisinternal ORDER BY 1,2,3""",
        'policies': f"""SELECT n.nspname,c.relname,p.polname,p.polcmd,p.polpermissive,
            ARRAY(SELECT rolname FROM pg_roles WHERE oid=ANY(p.polroles) ORDER BY rolname),
            COALESCE(pg_get_expr(p.polqual,p.polrelid),''),
            COALESCE(pg_get_expr(p.polwithcheck,p.polrelid),'')
            FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE {USER_SCHEMA} ORDER BY 1,2,3""",
        'routines': f"""SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),
            p.prokind,p.provolatile,p.prosecdef,pg_get_functiondef(p.oid)
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE {USER_SCHEMA} AND p.prokind IN ('f','p','w') ORDER BY 1,2,3""",
        'enums': f"""SELECT n.nspname,t.typname,e.enumlabel,e.enumsortorder::text
            FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid
            JOIN pg_namespace n ON n.oid=t.typnamespace
            WHERE {USER_SCHEMA} ORDER BY 1,2,e.enumsortorder""",
        'domains': f"""SELECT n.nspname,t.typname,format_type(t.typbasetype,t.typtypmod),
            t.typnotnull,t.typdefault,COALESCE(k.conname,''),COALESCE(pg_get_constraintdef(k.oid,true),'')
            FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
            LEFT JOIN pg_constraint k ON k.contypid=t.oid
            WHERE {USER_SCHEMA} AND t.typtype='d' ORDER BY 1,2,6""",
        'extensions': "SELECT extname,extversion FROM pg_extension ORDER BY 1",
    }
    return {name: [list(row) for row in conn.execute(query).fetchall()]
            for name, query in queries.items()}


def foreign_keys(conn, sql):
    constraints = conn.execute(f"""SELECT n.nspname,c.relname,k.conname,
        pn.nspname,p.relname,k.confmatchtype,
        ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY x(num,pos)
              JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=x.num ORDER BY x.pos),
        ARRAY(SELECT a.attname FROM unnest(k.confkey) WITH ORDINALITY x(num,pos)
              JOIN pg_attribute a ON a.attrelid=p.oid AND a.attnum=x.num ORDER BY x.pos)
        FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_class p ON p.oid=k.confrelid JOIN pg_namespace pn ON pn.oid=p.relnamespace
        WHERE {USER_SCHEMA} AND k.contype='f' AND k.conparentid=0 ORDER BY 1,2,3""").fetchall()
    result = []
    for schema, table, name, pschema, parent, match, children, parents in constraints:
        if match not in ('s', 'f'):
            raise ValueError('Unsupported foreign key match mode')
        present = sql.SQL(' AND ').join(sql.SQL('c.{} IS NOT NULL').format(sql.Identifier(v)) for v in children)
        missing = sql.SQL(' AND ').join(sql.SQL('c.{} IS NULL').format(sql.Identifier(v)) for v in children)
        equality = sql.SQL(' AND ').join(sql.SQL('p.{} = c.{}').format(sql.Identifier(p), sql.Identifier(c))
                                         for c, p in zip(children, parents))
        invalid = sql.SQL('({}) AND NOT EXISTS (SELECT 1 FROM {} p WHERE {})').format(
            present, sql.Identifier(pschema, parent), equality)
        if match == 'f':
            invalid = sql.SQL('((NOT ({})) AND (NOT ({}))) OR ({})').format(present, missing, invalid)
        query = sql.SQL('SELECT count(*) FROM {} c WHERE {}').format(sql.Identifier(schema, table), invalid)
        violations = conn.execute(query).fetchone()[0]
        result.append({'schema': schema, 'table': table, 'constraint': name,
                       'violations': violations,
                       'workspace_key': 'workspace_id' in children})
    return result


def snapshot(dsn):
    import psycopg
    from psycopg import sql

    with psycopg.connect(dsn, connect_timeout=10, application_name='socialmei-copy-validation') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL statement_timeout = '120s'")
        conn.execute("SET LOCAL lock_timeout = '5s'")
        conn.execute("SET LOCAL work_mem = '4MB'")
        conn.execute("SET LOCAL timezone = 'UTC'")
        conn.execute("SET LOCAL datestyle = 'ISO, YMD'")
        conn.execute("SET LOCAL intervalstyle = 'postgres'")
        conn.execute("SET LOCAL extra_float_digits = 3")
        conn.execute("SET LOCAL bytea_output = 'hex'")
        conn.execute('SET LOCAL search_path = pg_catalog')
        conn.execute('SET LOCAL row_security = off')
        large_objects = conn.execute('SELECT count(*) FROM pg_catalog.pg_largeobject_metadata').fetchone()[0]
        if type(large_objects) is not int or large_objects != 0:
            raise LargeObjectsUnsupported('Large objects require a separate validated copy check')
        structure = catalog(conn)
        if any(row[2] == 'f' for row in structure['relations']):
            raise ValueError('Foreign tables require a separate source validation')
        tables = []
        for ordinal, row in enumerate(structure['relations']):
            schema, table, kind = row[:3]
            if kind not in ('r', 'p', 'm'):
                continue
            query = sql.SQL('SELECT value FROM (SELECT row_to_json(t)::text AS value FROM ONLY {} t) x ORDER BY value COLLATE "C"').format(
                sql.Identifier(schema, table))
            with conn.cursor(name='copy_validation_' + str(ordinal)) as cursor:
                cursor.itersize = 500
                cursor.execute(query)
                value = digest_rows(cursor)
            tables.append({'schema': schema, 'table': table, **value})
        sequences = []
        for row in conn.execute(f"""SELECT n.nspname,c.relname,format_type(s.seqtypid,NULL),
            s.seqstart,s.seqincrement,s.seqmax,s.seqmin,s.seqcache,s.seqcycle,
            COALESCE((SELECT format('%I.%I.%I',pn.nspname,pc.relname,a.attname)
              FROM pg_depend d JOIN pg_class pc ON pc.oid=d.refobjid
              JOIN pg_namespace pn ON pn.oid=pc.relnamespace
              JOIN pg_attribute a ON a.attrelid=pc.oid AND a.attnum=d.refobjsubid
              WHERE d.classid='pg_class'::regclass AND d.objid=c.oid
              AND d.refclassid='pg_class'::regclass AND d.deptype IN ('a','i')
              AND d.refobjsubid>0),'')
            FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {USER_SCHEMA} ORDER BY 1,2"""):
            schema, name = row[:2]
            state = conn.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(
                sql.Identifier(schema, name))).fetchone()
            sequences.append({'schema': schema, 'sequence': name, 'definition': list(row[2:]),
                              'last_value': state[0], 'is_called': state[1]})
        fk = foreign_keys(conn, sql)
        ledger = []
        for row in structure['relations']:
            if row[1] == 'schema_migrations' and row[2] in ('r', 'p'):
                versions = conn.execute(sql.SQL('SELECT version FROM {} ORDER BY version').format(
                    sql.Identifier(row[0], row[1]))).fetchall()
                ledger.append({'schema': row[0], 'versions': [value[0] for value in versions]})
        permissions = [list(row) for row in conn.execute(f"""SELECT n.nspname,c.relname,c.relkind,
            has_table_privilege(c.oid,'SELECT'),has_table_privilege(c.oid,'INSERT'),
            has_table_privilege(c.oid,'UPDATE'),has_table_privilege(c.oid,'DELETE')
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE {USER_SCHEMA} AND c.relkind IN ('r','p') ORDER BY 1,2""")]
        sequence_permissions = [list(row) for row in conn.execute(f"""SELECT n.nspname,c.relname,
            has_sequence_privilege(c.oid,'SELECT'),has_sequence_privilege(c.oid,'USAGE'),
            has_sequence_privilege(c.oid,'UPDATE')
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE {USER_SCHEMA} AND c.relkind='S' ORDER BY 1,2""")]
        identity = conn.execute("""SELECT current_setting('server_version_num')::integer,
            current_setting('transaction_read_only'),current_setting('transaction_isolation')""").fetchone()
        conn.rollback()
    return {'manifest_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'snapshot': {'server_version_num': identity[0], 'read_only': identity[1],
                         'isolation': identity[2], 'row_security': 'off',
                         'sequence_comparison_requires_quiescent_writers': True},
            'structure': structure, 'tables': tables, 'sequences': sequences, 'migration_ledger': ledger,
            'large_objects': large_objects,
            'foreign_keys': fk, 'effective_permissions': permissions,
            'effective_sequence_permissions': sequence_permissions,
            'valid': not any(row['violations'] for row in fk)}


def compare(source, target):
    if source.get('manifest_version') != 1 or target.get('manifest_version') != 1:
        raise ValueError('Unsupported manifest version')
    for manifest in (source, target):
        if (type(manifest.get('large_objects')) is not int or manifest['large_objects'] != 0
                or not isinstance(manifest.get('structure'), dict)
                or any(not isinstance(manifest.get(key), list) for key in
                       ('tables', 'sequences', 'foreign_keys', 'migration_ledger', 'effective_permissions'))):
            raise ValueError('Incomplete snapshot manifest')
    differing = [key for key in ('structure', 'tables', 'sequences', 'foreign_keys', 'migration_ledger')
                 if source.get(key) != target.get(key)]
    return {'equal': not differing and source.get('valid') is True and target.get('valid') is True,
            'different_sections': differing,
            'source_valid': source.get('valid') is True, 'target_valid': target.get('valid') is True,
            'effective_permissions_equal': source.get('effective_permissions') == target.get('effective_permissions'),
            'effective_sequence_permissions_equal': source.get('effective_sequence_permissions') == target.get('effective_sequence_permissions'),
            'freshness_verified': False, 'cutover_authorized': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New private manifest/report path')
    parser.add_argument('--compare', action='store_true', help='Read SOURCE_DATABASE_URL and TARGET_DATABASE_URL')
    args = parser.parse_args(argv)
    try:
        if args.compare:
            source = snapshot(os.environ['SOURCE_DATABASE_URL'])
            target = snapshot(os.environ['TARGET_DATABASE_URL'])
            result = compare(source, target)
            private_json(args.output, {'source': source, 'target': target, 'comparison': result})
            print(canonical(result))
            return 0 if result['equal'] else 2
        result = snapshot(os.environ['DATABASE_URL'])
        private_json(args.output, result)
        print(canonical({'snapshot_written': True, 'valid': result['valid'],
                         'tables': len(result['tables']), 'cutover_authorized': False}))
        return 0 if result['valid'] else 2
    except LargeObjectsUnsupported:
        print('Validation blocked: PostgreSQL large objects require a separate validated copy check.', file=sys.stderr)
        return 1
    except Exception:
        print('Validation unavailable; inspect private configuration, permissions and source access.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
