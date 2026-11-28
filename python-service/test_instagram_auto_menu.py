import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row
import instagram_auto_menu as menu
import test_instagram_direct_outbox as fixtures
from test_instagram_simulation import DB


class AutoMenuHandoffContracts(unittest.TestCase):
    def test_recovery_window_defaults_to_two_minutes_and_invalid_settings_never_query(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(menu.source_max_age(), 120)
        for value in ('0', '119', '901', '-1', '1.5', 'forever', '???'):
            with self.subTest(value=value), patch.dict(os.environ, {
                    'SOCIALMEI_INSTAGRAM_AUTO_MENU_MAX_AGE_SECONDS': value}), \
                    patch.object(menu, 'enabled', return_value=True), patch.object(menu, 'db') as db:
                with self.assertRaises(RuntimeError):
                    menu.next_source(60, datetime.now(timezone.utc))
                db.assert_not_called()

    def test_send_limits_preserve_handoff_without_sending_or_opening_token(self):
        from unittest.mock import MagicMock
        now = datetime.now(timezone.utc)
        row = {'conversation_id': 12, 'text': 'ATENDENTE', 'occurred_at': now,
               'connection_id': str(uuid4()), 'external_account_id': '987',
               'contact_ref': 'instagram:123'}
        state = {'state': 'menu', 'last_message_id': None, 'last_occurred_at': None}
        for counts in ({'total': 60, 'contact': 1}, {'total': 10, 'contact': 10}):
            conn = MagicMock()
            conn.execute.return_value.fetchone.side_effect = [True, None, None, counts, state, None]
            runtime = MagicMock(send=True)
            with patch.object(menu, 'enabled', return_value=True), patch.object(menu, 'db') as db, \
                    patch.object(menu, '_lock'), patch.object(menu, 'source', return_value=row):
                db.return_value.__enter__.return_value = conn
                self.assertEqual(menu.reply(runtime, 7, 99, now), 'skipped')
            runtime.direct.vault.open.assert_not_called()
            runtime.direct.adapter.send_direct.assert_not_called()
            inserts = [call.args[1] for call in conn.execute.call_args_list
                       if 'INSERT INTO socialmei.ig_menu_replies' in call.args[0]]
            self.assertEqual(len(inserts), 1)
            self.assertEqual(inserts[0][-2], 'skipped')
            updates = [call.args[1] for call in conn.execute.call_args_list
                       if 'UPDATE socialmei.ig_menu_conversations' in call.args[0]]
            self.assertEqual(updates[0][0], 'human')


@unittest.skipUnless(DB, 'Disposable PostgreSQL required')
class AutoMenuDatabaseTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.DatabaseTests.setUpClass.__func__)
    tearDown=fixtures.DatabaseTests.tearDown
    begin=fixtures.DatabaseTests.begin
    complete=fixtures.DatabaseTests.complete
    post=fixtures.DatabaseTests.post
    incoming=fixtures.DatabaseTests.incoming
    request=fixtures.DatabaseTests.request

    def setUp(self):
        fixtures.DatabaseTests.setUp(self)
        self.workspace=self.identity['workspace_id']
        flags=patch.dict(os.environ,{'SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED':'true',
                                    'SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES':str(self.workspace)})
        flags.start(); self.addCleanup(flags.stop)
        self.runtime=SimpleNamespace(send=True,direct=self.direct)
        self.start=datetime.now(timezone.utc)-timedelta(seconds=5)

    def test_reviewed_recovery_window_resumes_persisted_five_minute_backlog_once(self):
        start = datetime.now(timezone.utc) - timedelta(minutes=10)
        with menu.db() as conn:
            conn.execute("UPDATE socialmei.me_messages SET occurred_at=NOW()-INTERVAL '5 minutes' "
                         "WHERE workspace_id=%s AND id=%s", (self.workspace, self.source))
            conn.execute("UPDATE socialmei.ig_meta_ingress_events SET received_at=NOW()-INTERVAL '5 minutes' "
                         "WHERE workspace_id=%s AND message_id=%s", (self.workspace, self.source))
        self.assertIsNone(menu.next_source(self.workspace, start))
        with patch.dict(os.environ, {'SOCIALMEI_INSTAGRAM_AUTO_MENU_MAX_AGE_SECONDS': '900'}):
            self.assertEqual(menu.next_source(self.workspace, start), self.source)
            self.assertEqual(menu.reply(self.runtime, self.workspace, self.source, start), 'confirmed')
            self.assertIsNone(menu.next_source(self.workspace, start))
            self.assertEqual(menu.reply(self.runtime, self.workspace, self.source, start), 'duplicate')
            self.assertIsNone(menu.next_source(self.identities[1]['workspace_id'], start))
        self.assertEqual(len(self.send_calls), 1)

    def test_disconnected_or_expired_account_does_not_starve_next_source(self):
        self.assertEqual(menu.next_source(self.workspace, self.start), self.source)
        with menu.db() as conn:
            previous = conn.execute(
                "SELECT encrypted_token FROM socialmei.ig_meta_connections "
                "WHERE workspace_id=%s AND status='connected'", (self.workspace,)
            ).fetchone()
            self.assertIsNotNone(previous)
            # Mirror the real disconnect contract; the database forbids
            # retaining an encrypted access token for a disconnected account.
            conn.execute("UPDATE socialmei.ig_meta_connections "
                         "SET status='disconnected',encrypted_token=NULL,disconnected_at=NOW(),"
                         "revision=revision+1 WHERE workspace_id=%s", (self.workspace,))
        self.assertIsNone(menu.next_source(self.workspace, self.start))
        with menu.db() as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET status='connected', "
                         "encrypted_token=%s,disconnected_at=NULL,revision=revision+1,"
                         "issued_at=NOW()-INTERVAL '2 days',expires_at=NOW()-INTERVAL '1 day' "
                         "WHERE workspace_id=%s",
                         (previous['encrypted_token'], self.workspace))
        self.assertIsNone(menu.next_source(self.workspace, self.start))
        self.assertEqual(self.send_calls, [])

    def test_missing_message_scope_does_not_enter_dispatch_queue(self):
        with menu.db() as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET scopes=ARRAY['instagram_business_basic'] "
                         "WHERE workspace_id=%s", (self.workspace,))
        self.assertIsNone(menu.next_source(self.workspace, self.start))
        self.assertEqual(self.send_calls, [])

    def test_concurrent_workers_dispatch_once_and_preserve_receipt(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:menu.reply(self.runtime,self.workspace,self.source,self.start),range(2)))
        self.assertEqual(sorted(results),['confirmed','duplicate'])
        self.assertEqual(len(self.send_calls),1)
        with menu.db() as conn:
            rows=conn.execute('SELECT status,provider_message_id FROM socialmei.ig_menu_replies WHERE workspace_id=%s',
                              (self.workspace,)).fetchall()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'confirmed')

    def test_restart_after_confirmation_keeps_durable_deduplication(self):
        from instagram_worker_state import reconcile
        checkpoint = reconcile(None, self.workspace, self.start, unresolved=False)
        checkpoint['in_flight'] = True
        self.assertEqual(menu.reply(self.runtime, self.workspace, self.source, self.start), 'confirmed')
        with menu.db() as conn:
            unresolved = bool(conn.execute("SELECT 1 FROM socialmei.ig_menu_replies WHERE workspace_id=%s "
                                           "AND status IN ('dispatching','uncertain') LIMIT 1",
                                           (self.workspace,)).fetchone())
        recovered = reconcile(checkpoint, self.workspace, self.start, unresolved=unresolved)
        self.assertFalse(recovered['in_flight'])
        self.assertIsNone(menu.next_source(self.workspace, self.start))
        self.assertEqual(menu.reply(self.runtime, self.workspace, self.source, self.start), 'duplicate')
        self.assertEqual(len(self.send_calls), 1)

    def test_restart_with_uncertain_delivery_never_resends(self):
        from instagram_worker_state import reconcile
        checkpoint = reconcile(None, self.workspace, self.start, unresolved=False)
        checkpoint['in_flight'] = True
        self.send_error = TimeoutError('synthetic provider timeout')
        self.assertEqual(menu.reply(self.runtime, self.workspace, self.source, self.start), 'uncertain')
        with menu.db() as conn:
            unresolved = bool(conn.execute("SELECT 1 FROM socialmei.ig_menu_replies WHERE workspace_id=%s "
                                           "AND status IN ('dispatching','uncertain') LIMIT 1",
                                           (self.workspace,)).fetchone())
        with self.assertRaises(RuntimeError):
            reconcile(checkpoint, self.workspace, self.start, unresolved=unresolved)
        self.assertEqual(len(self.send_calls), 1)

    def test_observer_reads_persisted_direct_in_its_workspace_without_dispatch(self):
        from instagram_worker_observer import pending, checkpoint
        counts = pending(self.workspace, self.start)
        self.assertEqual(counts['pending_count'], 1)
        self.assertEqual(counts['latest_pending_message_id'], self.source)
        other = self.identities[1]['workspace_id']
        self.assertEqual(pending(other, self.start)['pending_count'], 0)
        state = checkpoint(None, self.workspace, self.start, counts)
        self.incoming(text='Outra mensagem sintética')
        resumed = checkpoint(state, self.workspace, self.start, pending(self.workspace, self.start))
        self.assertEqual(resumed['pending_count'], 2)
        self.assertFalse(resumed['send_enabled'])
        self.assertEqual(self.send_calls, [])

    def test_old_and_foreign_messages_never_dispatch(self):
        self.assertIsNone(menu.next_source(self.workspace,datetime.now(timezone.utc)+timedelta(seconds=1)))
        self.assertEqual(menu.reply(self.runtime,self.workspace,self.source,datetime.now(timezone.utc)+timedelta(seconds=1)),'skipped')
        other=self.identities[1]['workspace_id']
        with patch.dict(os.environ,{'SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES':str(other)}):
            self.assertEqual(menu.reply(self.runtime,other,self.source,self.start),'skipped')
        self.assertEqual(self.send_calls,[])

    def test_human_draft_pauses_auto_until_cancelled_and_explicit_resume(self):
        draft=self.request('/jobs',{'operation_id':str(uuid4()),'source_message_id':self.source,'text':'Resposta humana de teste'})
        self.assertEqual(draft.status_code,200,draft.text)
        self.assertEqual(menu.reply(self.runtime,self.workspace,self.source,self.start),'skipped')
        self.assertEqual(self.send_calls,[])
        row=draft.json()
        cancel=self.request('/jobs/'+row['id']+'/cancel',{'operation_id':str(uuid4()),'expected_revision':row['revision']})
        self.assertEqual(cancel.status_code,200,cancel.text)
        source=self.incoming(text='0')
        self.assertEqual(menu.reply(self.runtime,self.workspace,source,self.start),'confirmed')

    def test_uncertain_result_never_retries_and_blocks_automatic_continuation(self):
        self.send_error=TimeoutError('synthetic provider timeout')
        self.assertEqual(menu.reply(self.runtime,self.workspace,self.source,self.start),'uncertain')
        self.assertEqual(menu.reply(self.runtime,self.workspace,self.source,self.start),'duplicate')
        with self.assertRaises(HTTPException):
            menu.reply(self.runtime,self.workspace,self.incoming(text='0'),self.start)
        self.assertEqual(len(self.send_calls),1)

    def test_manual_draft_is_blocked_while_auto_dispatch_is_in_flight(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        self.send_gate=threading.Event()
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(menu.reply,self.runtime,self.workspace,self.source,self.start)
            self.assertTrue(self.started.wait(5))
            try:
                draft=self.request('/jobs',{'operation_id':str(uuid4()),'source_message_id':self.source,'text':'Fixture humana'})
                self.assertEqual(draft.status_code,409,draft.text)
            finally:
                self.send_gate.set()
            self.assertEqual(future.result(),'confirmed')

    def test_menu_handoff_and_explicit_resume_preserve_human_state(self):
        from instagram_meta_adapter import ProviderResponse
        for index,text in enumerate(['5','Mensagem após atendimento humano','0']):
            self.send_response=ProviderResponse(200,('{"recipient_id":"123456789","message_id":"receipt-'+str(index)+'"}').encode())
            outcome=menu.reply(self.runtime,self.workspace,self.incoming(text=text),self.start)
            self.assertEqual(outcome,'skipped' if index==1 else 'confirmed')
        self.assertEqual(len(self.send_calls),2)

    def test_confirmed_auto_reply_is_projected_once_in_inbox(self):
        self.assertEqual(menu.reply(self.runtime,self.workspace,self.source,self.start),'confirmed')
        response=self.client.get('/api/v1/message-enrichment/conversations')
        self.assertEqual(response.status_code,200,response.text)
        messages=[m for row in response.json()['items'] for m in row['messages'] if m.get('direction')=='outgoing']
        self.assertEqual(len(messages),1)
        self.assertEqual(messages[0]['provider'],'instagram')

    def test_booking_plan_uses_the_existing_safe_direct_sender(self):
        import channel_booking_flow as flow
        import instagram_booking_flow as booking
        plan = flow.response('booking_services', 'Qual serviço deseja agendar?',
            [flow.option('1', 'Serviço de teste', 'resources', service_id=42),
             *flow.navigation()], False)
        with patch('instagram_auto_menu.instagram_booking_flow.respond',
                   return_value=(plan[0], plan[1], {'step': 'services'})):
            self.assertEqual(menu.reply(self.runtime, self.workspace, self.source, self.start),
                             'confirmed')
        with menu.db() as conn:
            row = conn.execute('SELECT text,status FROM socialmei.ig_menu_replies '
                'WHERE workspace_id=%s AND source_message_id=%s',
                (self.workspace, self.source)).fetchone()
        self.assertEqual(row['status'], 'confirmed')
        self.assertIn('Qual serviço deseja agendar?', row['text'])
        self.assertEqual(booking._decode_reference(row['text'])[0][1]['service_id'], 42)
        self.assertEqual(len(self.send_calls), 1)
        self.assertNotIn(booking.MARKER, self.send_calls[0].json_body.decode('utf-8'))
        inbox = self.client.get('/api/v1/message-enrichment/conversations')
        self.assertEqual(inbox.status_code, 200, inbox.text)
        self.assertNotIn(booking.MARKER, inbox.text)

    def test_instagram_presence_review_and_text_confirmation_write_one_event(self):
        from instagram_meta_adapter import ProviderResponse
        with psycopg.connect(DB) as conn:
            slug,name,config=conn.execute("SELECT slug,nome,configuracao FROM socialmei.workspaces WHERE id=%s",
                                          (self.workspace,)).fetchone()
        self.identity.update(workspace_slug=slug,nome_negocio=name,configuracao=config)
        def create(path, body):
            response=self.client.post(path,json=body,headers=self.headers)
            self.assertEqual(response.status_code,201,response.text)
            return response.json()
        customer=create('/api/v1/clientes',{'nome':'Contato fixture'})
        service=create('/api/v1/produtos',{'nome':'Atendimento fixture','tipo':'Serviço','preco':40,'duracao_minutos':30})
        resource=create('/api/v1/agenda/resources',{'operation_id':str(uuid4()),'nome':'Equipe'})
        appointment=create('/api/v1/agenda/appointments',{
            'operation_id':str(uuid4()),'cliente_id':customer['id'],'servico_id':service['id'],
            'resource_id':resource['id'],'scheduled_for':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
        })
        with psycopg.connect(DB) as conn:
            conn.execute("UPDATE socialmei.me_conversations SET cliente_id=%s WHERE workspace_id=%s",
                         (customer['id'],self.workspace))
        def text_reply(value):
            self.send_response=ProviderResponse(200,('{"recipient_id":"123456789","message_id":"fixture-'
                +uuid4().hex+'"}').encode())
            mid=self.incoming(text=value)
            self.assertEqual(menu.reply(self.runtime,self.workspace,mid,self.start),'confirmed')
            return mid
        with patch.dict(os.environ,{'SOCIALMEI_CHANNEL_ATTENDANCE_ENABLED':'YES',
                                    'SOCIALMEI_CHANNEL_ATTENDANCE_WORKSPACES':str(self.workspace)}):
            text_reply('8')
            text_reply('1')
            text_reply('3')
            with psycopg.connect(DB) as conn:
                self.assertEqual(conn.execute("SELECT attendance FROM socialmei.agenda_appointments WHERE id=%s",
                                              (appointment['id'],)).fetchone(),(None,))
            mid=text_reply('1')
            self.assertEqual(menu.reply(self.runtime,self.workspace,mid,self.start),'duplicate')
        with psycopg.connect(DB) as conn:
            self.assertEqual(conn.execute("SELECT source_channel,source_message_id FROM socialmei.agenda_attendance_events "
                                          "WHERE appointment_id=%s",(appointment['id'],)).fetchall(),[('instagram',mid)])

    def test_full_direct_booking_in_two_isolated_stores_without_provider(self):
        """Meta-like inbound events, existing sender and real disposable agenda."""
        from instagram_meta_adapter import ProviderResponse
        from instagram_booking_flow import MARKER
        import channel_booking as booking

        other = self.identities[1]['workspace_id']
        with psycopg.connect(DB) as conn:
            conn.execute('UPDATE socialmei.workspaces SET nome=%s WHERE id=%s',
                         ('Bella Store (somente fixture)', self.workspace))
            conn.execute('UPDATE socialmei.workspaces SET nome=%s WHERE id=%s',
                         ('Brilho Limpeza (somente fixture)', other))
            slug, name, config = conn.execute(
                'SELECT slug,nome,configuracao FROM socialmei.workspaces WHERE id=%s',
                (self.workspace,)).fetchone()
        # The real authenticated API expects a full workspace identity; the
        # generic Instagram transport fixture intentionally omits these fields.
        self.identity.update(workspace_slug=slug, nome_negocio=name,
                             configuracao=config)
        def create(path, body):
            response = self.client.post(path, json=body, headers=self.headers)
            self.assertEqual(response.status_code, 201, response.text)
            return response.json()

        customer = create('/api/v1/clientes', {'nome': 'Cliente Instagram simulado'})
        service = create('/api/v1/produtos', {'nome': 'Serviço simulado de avaliação',
            'tipo': 'Serviço', 'preco': 80, 'duracao_minutos': 30})
        create('/api/v1/agenda/resources', {
            'operation_id': str(uuid4()), 'nome': 'Recurso simulado A'})
        policy = {'enabled': True, 'timezone': 'UTC', 'lead_minutes': 0,
            'hours': [{'weekday': day, 'opens': '09:00', 'closes': '17:00'}
                      for day in range(7)]}
        configured = self.client.put('/api/v1/agenda/channel-booking',
            json={'expected_revision': 0, 'policy': policy}, headers=self.headers)
        self.assertEqual(configured.status_code, 200, configured.text)
        with psycopg.connect(DB) as conn:
            conn.execute('UPDATE socialmei.me_conversations SET cliente_id=%s '
                         "WHERE workspace_id=%s AND origin='instagram'",
                         (customer['id'], self.workspace))

        def send_reply(message_text):
            self.send_response = ProviderResponse(200,
                ('{"recipient_id":"123456789","message_id":"' +
                 'fixture-' + uuid4().hex + '"}').encode())
            mid = self.incoming(text=message_text)
            with patch('channel_booking.settings.instagram_n8n_ingress_configuration',
                       return_value={'meta_app_secret': 'a' * 64}):
                result = menu.reply(self.runtime, self.workspace, mid, self.start)
            self.assertEqual(result, 'confirmed')
            with menu.db() as conn:
                row = conn.execute('SELECT text FROM socialmei.ig_menu_replies '
                    'WHERE workspace_id=%s AND source_message_id=%s',
                    (self.workspace, mid)).fetchone()
            self.assertIsNotNone(row)
            self.assertNotIn(MARKER, self.send_calls[-1].json_body.decode('utf-8'))
            return mid, row['text']

        with patch.dict(os.environ,
                        {'SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES': str(other)}):
            self.assertEqual(menu.reply(self.runtime, other, self.source, self.start),
                             'skipped')
        self.assertEqual(len(self.send_calls), 0)

        _, services = send_reply('6')
        self.assertIn('Qual serviço', services)
        self.assertIn(MARKER, services)
        _, resources = send_reply('1')
        self.assertIn('Escolha', resources)
        _, days = send_reply('1')
        self.assertIn('Escolha a data', days)
        day = (datetime.now(timezone.utc) + timedelta(days=1)).date()
        date_label = day.strftime('%d/%m/%Y')
        choice = next(line.split(' - ', 1)[0] for line in days.splitlines()
                      if line.endswith(date_label) and ' - ' in line)
        _, slots = send_reply(choice)
        self.assertIn('Escolha um horário', slots)
        _, review = send_reply('1')
        self.assertIn('Confirme seu agendamento', review)
        with psycopg.connect(DB) as conn:
            count = conn.execute('SELECT count(*) FROM socialmei.agenda_appointments '
                'WHERE workspace_id IN (%s,%s)', (self.workspace, other)).fetchone()[0]
        self.assertEqual(count, 0)

        confirmed_source, confirmation = send_reply('1')
        self.assertIn('Agendamento confirmado', confirmation)
        with psycopg.connect(DB) as conn:
            booking_rows = conn.execute(
                'SELECT workspace_id,cliente_id,servico_id FROM socialmei.agenda_appointments '
                'WHERE workspace_id IN (%s,%s)', (self.workspace, other)).fetchall()
            second_policy = conn.execute(
                "SELECT configuracao ? 'channel_booking' FROM socialmei.workspaces "
                'WHERE id=%s', (other,)).fetchone()[0]
            conversation = conn.execute(
                'SELECT conversation_id FROM socialmei.me_messages '
                'WHERE workspace_id=%s AND id=%s',
                (self.workspace, confirmed_source)).fetchone()[0]
        self.assertEqual(booking_rows, [(self.workspace, customer['id'], service['id'])])
        self.assertFalse(second_policy)
        with self.assertRaises(HTTPException) as blocked:
            booking.services_for_message(other, conversation, confirmed_source,
                                         'instagram')
        self.assertIn(blocked.exception.status_code, {403, 404})
        self.assertEqual(len(self.send_calls), 6)
        self.assertEqual(menu.reply(self.runtime, self.workspace, confirmed_source,
                                    self.start), 'duplicate')
        with psycopg.connect(DB) as conn:
            self.assertEqual(conn.execute(
                'SELECT count(*) FROM socialmei.agenda_appointment_history '
                'WHERE workspace_id=%s', (self.workspace,)).fetchone()[0], 1)

    def test_migration_is_idempotent_and_rejects_cross_workspace_state(self):
        from pathlib import Path
        with psycopg.connect(DB) as conn:
            conn.execute((Path(__file__).resolve().parents[1]/'database/migrations/039_instagram_auto_menu.sql').read_text(),prepare=False)
        with psycopg.connect(DB) as conn:
            conversation=conn.execute('SELECT conversation_id FROM socialmei.me_messages WHERE workspace_id=%s AND id=%s',
                                      (self.workspace,self.source)).fetchone()[0]
        with self.assertRaises(psycopg.errors.ForeignKeyViolation),psycopg.connect(DB) as conn:
            conn.execute('INSERT INTO socialmei.ig_menu_conversations(workspace_id,conversation_id) VALUES(%s,%s)',
                         (self.identities[1]['workspace_id'],conversation))
