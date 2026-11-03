"""Strict restore metadata comparison; only two reviewed PostgreSQL rewrites canonicalized."""
import copy
import re

_NESTED = 'CHECK ((((octet_length(text) >= 1) AND (octet_length(text) <= 1000)) AND (length(btrim(text)) > 0)))'
_FLAT = 'CHECK (((octet_length(text) >= 1) AND (octet_length(text) <= 1000) AND (length(btrim(text)) > 0)))'
_LITERAL = r"'(?:[^']|'')*'::character varying"
_ARRAY = re.compile(r'\(ARRAY\[(?P<items>'+_LITERAL+r'(?:,\s*'+_LITERAL+r')*)\]\)::text\[\]')

def canonical_expression(value):
    if value == _NESTED:
        return _FLAT
    if not isinstance(value, str):
        return value
    output=[];i=0
    while i<len(value):
        # Never rewrite SQL code embedded inside a quoted text literal.
        if value[i]=="'":
            start=i;i+=1
            while i<len(value):
                if value[i]=="'":
                    i+=1
                    if i<len(value) and value[i]=="'":i+=1;continue
                    break
                i+=1
            output.append(value[start:i]);continue
        match=_ARRAY.match(value,i)
        if match:
            items=re.sub(_LITERAL,lambda m:'('+m.group(0)+')::text',match.group('items'))
            output.append('ARRAY['+items+']');i=match.end();continue
        output.append(value[i]);i+=1
    return ''.join(output)

def canonical_schema(value):
    result=copy.deepcopy(value)
    for row in result.get('constraints') or []:
        row['definition']=canonical_expression(row['definition'])
    for row in result.get('indexes') or []:
        for key in ('definition','expression','predicate'):
            if key in row:row[key]=canonical_expression(row[key])
    # Catalog order can depend on database locale. Object identity and every property remain checked.
    keys={'columns':('table_name','column_name'),'constraints':('relname','conname'),
          'indexes':('table_name','index_name'),'tables':('table_name',),'sequences':('name',),
          'schemas':('name',),'triggers':('table_name','name'),'policies':('table_name','name'),
          'functions':('name','arguments'),'views':('name',)}
    for group,fields in keys.items():
        rows=result.get(group)
        if rows is not None:
            identities=[tuple(row[f] for f in fields) for row in rows]
            if len(set(identities))!=len(identities):raise ValueError('duplicate_schema_object')
            result[group]=sorted(rows,key=lambda r:tuple(r[f] for f in fields))
    return result

def compare(source,restored):
    return canonical_schema(source)==canonical_schema(restored)


METADATA_GROUPS = ['columns', 'constraint_properties', 'constraints', 'environment', 'functions', 'indexes', 'schemas', 'sequences', 'tables', 'triggers', 'views']
SCHEMA_QUERY = "SELECT a.doc::jsonb || b.doc::jsonb FROM (SELECT json_build_object(\n 'columns',(SELECT json_agg(row_to_json(x)) FROM(SELECT table_name,column_name,ordinal_position,data_type,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='socialmei' ORDER BY table_name,ordinal_position)x),\n 'constraints',(SELECT json_agg(row_to_json(x)) FROM(SELECT r.relname,c.conname,c.contype,pg_catalog.pg_get_constraintdef(c.oid) AS definition FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class r ON r.oid=c.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='socialmei' ORDER BY r.relname,c.conname)x))) a(doc) CROSS JOIN (SELECT json_build_object(\n 'environment',(SELECT row_to_json(x) FROM (SELECT current_setting('server_version_num') AS version,pg_encoding_to_char(encoding) AS encoding,datcollate,datctype,datlocprovider,daticulocale FROM pg_database WHERE datname=current_database())x),\n 'tables',(SELECT json_agg(row_to_json(x)) FROM (SELECT c.relname AS table_name,c.relkind,c.relpersistence,c.relrowsecurity,c.relforcerowsecurity,c.relreplident,c.reloptions,pg_get_userbyid(c.relowner) AS owner,c.relacl FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='socialmei' AND c.relkind IN ('r','p') ORDER BY c.relname)x),\n 'indexes',(SELECT json_agg(row_to_json(x)) FROM (SELECT t.relname AS table_name,i.relname AS index_name,pg_get_indexdef(i.oid) AS definition,ix.indisunique,ix.indisprimary,ix.indisvalid,ix.indisready,ix.indisreplident,pg_get_expr(ix.indexprs,ix.indrelid) AS expression,pg_get_expr(ix.indpred,ix.indrelid) AS predicate FROM pg_index ix JOIN pg_class i ON i.oid=ix.indexrelid JOIN pg_class t ON t.oid=ix.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='socialmei' ORDER BY t.relname,i.relname)x),\n 'constraint_properties',(SELECT json_agg(row_to_json(x)) FROM (SELECT r.relname,c.conname,c.condeferrable,c.condeferred,c.convalidated,c.conislocal,c.connoinherit,c.confupdtype,c.confdeltype,c.confmatchtype,c.conkey,c.confkey FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='socialmei' ORDER BY r.relname,c.conname)x),\n 'triggers',(SELECT json_agg(row_to_json(x)) FROM (SELECT r.relname AS table_name,t.tgname AS name,t.tgenabled,pg_get_triggerdef(t.oid) AS definition FROM pg_trigger t JOIN pg_class r ON r.oid=t.tgrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='socialmei' AND NOT t.tgisinternal ORDER BY r.relname,t.tgname)x),\n 'functions',(SELECT json_agg(row_to_json(x)) FROM (SELECT p.proname AS name,pg_get_function_identity_arguments(p.oid) AS arguments,pg_get_functiondef(p.oid) AS definition,pg_get_userbyid(p.proowner) AS owner,p.proacl FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='socialmei' AND p.prokind IN ('f','p') ORDER BY p.proname,pg_get_function_identity_arguments(p.oid))x),\n 'schemas',(SELECT json_agg(row_to_json(x)) FROM (SELECT nspname AS name,pg_get_userbyid(nspowner) AS owner,nspacl FROM pg_namespace WHERE nspname='socialmei')x),\n 'views',(SELECT json_agg(row_to_json(x)) FROM (SELECT c.relname AS name,pg_get_viewdef(c.oid) AS definition,c.reloptions FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='socialmei' AND c.relkind IN ('v','m') ORDER BY c.relname)x),\n 'sequences',(SELECT json_agg(row_to_json(x)) FROM (SELECT c.relname AS name,format_type(s.seqtypid,NULL) AS type,s.seqstart,s.seqincrement,s.seqmax,s.seqmin,s.seqcache,s.seqcycle FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='socialmei' ORDER BY c.relname)x)\n)) b(doc);"
