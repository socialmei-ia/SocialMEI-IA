"""Management contracts with controlled storage; never production or provider I/O."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4
import unittest
from fastapi import HTTPException
import appointments
import channel_booking as core
import channel_booking_flow as flow
import instagram_booking_flow as ig


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        start = (self.now + timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0)
        self.row = dict(id=uuid4(), cliente_id=9, servico_id=31, resource_id=uuid4(),
            service_name='Consulta', duration_minutes=30, price=Decimal('50.00'),
            scheduled_for=start, ends_at=start+timedelta(minutes=30), status='pending', revision=1)
        self.reference = dict(id=str(self.row['id']), revision=1,
            snapshot=core.appointment_snapshot(self.row), binding='bound-conversation')
        self.context = dict(cliente_id=9, binding='bound-conversation')
        self.conn = MagicMock()
        self.conn.execute.return_value.fetchone.side_effect = self.fetch
        self.key = 'controlled-management-signing-key-long-enough'
        self.writes = []
        patches = [patch.object(core, 'context_for_message', return_value=self.context),
            patch.object(appointments, 'lock_workspace'),
            patch.object(appointments, 'lock_resource', return_value={'revision': 1, 'nome': 'Equipe'}),
            patch.object(appointments, 'service', return_value={'versao': 1, 'preco': Decimal('50.00'), 'duracao_minutos': 30}),
            patch.object(appointments, 'update_appointment_in', side_effect=self.write),
            patch.object(core, 'active_policy', return_value=(SimpleNamespace(), 'policy')),
            patch.object(core, 'allowed_start', return_value=True)]
        for item in patches:
            item.start(); self.addCleanup(item.stop)

    def fetch(self):
        args = self.conn.execute.call_args.args[1]
        if args != (7, 9, self.row['id']):
            return None
        return dict(self.row)

    def write(self, conn, workspace, identifier, payload):
        self.assertEqual((workspace, identifier), (7, self.row['id']))
        if payload.expected_revision != self.row['revision']:
            raise HTTPException(409, 'Changed')
        self.writes.append(payload)
        self.row.update(status=payload.status, revision=self.row['revision']+1)
        if payload.scheduled_for:
            self.row.update(scheduled_for=payload.scheduled_for,
                            ends_at=payload.scheduled_for+timedelta(minutes=30))
        return appointments.view({**self.row, 'resource_name':'Equipe'})

    def token(self, **changes):
        claims = dict(binding=self.context['binding'], policy='policy', service=31,
            service_revision=1, resource=str(self.row['resource_id']), resource_revision=1,
            start=(self.row['scheduled_for']+timedelta(hours=1)).isoformat(),
            expires=int((self.now+timedelta(minutes=10)).timestamp()))
        claims.update(changes)
        return core.confirmation_token(claims, self.key)

    def apply(self, origin='instagram', **options):
        return core.change_for_message(7, 12, 13, origin, self.reference,
            connection=self.conn, confirmed=True, **options)

    def test_cancel_is_owned_explicit_and_idempotent_in_both_channels(self):
        first = self.apply('waha')
        second = self.apply('instagram')
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'cancelled')
        self.assertEqual(len(self.writes), 1)

    def test_missing_consent_never_loads_or_changes_an_appointment(self):
        with self.assertRaises(HTTPException):
            core.change_for_message(7,12,13,'instagram',self.reference,connection=self.conn)
        self.conn.execute.assert_not_called()
        self.assertFalse(self.writes)

    def test_foreign_customer_workspace_or_reference_are_refused(self):
        for customer in (10, None):
            with patch.object(core, 'context_for_message', return_value={**self.context, 'cliente_id': customer}):
                with self.assertRaises(HTTPException): self.apply()
        for change in ({'id':str(uuid4())}, {'binding':'other-conversation'}, {'revision':True}):
            original = self.reference
            self.reference = {**original, **change}
            with self.assertRaises(HTTPException): self.apply()
            self.reference = original
        self.assertFalse(self.writes)

    def test_modified_revision_summary_past_or_finished_cannot_be_changed(self):
        original = dict(self.row)
        for change in ({'revision':3}, {'price':Decimal('60')}, {'status':'done'},
                       {'scheduled_for':self.now-timedelta(hours=1)}):
            self.row.update(change)
            with self.assertRaises(HTTPException): self.apply()
            self.row = dict(original)
        self.assertFalse(self.writes)

    def test_reschedule_updates_original_id_once_and_never_creates_a_booking(self):
        token = self.token()
        before = self.row['scheduled_for']
        first = self.apply(confirmation=token,signing_key=self.key)
        second = self.apply(confirmation=token,signing_key=self.key)
        self.assertEqual(first, second)
        self.assertEqual(self.row['scheduled_for'], before+timedelta(hours=1))
        self.assertEqual(self.row['status'], 'pending')
        self.assertEqual(len(self.writes), 1)

    def test_wrong_signature_binding_expiry_or_offer_conditions_refuse_reschedule(self):
        changes = [{'binding':'other'}, {'service':44}, {'resource':str(uuid4())},
                   {'expires':1}, {'policy':'changed'}, {'service_revision':2}, {'resource_revision':2}]
        for change in changes:
            with self.assertRaises(HTTPException):
                self.apply(confirmation=self.token(**change), signing_key=self.key)
        with self.assertRaises(HTTPException):
            self.apply(confirmation=self.token(), signing_key='wrong-key-also-long-enough-for-signing')
        self.assertFalse(self.writes)

    def test_conflicting_new_slot_propagates_without_success(self):
        with patch.object(appointments, 'update_appointment_in', side_effect=HTTPException(409,'occupied')):
            with self.assertRaises(HTTPException) as error:
                self.apply(confirmation=self.token(), signing_key=self.key)
        self.assertEqual(error.exception.status_code,409)
        self.assertFalse(self.writes)

    def test_human_pause_is_checked_before_mutation(self):
        with patch.object(core, 'context_for_message', side_effect=HTTPException(409,'human')):
            with self.assertRaises(HTTPException): self.apply()
        self.assertFalse(self.writes)

    def test_confirm_step_without_new_slot_cannot_cancel_by_accident(self):
        with self.assertRaises(HTTPException):
            flow.advance(self.conn, {'workspace_id':7}, {'conversation_id':12,'id':13},
                {'step':'confirm','appointment':self.reference},False,origin='instagram')
        self.assertFalse(self.writes)

    def test_management_choices_roundtrip_and_hide_opaque_identifiers(self):
        output = flow.response('booking_manage','Escolha uma ação',
            [flow.option('1','Cancelar','cancel_review',appointment=self.reference),
             flow.option('2','Reagendar','days',appointment=self.reference,service_id=31,
                         resource_id=str(self.row['resource_id']))],False)[1]
        stored = ig.render(output, {'step':'manage'})
        decoded = ig._decode_reference(stored)
        self.assertEqual(decoded[0][1]['appointment'],self.reference)
        self.assertNotIn(str(self.row['id']),ig.public_text(stored))
        self.assertLessEqual(len(stored.encode()),1000)

    def test_management_action_can_be_selected_through_normal_channel_menu(self):
        for origin in ('waha','instagram'):
            with patch.object(core,'appointments_for_message',return_value=[]), \
                 patch.object(core,'read_policy',return_value={'policy':{'timezone':'America/Fortaleza'}}):
                state,result = flow.advance(self.conn,{'workspace_id':7},
                    {'conversation_id':12,'id':13},{'step':'appointments'},False,origin=origin)
                self.assertEqual(state,'menu')
                self.assertEqual(result['action'],'booking_appointments')
                self.assertIn('Não há',result['text'])

    def test_instagram_cancel_journey_uses_confirmed_history_and_explicit_consent(self):
        from test_instagram_booking_flow import RecentReply
        message = {'id':13,'conversation_id':12,'text':'8'}
        row = {**self.row, 'reference':self.reference}
        previous = None
        with patch.object(core,'appointments_for_message',return_value=[row]), \
             patch.object(core,'read_policy',return_value={'policy':{'timezone':'UTC'}}), \
             patch.object(core,'owned_appointment',side_effect=lambda *args:dict(self.row)):
            actions = []
            for command in ('8','1','1','1'):
                message['text'] = command
                outcome = ig.respond(RecentReply(previous),7,message)
                self.assertIsNotNone(outcome, (command, len(actions), ig._recent_choices(previous)))
                state,result,selected = outcome
                actions.append(result['action'])
                previous = {'status':'confirmed','created_at':self.now,'text':ig.render(result,selected)}
                if len(actions)<4: self.assertFalse(self.writes)
            self.assertEqual(actions,['booking_appointments','booking_manage','booking_cancel_review','booking_cancelled'])
            self.assertEqual(len(self.writes),1)
            self.assertEqual(self.row['status'],'cancelled')

    def test_instagram_reschedule_confirmation_preserves_management_reference(self):
        from test_instagram_booking_flow import RecentReply
        token = self.token()
        offer = dict(service_id=31,service_name=self.row['service_name'],resource_id=str(self.row['resource_id']),
            resource_name='Equipe',price='50.00',duration_minutes=30,confirmation=token,
            scheduled_for=(self.row['scheduled_for']+timedelta(hours=1)).isoformat(),
            ends_at=(self.row['ends_at']+timedelta(hours=1)).isoformat())
        selected = {'step':'slots','appointment':self.reference,'day':'2026-11-20','page':0}
        result = flow.response('booking_slots','Escolha o horário',
            [flow.option('1','Novo horário','review',offer=offer,appointment=self.reference)],False)[1]
        previous = {'status':'confirmed','created_at':self.now,'text':ig.render(result,selected)}
        with patch.object(core,'signing_key_for_context',return_value=self.key), \
             patch.object(core,'slots_for_message',return_value={'items':[offer]}), \
             patch.object(core,'read_policy',return_value={'policy':{'timezone':'UTC'}}), \
             patch.object(core,'owned_appointment',side_effect=lambda *args:dict(self.row)):
            _,review,selection=ig.respond(RecentReply(previous),7,{'id':13,'conversation_id':12,'text':'1'})
            self.assertEqual(review['action'],'booking_review')
            self.assertFalse(self.writes)
            previous={'status':'confirmed','created_at':self.now,'text':ig.render(review,selection)}
            _,done,_=ig.respond(RecentReply(previous),7,{'id':14,'conversation_id':12,'text':'1'})
            self.assertEqual(done['action'],'booking_rescheduled')
            self.assertEqual(len(self.writes),1)
            self.assertEqual(self.row['scheduled_for'].isoformat(),offer['scheduled_for'])

    def test_other_workspace_cannot_change_reference_even_with_same_customer_number(self):
        with self.assertRaises(HTTPException):
            core.change_for_message(8,12,13,'instagram',self.reference,confirmed=True,connection=self.conn)
        self.assertFalse(self.writes)

    def test_whatsapp_cancellation_walks_existing_text_and_native_menus(self):
        for native in (False,True):
            original=dict(self.row)
            self.writes.clear()
            previous=None
            conn=MagicMock()
            conn.execute.return_value.fetchone.side_effect=lambda: {'result':previous} if previous else None
            channel={'workspace_id':7,'channel_id':2,'binding_hash':'channel-test'}
            listed={**self.row,'reference':self.reference}
            with patch.object(core,'appointments_for_message',return_value=[listed]), \
                 patch.object(core,'read_policy',return_value={'policy':{'timezone':'UTC'}}), \
                 patch.object(core,'owned_appointment',side_effect=lambda *args:dict(self.row)):
                expected=['booking_appointments','booking_manage','booking_cancel_review','booking_cancelled']
                for index,command in enumerate(('8','1','1','1')):
                    message={'id':13+index,'conversation_id':12,'text':command}
                    if native and previous:
                        message['catalog_target']=previous['choices'][0]['target']
                    state,result=flow.respond(conn,channel,message,{'state':'menu'},native=native)
                    self.assertEqual(result['action'],expected[index])
                    if index<3:self.assertFalse(self.writes)
                    previous=result
                self.assertEqual(len(self.writes),1)
                self.assertEqual(self.row['status'],'cancelled')
            self.row=original

    def test_shared_reschedule_slots_review_confirm_keep_reference_without_new_booking(self):
        for origin in ('waha','instagram'):
            original=dict(self.row)
            self.writes.clear()
            token=self.token()
            offer=dict(service_id=31,service_name='Consulta',resource_id=str(self.row['resource_id']),
                resource_name='Equipe',price='50.00',duration_minutes=30,confirmation=token,
                scheduled_for=(self.row['scheduled_for']+timedelta(hours=1)).isoformat(),
                ends_at=(self.row['ends_at']+timedelta(hours=1)).isoformat())
            target={'step':'slots','day':'2026-11-20','service_id':31,
                    'resource_id':str(self.row['resource_id']),'appointment':self.reference}
            with patch.object(core,'signing_key_for_context',return_value=self.key), \
                 patch.object(core,'slots_for_message',return_value={'items':[offer],'has_more':False}) as slots, \
                 patch.object(core,'read_policy',return_value={'policy':{'timezone':'UTC'}}), \
                 patch.object(core,'owned_appointment',side_effect=lambda *args:dict(self.row)), \
                 patch.object(appointments,'create_appointment_in') as create:
                for action in ('booking_slots','booking_review','booking_rescheduled'):
                    _,result=flow.advance(self.conn,{'workspace_id':7},{'id':13,'conversation_id':12},
                                          target,False,origin=origin)
                    self.assertEqual(result['action'],action)
                    if action!='booking_rescheduled':
                        self.assertFalse(self.writes)
                        target=result['choices'][0]['target']
                        self.assertEqual(target['appointment'],self.reference)
                self.assertEqual(slots.call_args.kwargs['appointment_reference'],self.reference)
                create.assert_not_called()
                self.assertEqual(len(self.writes),1)
            self.row=original
