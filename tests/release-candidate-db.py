#!/usr/bin/env python3
"""Opt-in PostgreSQL 16 rehearsal; exclusively owns its disposable Docker resources.

python tests/release-candidate-db.py --run --output /tmp/rc80-evidence --backend-tests
Requires Linux Docker's local socket and installed python-service requirements.
No database URL, remote Docker endpoint, existing container, or deployment is accepted.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'postgres:16-alpine'
LABEL = 'socialmei.release-candidate-rehearsal'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, default=str)


class Rehearsal:
    def __init__(self, output):
        self.output = output
        self.token = uuid4().hex
        self.name = 'socialmei-rc80-' + self.token[:12]
        self.password = secrets.token_hex(24)
        self.container = self.network = None
        self.volumes = []
        self.dsn = None
        self.env = dict(os.environ)
        for name in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
            self.env.pop(name, None)
        self.report = {'schema_version': 1, 'image': IMAGE, 'checks': [], 'cleanup': False,
                       'limitations': ['Team migration ledger stores version/applied_at only; it has no stored checksum or automatic drift rejection.',
                                       'Disabled-feature compatibility preserves tables/data; old application images are not executed and no destructive down migration is run.',
                                       'A synthetic rehearsal is not a production backup, deploy, migration or rollback authorization.']}

    def clean_text(self, value):
        value = str(value).replace(self.password, '[redacted]')
        if self.dsn:
            value = value.replace(self.dsn, '[owned-disposable-database]')
        return value

    def docker(self, *args, check=True, binary=False):
        result = subprocess.run(['docker', '--host=unix:///var/run/docker.sock', *args],
                                env=self.env, capture_output=True, text=not binary, timeout=180)
        if check and result.returncode:
            raise RuntimeError('Local Docker operation failed: ' + self.clean_text(result.stderr)[-1500:])
        return result

    def check(self, condition, name):
        if not condition:
            raise AssertionError(name)
        self.report['checks'].append(name)
        print('PASS:', name, flush=True)

    def start(self):
        self.docker('info', '--format', '{{.ServerVersion}}')
        self.network = self.docker('network', 'create', '--internal', '--label', LABEL+'='+self.token, self.name).stdout.strip()
        self.container = self.docker('run', '-d', '--name', self.name, '--network', self.network,
                                     '--label', LABEL+'='+self.token, '-e', 'POSTGRES_USER=rc80',
                                     '-e', 'POSTGRES_PASSWORD='+self.password, '-e', 'POSTGRES_DB=rc80_upgrade', IMAGE).stdout.strip()
        for _ in range(120):
            # The entrypoint's temporary init server accepts Unix sockets before TCP.
            ready = self.docker('exec', self.container, 'pg_isready', '-h', '127.0.0.1', '-U', 'rc80', '-d', 'rc80_upgrade', check=False)
            if ready.returncode == 0:
                break
            time.sleep(.25)
        else:
            raise RuntimeError('Owned PostgreSQL did not become ready')
        details = json.loads(self.docker('inspect', self.container).stdout)[0]
        self.check(details['Config']['Labels'].get(LABEL) == self.token and not details['HostConfig'].get('PortBindings'), 'own isolated PostgreSQL container; no published ports')
        self.volumes = [mount['Name'] for mount in details['Mounts'] if mount['Type'] == 'volume']
        ip = next(iter(details['NetworkSettings']['Networks'].values()))['IPAddress']
        self.dsn = f'postgresql://rc80:{self.password}@{ip}:5432/rc80_upgrade'

    def connect(self, database='rc80_upgrade', **kwargs):
        import psycopg
        # Only this internally generated DSN is used; inherited URL variables are ignored.
        return psycopg.connect(self.dsn.rsplit('/', 1)[0]+'/'+database, connect_timeout=10, **kwargs)

    def migrate(self, folder, stage, database='rc80_upgrade'):
        spec = importlib.util.spec_from_file_location('rc80_team_migrate', ROOT/'tools/team_migrate.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.connect = lambda: self.connect(database)
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            module.migrate(folder)
        with (self.output/'migrations.log').open('a') as target:
            target.write(stage+'\n'+log.getvalue())

    def canonical_expression(self, conn, table, expression, null_passes=True):
        from psycopg import sql
        # CHECK accepts NULL; a partial index includes only TRUE. Preserve both semantics.
        truth = 'NOT FALSE' if null_passes else 'TRUE'
        query = sql.SQL('EXPLAIN (FORMAT JSON, COSTS OFF) SELECT 1 FROM {} WHERE ({}) IS '+truth).format(sql.Identifier('socialmei', table), sql.SQL(expression))
        plan = conn.execute(query).fetchone()[0][0]['Plan']
        expressions = []
        def collect(node):
            for key in ('Filter', 'One-Time Filter'):
                if key in node:
                    expressions.append(node[key])
            for child in node.get('Plans', []):
                collect(child)
        collect(plan)
        if len(expressions) > 1:
            raise AssertionError('Unexpected compound expression plan')
        return expressions[0] if expressions else 'true'

    def snapshot(self, database='rc80_upgrade'):
        from psycopg import sql
        with self.connect(database) as conn:
            conn.execute('SET LOCAL enable_indexscan=off; SET LOCAL enable_indexonlyscan=off; SET LOCAL enable_bitmapscan=off; SET LOCAL max_parallel_workers_per_gather=0; SET LOCAL constraint_exclusion=off')
            names = [row[0] for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='socialmei' ORDER BY tablename")]
            tables = {}
            for name in names:
                rows = [row[0] for row in conn.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t').format(sql.Identifier('socialmei', name)))]
                tables[name] = sorted(rows, key=canonical)
            indexes = []
            for table, name, definition, predicate in conn.execute("SELECT t.relname,c.relname,pg_get_indexdef(i.indexrelid),pg_get_expr(i.indpred,i.indrelid) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='socialmei' ORDER BY t.relname,c.relname").fetchall():
                if predicate is not None:
                    head, delimiter, _ = definition.partition(' WHERE ')
                    if not delimiter:
                        raise AssertionError('Missing deparsed index predicate')
                    definition = (head, self.canonical_expression(conn, table, predicate, null_passes=False))
                indexes.append((table, name, definition))
            constraints = []
            for table, name, kind, validated, definition, expression in conn.execute("SELECT c.relname,k.conname,k.contype,k.convalidated,pg_get_constraintdef(k.oid),pg_get_expr(k.conbin,k.conrelid) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='socialmei' ORDER BY c.relname,k.conname").fetchall():
                if kind == 'c':
                    definition = self.canonical_expression(conn, table, expression)
                constraints.append((table, name, kind, validated, definition))
            columns = conn.execute("SELECT table_name,column_name,ordinal_position,data_type,is_nullable,column_default,character_maximum_length FROM information_schema.columns WHERE table_schema='socialmei' ORDER BY table_name,ordinal_position").fetchall()
            sequences = {}
            for (name,) in conn.execute("SELECT sequencename FROM pg_sequences WHERE schemaname='socialmei' ORDER BY sequencename"):
                sequences[name] = conn.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(sql.Identifier('socialmei', name))).fetchone()
            definitions = conn.execute("SELECT sequencename,data_type,start_value,min_value,max_value,increment_by,cycle,cache_size FROM pg_sequences WHERE schemaname='socialmei' ORDER BY sequencename").fetchall()
        return {'tables': tables, 'indexes': indexes, 'constraints': constraints,
                'columns': columns, 'sequences': sequences, 'sequence_definitions': definitions}

    def seed_initial(self):
        with self.connect() as conn:
            customer = conn.execute("INSERT INTO socialmei.clientes(nome,identificador_externo) VALUES('RC80 legado fictício','rc80:legacy') RETURNING id").fetchone()[0]
            conversation = conn.execute("INSERT INTO socialmei.conversas(cliente_id,canal,identificador_externo) VALUES(%s,'whatsapp','rc80:legacy-chat') RETURNING id", (customer,)).fetchone()[0]
            conn.execute("INSERT INTO socialmei.mensagens(conversa_id,identificador_externo,conteudo,metadados) VALUES(%s,'rc80:legacy-message','Histórico sintético preservado', '{\"synthetic\":true}')", (conversation,))

    def seed_workspaces(self):
        tenants = []
        with self.connect() as conn:
            for index in (1, 2):
                workspace = conn.execute('INSERT INTO socialmei.workspaces(slug,nome) VALUES(%s,%s) RETURNING id', ('rc80-'+str(index), 'RC80 sintético '+str(index))).fetchone()[0]
                user = conn.execute('INSERT INTO socialmei.users(email,nome) VALUES(%s,%s) RETURNING id', (f'rc80-{index}@example.test', 'Usuário fictício')).fetchone()[0]
                conn.execute("INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'owner')", (workspace, user))
                customer = conn.execute("INSERT INTO socialmei.crm_clientes(workspace_id,nome,tags) VALUES(%s,'Mesmo nome sintético','[\"rc80\"]') RETURNING id", (workspace,)).fetchone()[0]
                channel = conn.execute("INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao) VALUES(%s,%s,'synthetic') RETURNING id", (workspace, 'rc80-'+str(index))).fetchone()[0]
                conversation = conn.execute("INSERT INTO socialmei.crm_conversas_canal(workspace_id,canal_id,identificador_externo,cliente_id,nome) VALUES(%s,%s,'synthetic:contact',%s,'Mesmo nome sintético') RETURNING id", (workspace, channel, customer)).fetchone()[0]
                conn.execute("INSERT INTO socialmei.crm_mensagens_canal(workspace_id,canal_id,conversa_id,identificador_externo,direcao,conteudo,status) VALUES(%s,%s,%s,'synthetic:message','entrada','Atendimento sintético preservado','recebida')", (workspace, channel, conversation))
                session_hash = digest(f'synthetic-session:{workspace}'.encode())
                conn.execute("INSERT INTO socialmei.auth_sessoes(token_hash,user_id,workspace_id,expira_em) VALUES(%s,%s,%s,NOW()+INTERVAL '1 day')", (session_hash,user,workspace))
                tenants.append({'workspace': workspace, 'user': user, 'session_hash': session_hash})
        return tenants

    def seed_incremental(self, version, tenants):
        from psycopg.types.json import Jsonb
        from workspace_profile import BusinessProfile, Capabilities, default_preferences
        with self.connect() as conn:
            for index, tenant in enumerate(tenants):
                workspace, user = tenant['workspace'], tenant['user']
                if version == 12:
                    account = uuid4()
                    conn.execute("INSERT INTO socialmei.instagram_sim_accounts(workspace_id,id,label,created_by) VALUES(%s,%s,'Conta fictícia',%s)", (workspace, account, user))
                    conn.execute("INSERT INTO socialmei.instagram_sim_publications(workspace_id,id,account_id,requested_by,idempotency_key,fingerprint,format,caption,media_manifest) VALUES(%s,%s,%s,%s,%s,%s,'feed','Simulação sem envio',%s)", (workspace, uuid4(), account, user, uuid4(), 'a'*64, Jsonb([{'name':'synthetic.png','mime':'image/png','size':32}])))
                elif version == 13:
                    profile = BusinessProfile.model_validate({'version':1,'businessName':'RC80','segment':'barber','activity':'Teste','offers':['services'],'services':['Corte fictício'],'productCategories':[],'capabilities':{name:name=='appointments' for name in Capabilities.model_fields},'modules':['clients','services','appointments'],'ignoredSuggestions':[],'completed':True}).normalized('RC80 sintético '+str(index+1))
                    conn.execute('INSERT INTO socialmei.workspace_profiles(workspace_id,profile) VALUES(%s,%s)', (workspace, Jsonb(profile)))
                    conn.execute('INSERT INTO socialmei.auth_preferences(workspace_id,user_id,preferences) VALUES(%s,%s,%s)', (workspace, user, Jsonb(default_preferences())))
                elif version == 14:
                    conversation = conn.execute("INSERT INTO socialmei.me_conversations(workspace_id,channel,account_ref,contact_ref,contact_name,revision) VALUES(%s,'whatsapp','synthetic:account','synthetic:contact','Mesmo nome sintético',1) RETURNING id", (workspace,)).fetchone()[0]
                    message = conn.execute("INSERT INTO socialmei.me_messages(workspace_id,conversation_id,external_message_id,fingerprint,conversation_revision,text,revision) VALUES(%s,%s,'synthetic:message',%s,1,'Preço fictício',2) RETURNING id", (workspace, conversation, 'b'*64)).fetchone()[0]
                    conn.execute("INSERT INTO socialmei.me_external_messages(workspace_id,channel,account_ref,external_message_id,message_id) VALUES(%s,'whatsapp','synthetic:account','synthetic:message',%s)", (workspace, message))
                    document = conn.execute("INSERT INTO socialmei.me_documents(workspace_id,title,content) VALUES(%s,'Fonte sintética','Preço exclusivamente fictício') RETURNING id", (workspace,)).fetchone()[0]
                    job = uuid4()
                    result = {'sentiment':'neutral','confidence':'low','explanation':'Stub sintético','suggested_reply':'Rascunho não enviado','citations':[{'id':document,'title':'Fonte sintética','revision':1}]}
                    conn.execute("INSERT INTO socialmei.me_jobs(id,workspace_id,message_id,message_revision,revision,status,result) VALUES(%s,%s,%s,2,2,'pending_review',%s)", (job, workspace, message, Jsonb(result)))
                    conn.execute('INSERT INTO socialmei.me_citations(workspace_id,job_id,document_id,document_revision) VALUES(%s,%s,%s,1)', (workspace, job, document))
                    conn.execute("INSERT INTO socialmei.me_operations(workspace_id,kind,operation_id,fingerprint,response) VALUES(%s,'enrich',%s,%s,%s)", (workspace, uuid4(), 'c'*64, Jsonb({'id':str(job),'message_id':message})))
                    conn.execute('INSERT INTO socialmei.me_events(event_id,job_id,attempt,fingerprint) VALUES(%s,%s,1,%s)', (uuid4(), job, 'd'*64))
                    conn.execute('INSERT INTO socialmei.me_limits(workspace_id,count) VALUES(%s,1)', (workspace,))

                elif version == 15:
                    account = conn.execute('SELECT id FROM socialmei.instagram_sim_accounts WHERE workspace_id=%s LIMIT 1',(workspace,)).fetchone()[0]
                    job = uuid4()
                    conn.execute("INSERT INTO socialmei.content_preparation_jobs(workspace_id,id,account_id,requested_by,idempotency_key,fingerprint,title,format,caption,media_manifest,status,scheduled_for,run_after) VALUES(%s,%s,%s,%s,%s,%s,'Ensaio fictício','feed','Sem publicação',%s,'scheduled',now()+interval '1 day',now()+interval '1 day')",(workspace,job,account,user,uuid4(),'c'*64,Jsonb([{'name':'fixture.png','mime':'image/png','size':32}])))
                    conn.execute("INSERT INTO socialmei.content_preparation_events(workspace_id,job_id,status) VALUES(%s,%s,'scheduled')",(workspace,job))

                elif version == 16:
                    client = conn.execute('SELECT id FROM socialmei.crm_clientes WHERE workspace_id=%s LIMIT 1', (workspace,)).fetchone()[0]
                    opportunity = uuid4()
                    conn.execute("INSERT INTO socialmei.crm_opportunities(workspace_id,id,client_id,title,interest_level,created_by) VALUES(%s,%s,%s,'Negociação fictícia','hot',%s)", (workspace, opportunity, client, user))
                    snapshot = {'id': str(opportunity), 'workspace_id': workspace, 'revision': 1}
                    conn.execute("INSERT INTO socialmei.crm_opportunity_events(workspace_id,opportunity_id,actor_id,action,current) VALUES(%s,%s,%s,'create',%s)", (workspace, opportunity, user, Jsonb(snapshot)))
                    conn.execute('INSERT INTO socialmei.crm_opportunity_operations(workspace_id,operation_id,fingerprint,response) VALUES(%s,%s,%s,%s)', (workspace, uuid4(), 'e'*64, Jsonb(snapshot)))
                elif version == 17:
                    preparation = {'username': 'loja.ficticia', 'account_type': 'business', 'meta_app_status': 'unknown', 'test_participants': ['equipe.teste'], 'reply_mode': 'review'}
                    conn.execute('INSERT INTO socialmei.integration_setup(workspace_id,instagram,updated_by) VALUES(%s,%s,%s)', (workspace, Jsonb(preparation), user))
                elif version == 18:
                    account = conn.execute('SELECT id FROM socialmei.instagram_sim_accounts WHERE workspace_id=%s LIMIT 1', (workspace,)).fetchone()[0]
                    state_hash = digest(f'synthetic-state:{workspace}'.encode())
                    conn.execute("INSERT INTO socialmei.ig_lab_states(state_hash,workspace_id,user_id,session_hash,expires_at) VALUES(%s,%s,%s,%s,NOW()+INTERVAL '5 minutes')", (state_hash, workspace, user, 'f'*64))
                    conn.execute("INSERT INTO socialmei.ig_lab_connections(workspace_id,account_id,status,expires_at) VALUES(%s,%s,'connected',NOW()+INTERVAL '1 hour')", (workspace, account))
                    conn.execute('INSERT INTO socialmei.ig_lab_events(workspace_id,event_id,fingerprint,result) VALUES(%s,%s,%s,%s)', (workspace, uuid4(), 'a'*64, Jsonb({'fictional':True,'transport':'none'})))
                    conn.execute("INSERT INTO socialmei.ig_lab_publications(workspace_id,id,account_id,idempotency_key,fingerprint,payload,approved_by,status,attempts,provider_result) VALUES(%s,%s,%s,%s,%s,%s,%s,'simulated-published',1,%s)", (workspace, uuid4(), account, uuid4(), 'b'*64, Jsonb({'caption':'Somente fixture','format':'feed','media':[{'name':'fixture.png','mime':'image/png','size':32}]}), user, Jsonb({'fictional':True,'published':False})))
                elif version == 19:
                    from instagram_token_vault import TokenBinding, TokenVault
                    connection = uuid4()
                    external = str(900000 + index)
                    encrypted = TokenVault(keys={'rehearsal': b'r'*32}, active_key_id='rehearsal').seal('synthetic-rehearsal-token', TokenBinding(workspace,connection,external))
                    conn.execute("INSERT INTO socialmei.ig_meta_connections(id,workspace_id,external_account_id,account_type,status,scopes,encrypted_token,token_kind,issued_at,expires_at,created_by) VALUES(%s,%s,%s,'BUSINESS','connected',%s,%s,'long',NOW(),NOW()+INTERVAL '1 day',%s)", (connection,workspace,external,['instagram_business_basic'],encrypted,user))
                    conn.execute("INSERT INTO socialmei.ig_meta_oauth_states(state_hash,workspace_id,user_id,session_hash,callback_uri,scopes,expires_at) VALUES(%s,%s,%s,%s,'https://synthetic.invalid/callback',%s,NOW()+INTERVAL '5 minutes')", (digest(f'synthetic-meta-state:{workspace}'.encode()),workspace,user,tenant['session_hash'],['instagram_business_basic']))
                    conn.execute("INSERT INTO socialmei.ig_meta_audit(workspace_id,user_id,connection_id,action) VALUES(%s,%s,%s,'connected')", (workspace,user,connection))
                elif version == 20:
                    connection, external = conn.execute('SELECT id,external_account_id FROM socialmei.ig_meta_connections WHERE workspace_id=%s', (workspace,)).fetchone()
                    account_ref, contact_ref = 'instagram:'+external, 'instagram:'+str(700000+index)
                    conversation = conn.execute("INSERT INTO socialmei.me_conversations(workspace_id,channel,account_ref,contact_ref,contact_name,origin,revision) VALUES(%s,'instagram',%s,%s,'Contato de teste','instagram',1) RETURNING id", (workspace,account_ref,contact_ref)).fetchone()[0]
                    external_message = 'rehearsal-mid-'+external+'x'*140
                    message = conn.execute("INSERT INTO socialmei.me_messages(workspace_id,conversation_id,external_message_id,fingerprint,conversation_revision,text,origin) VALUES(%s,%s,%s,%s,1,'Mensagem isolada de ensaio','instagram') RETURNING id", (workspace,conversation,external_message,'d'*64)).fetchone()[0]
                    conn.execute("INSERT INTO socialmei.me_external_messages(workspace_id,channel,account_ref,external_message_id,message_id,origin) VALUES(%s,'instagram',%s,%s,%s,'instagram')", (workspace,account_ref,external_message,message))
                    conn.execute("INSERT INTO socialmei.ig_meta_ingress_events(external_account_id,event_key,workspace_id,connection_id,kind,fingerprint,status,message_id) VALUES(%s,%s,%s,%s,'message',%s,'processed',%s)", (external,digest(external_message.encode()),workspace,connection,'d'*64,message))

    def prove_fks(self, tenants, database):
        import psycopg
        with self.connect(database) as conn:
            first, second = [tenant['workspace'] for tenant in tenants]
            foreign_doc = conn.execute('SELECT id FROM socialmei.me_documents WHERE workspace_id=%s', (second,)).fetchone()[0]
            try:
                with conn.transaction():
                    conn.execute('UPDATE socialmei.me_citations SET document_id=%s WHERE workspace_id=%s', (foreign_doc, first))
            except psycopg.errors.ForeignKeyViolation:
                pass
            else:
                raise AssertionError('Cross-workspace RAG FK accepted invalid data')
            for table in ('ig_lab_connections', 'ig_lab_publications'):
                from psycopg import sql
                try:
                    with conn.transaction():
                        foreign_account = uuid4()
                        conn.execute("INSERT INTO socialmei.instagram_sim_accounts(workspace_id,id,label,created_by) VALUES(%s,%s,'Probe fictício',%s)", (second, foreign_account, tenants[1]['user']))
                        conn.execute(sql.SQL('UPDATE socialmei.{} SET account_id=%s WHERE workspace_id=%s').format(sql.Identifier(table)), (foreign_account, first))
                except psycopg.errors.ForeignKeyViolation:
                    pass
                else:
                    raise AssertionError('Cross-workspace fake provider FK accepted invalid data: '+table)
            self.check(True, database+': fake provider connection/publication cross-workspace FKs reject invalid data')
            foreign_connection = conn.execute('SELECT id FROM socialmei.ig_meta_connections WHERE workspace_id=%s', (second,)).fetchone()[0]
            foreign_message = conn.execute("SELECT id FROM socialmei.me_messages WHERE workspace_id=%s AND origin='instagram'", (second,)).fetchone()[0]
            synthetic_message = conn.execute("SELECT id FROM socialmei.me_messages WHERE workspace_id=%s AND origin='synthetic'", (first,)).fetchone()[0]
            for column, value in (('connection_id',foreign_connection), ('message_id',foreign_message), ('message_id',synthetic_message)):
                try:
                    with conn.transaction():
                        conn.execute(sql.SQL('UPDATE socialmei.ig_meta_ingress_events SET {}=%s WHERE workspace_id=%s').format(sql.Identifier(column)), (value,first))
                except psycopg.errors.ForeignKeyViolation:
                    pass
                else:
                    raise AssertionError('Instagram ingress FK accepted a foreign tenant or synthetic message')
            self.check(True, database+': Instagram ingress composite FKs reject foreign connections/messages and synthetic origin')
            self.check(conn.execute("SELECT COUNT(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='socialmei' AND c.contype='f' AND NOT c.convalidated").fetchone()[0] == 0, database+': all foreign keys validated and cross-workspace RAG link rejected')

    def defaults(self, tenants):
        from unittest.mock import patch
        safe = {'SOCIALMEI_AUTH_ENABLED':'true','SOCIALMEI_SHARED_DATA_ENABLED':'true',
                'SOCIALMEI_AUTH_ORIGIN':'https://rc80.example.test','SOCIALMEI_CORS_ORIGINS':''}
        with patch.dict(os.environ, safe):
            os.environ.pop('SOCIALMEI_INSTAGRAM_MODE', None)
            os.environ.pop('SOCIALMEI_MESSAGE_ENRICHMENT_MODE', None)
            os.environ.pop('SOCIALMEI_CONTENT_PREPARATION_MODE', None)
            os.environ.pop('SOCIALMEI_CHANNEL_INGRESS_MODE', None)
            os.environ.pop('SOCIALMEI_INSTAGRAM_PROVIDER', None)
            os.environ.pop('SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT', None)
            from app import app
            from fastapi.testclient import TestClient
            import settings
            identity = {'id':tenants[0]['user'],'workspace_id':tenants[0]['workspace'],'role':'owner','administrador_plataforma':False}
            with patch('account_auth.session_identity', return_value=identity), patch('instagram_simulation.connect', side_effect=AssertionError('unexpected database')), patch('message_enrichment.connect', side_effect=AssertionError('unexpected database')), patch('content_preparation.connect', side_effect=AssertionError('unexpected database')):
                client = TestClient(app, base_url=safe['SOCIALMEI_AUTH_ORIGIN'])
                client.cookies.set('__Host-socialmei-session', 'a'*64)
                self.check(not settings.instagram_provider_lab_enabled() and client.get('/api/v1/instagram/provider-lab/status').status_code == 503, 'fake Instagram provider default disabled')
                self.check(client.get('/api/v1/instagram/simulation/accounts').status_code == 503, 'Instagram default disabled without database access')
                self.check(client.get('/api/v1/content/preparation/status').status_code == 503, 'content preparation default disabled without database access')
                self.check(client.get('/api/v1/channel-lab/accounts').status_code == 503, 'channel ingress default disabled without database access')
                cap = client.get('/api/v1/message-enrichment/capabilities').json()
                self.check(settings.message_enrichment_mode() == 'disabled' and cap['mode'] == 'disabled' and cap['transport'] == 'none' and client.get('/api/v1/message-enrichment/conversations').status_code == 503, 'enrichment default disabled without database access')

    def run(self, backend_tests):
        import psycopg
        files = sorted((ROOT/'database/migrations').glob('*.sql'))
        self.check(len(files) == 20 and [p.name[:3] for p in files] == [f'{n:03}' for n in range(1,21)], 'exact incremental migrations001–020 present')
        manifest = {}
        for path in files:
            committed = subprocess.run(['git','show','HEAD:database/migrations/'+path.name], cwd=ROOT, capture_output=True, check=True).stdout
            self.check(digest(committed) == digest(path.read_bytes()), 'migration immutable versus Git HEAD: '+path.name)
            manifest[path.name] = digest(committed)
        self.report['migration_sha256'] = manifest
        self.report['git_head'] = subprocess.run(['git','rev-parse','HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        self.report['script_sha256'] = digest(Path(__file__).read_bytes())
        self.start()
        with self.connect(autocommit=True) as conn:
            version = conn.execute('SHOW server_version_num').fetchone()[0]
            self.check(int(version)//10000 == 16, 'actual PostgreSQL major16')
            self.report['postgres_version_num'] = version
            conn.execute('CREATE DATABASE rc80_restore')
            conn.execute('CREATE DATABASE rc80_backend')
        with tempfile.TemporaryDirectory(prefix='socialmei-rc80-migrations-') as directory:
            folder = Path(directory)
            shutil.copy2(files[0], folder/files[0].name)
            self.migrate(folder, '001 bootstrap')
            self.seed_initial()
            original = self.snapshot()['tables']
            for path in files[1:11]:
                shutil.copy2(path, folder/path.name)
            self.migrate(folder, '002 through011 upgrade with preexisting001 rows')
            tenants = self.seed_workspaces()
            before = self.snapshot()
            self.check(all(before['tables'][name] == rows for name,rows in original.items() if name != 'schema_migrations'), '001 legacy values preserved through011')
            legacy = {name:rows for name,rows in before['tables'].items() if name != 'schema_migrations'}
            for number, path in enumerate(files[11:], 12):
                before_ingress = self.snapshot() if number == 20 else None
                shutil.copy2(path, folder/path.name)
                self.migrate(folder, f'incremental{number:03}')
                if before_ingress is not None:
                    upgraded = self.snapshot()
                    for table, rows in before_ingress['tables'].items():
                        if table == 'schema_migrations':
                            self.check(all(row in upgraded['tables'][table] for row in rows), '020 preserves existing migration ledger timestamps')
                            continue
                        columns = [column[1] for column in before_ingress['columns'] if column[0] == table]
                        projected = [{key: row[key] for key in columns} for row in upgraded['tables'][table]]
                        self.check(sorted(projected,key=canonical) == rows, '020 preserves every preexisting value: '+table)
                self.seed_incremental(number, tenants)
                current = self.snapshot()
                self.check(all(current['tables'][name] == rows for name,rows in legacy.items()), f'{number:03} preserves all preexisting001–011 table values')
            baseline = self.snapshot()
            self.migrate(folder, 'ledger replay001–020')
            self.check(self.snapshot() == baseline, 'team migrator ledger replay preserves rows, schema, sequences and applied_at')
            with self.connect() as conn:
                for path in files[11:]:
                    conn.execute(path.read_text(), prepare=False)
            self.check(self.snapshot() == baseline, 'raw012–020 reapplication is idempotent with seeded data')
            with tempfile.TemporaryDirectory(prefix='socialmei-rc80-failure-') as failure:
                (Path(failure)/'999_release_probe.sql').write_text('CREATE TABLE socialmei.rc80_rollback_probe(id INT); SELECT 1/0;')
                try:
                    self.migrate(Path(failure), 'deliberately failing transactional migration')
                except psycopg.Error:
                    pass
                else:
                    raise AssertionError('Expected migration failure did not occur')
            self.check(self.snapshot() == baseline, 'failed migration rolls back table and ledger without touching previous data')
            self.defaults(tenants)
            self.check(self.snapshot() == baseline, 'disabled-feature compatibility preserves all tables and seeded data')
            self.prove_fks(tenants, 'rc80_upgrade')
            with self.connect() as conn:
                self.check(self.canonical_expression(conn, 'instagram_sim_publications', "status='simulated'") != self.canonical_expression(conn, 'instagram_sim_publications', "status='published'"), 'negative probe: canonicalization distinguishes different status restrictions')
                self.check(self.canonical_expression(conn, 'instagram_sim_publications', 'NULL::boolean', null_passes=False) != self.canonical_expression(conn, 'instagram_sim_publications', 'TRUE', null_passes=False), 'negative probe: partial-index NULL and TRUE membership remain distinct')
            self.docker('exec', self.container, 'pg_dump', '-U', 'rc80', '-d', 'rc80_upgrade', '--format=custom', '--file=/tmp/rc80.dump')
            self.docker('exec', self.container, 'pg_restore', '-U', 'rc80', '-d', 'rc80_restore', '--exit-on-error', '--no-owner', '/tmp/rc80.dump')
            self.docker('cp', self.container+':/tmp/rc80.dump', str(folder/'synthetic-rc80.dump'))
            restored = self.snapshot('rc80_restore')
            differences = [key for key in baseline if restored[key] != baseline[key]]
            if differences:
                self.report['restore_differences'] = differences
                for key in differences:
                    if isinstance(baseline[key], dict):
                        self.report['restore_differences_'+key] = [name for name in baseline[key] if baseline[key][name] != restored[key].get(name)]
                    else:
                        self.report['restore_differences_'+key] = {'before_sha256':digest(canonical(baseline[key]).encode()), 'after_sha256':digest(canonical(restored[key]).encode()), 'names':[list(row[:2]) for row in baseline[key] if row not in restored[key]]}
            self.check(not differences, 'custom pg_dump/pg_restore preserves every table value, count, FK, index, column, sequence and ledger timestamp')
            self.prove_fks(tenants, 'rc80_restore')
            self.migrate(folder, 'restored ledger replay', 'rc80_restore')
            self.check(self.snapshot('rc80_restore') == baseline, 'restored ledger safely prevents migration replay')
            self.report['table_counts'] = {name:len(rows) for name,rows in baseline['tables'].items()}
            self.report['snapshot_sha256'] = digest(canonical(baseline).encode())
            self.report['dump_sha256'] = digest((folder/'synthetic-rc80.dump').read_bytes())
            self.report['ledger_versions'] = [row['version'] for row in baseline['tables']['schema_migrations']]
        if backend_tests:
            env = dict(os.environ)
            env.update({'DATABASE_URL':self.dsn.rsplit('/',1)[0]+'/rc80_backend',
                        'TEST_DATABASE_URL':self.dsn.rsplit('/',1)[0]+'/rc80_backend',
                        'SOCIALMEI_CORS_ORIGINS':'','SOCIALMEI_SHARED_DATA_ENABLED':'true',
                        'SOCIALMEI_WORKSPACE_SLUG':'ci-shared-data','SOCIALMEI_WORKSPACE_NAME':'CI Shared Data'})
            for key in ('SOCIALMEI_INSTAGRAM_MODE','SOCIALMEI_MESSAGE_ENRICHMENT_MODE','SOCIALMEI_MESSAGE_ENRICHMENT_TEST_KEY','SOCIALMEI_AUTH_ENABLED'):
                env.pop(key, None)
            result = subprocess.run([sys.executable,'-m','unittest','discover','-s','python-service','-p','test_*.py','-v'], cwd=ROOT, env=env, capture_output=True, text=True, timeout=240)
            (self.output/'backend.log').write_text(self.clean_text(result.stdout+result.stderr))
            self.check(result.returncode == 0, 'full backend suite on a separate owned disposable database')
            self.report['backend_summary'] = [line for line in result.stderr.splitlines() if line.startswith('Ran ') or line == 'OK']
        self.check(all(digest(path.read_bytes()) == manifest[path.name] for path in files), 'migration hashes unchanged after rehearsal')

    def cleanup(self):
        log = []
        for kind, resource in (('container', self.container), ('network', self.network)):
            if not resource:
                continue
            listing = ('ps', '-aq', '--no-trunc', '--filter', 'id='+resource) if kind == 'container' else ('network', 'ls', '-q', '--no-trunc', '--filter', 'id='+resource)
            present = self.docker(*listing).stdout.split()
            if resource not in present:
                log.append(kind+': absence confirmed by successful listing')
                continue
            args = ('inspect', resource) if kind == 'container' else ('network', 'inspect', resource)
            details = json.loads(self.docker(*args).stdout)[0]
            labels = details['Config']['Labels'] if kind == 'container' else details['Labels']
            if labels.get(LABEL) != self.token:
                raise RuntimeError('Refusing cleanup: resource ownership label mismatch')
            self.docker('rm', '-f', '-v', resource) if kind == 'container' else self.docker('network','rm',resource)
            if resource in self.docker(*listing).stdout.split():
                raise RuntimeError('Owned resource remains after cleanup')
            log.append(kind+': removed owned resource; absence confirmed')
        remaining_volumes = set(self.docker('volume', 'ls', '-q').stdout.split())
        if remaining_volumes.intersection(self.volumes):
            raise RuntimeError('Owned anonymous test volume remains after cleanup')
        self.report['anonymous_volumes_removed'] = len(self.volumes)
        self.report['cleanup'] = True
        (self.output/'cleanup.log').write_text('\n'.join(log)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='explicitly authorize this isolated local Docker rehearsal')
    parser.add_argument('--output', type=Path, default=Path('/tmp/socialmei-release-candidate-db'))
    parser.add_argument('--backend-tests', action='store_true')
    args = parser.parse_args()
    if not args.run:
        parser.error('--run is required; no resources created')
    args.output.mkdir(parents=True, exist_ok=True)
    args.output.chmod(0o700)
    sys.path.insert(0, str(ROOT/'python-service'))
    import psycopg  # Fail before creating resources when prerequisites are absent.
    runner = Rehearsal(args.output)
    status = 0
    try:
        runner.run(args.backend_tests)
        runner.report['result'] = 'passed'
    except Exception as error:
        status = 1
        runner.report['result'] = 'failed'
        runner.report['error'] = runner.clean_text(type(error).__name__+': '+str(error))
        print('FAIL:', runner.report['error'], file=sys.stderr)
    finally:
        try:
            runner.cleanup()
        except Exception as error:
            status = 1
            runner.report['result'] = 'failed'
            runner.report['cleanup_error'] = runner.clean_text(str(error))
        (args.output/'result.json').write_text(json.dumps(runner.report, indent=2, ensure_ascii=False))
    print('Evidence:', args.output/'result.json')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
