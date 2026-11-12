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
