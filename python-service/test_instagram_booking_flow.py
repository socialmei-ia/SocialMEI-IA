"""Pure Instagram booking menu tests. No provider, live credentials, or database."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
from uuid import uuid4

import instagram_booking_flow as ig
import channel_booking_flow as shared


class RecentReply:
    def __init__(self, last=None):
        self.last = last
        self.queries = []

    def execute(self, query, args):
        self.queries.append((query, args))
        return self

    def fetchone(self):
        return self.last


class InstagramBookingFlowTests(unittest.TestCase):
    def message(self, text='6'):
        return {'id': 38, 'conversation_id': 12, 'text': text}

    def options(self, selected=None):
        if selected is None:
            selected = {'step': 'services'}
        output = shared.response('booking_services', 'Qual serviço deseja agendar?',
            [shared.option('1', 'Corte feminino', 'resources', service_id=31),
             shared.option('2', 'Lavagem', 'resources', service_id=44),
             *shared.navigation()], False)[1]
        return ig.render(output, selected)

    def test_render_roundtrip_has_explicit_expiry_and_navigation(self):
        text = self.options()
        self.assertIn('1 - Corte feminino', text)
        self.assertIn('0 - Voltar ao menu', text)
        self.assertIn(ig.MARKER, text)
        self.assertLessEqual(len(text.encode('utf-8')), 1000)
        row = {'status': 'confirmed', 'text': text, 'created_at': datetime.now(timezone.utc)}
        decoded = ig._recent_choices(row)
        self.assertEqual(decoded[0][1]['service_id'], 31)
        self.assertEqual(decoded[1][1]['service_id'], 44)
        self.assertEqual(len(decoded), 2)
        self.assertEqual(ig._recent_choices({**row, 'status': 'uncertain'}), [])
        self.assertEqual(ig._recent_choices({**row, 'status': 'failed'}), [])
        self.assertEqual(ig._recent_choices({**row, 'created_at':
            datetime.now(timezone.utc) - timedelta(minutes=11)}), [])

    def test_selection_reads_only_confirmed_own_conversation_reply(self):
        row = {'status': 'confirmed', 'text': self.options(), 'created_at': datetime.now(timezone.utc)}
        conn = RecentReply(row)
        output = shared.response('booking_resources', 'Escolha quem vai atender.',
            [shared.option('1', 'Profissional', 'days', service_id=31,
                           resource_id=str(uuid4())), *shared.navigation()], False)
        with patch('instagram_booking_flow.flow.advance', return_value=output) as advance:
            selected = ig.respond(conn, 77, self.message('1'))
        self.assertEqual(selected[0], 'menu')
        self.assertEqual(selected[2]['service_id'], 31)
        self.assertEqual(conn.queries[0][1], (77, 12))
        advance.assert_called_once()
        self.assertEqual(advance.call_args.kwargs, {'origin': 'instagram'})
        self.assertEqual(advance.call_args.args[1], {'workspace_id': 77})

    def test_explicit_start_without_history_and_exit_to_normal_menu(self):
        with patch('instagram_booking_flow.flow.advance',
                   return_value=shared.response('booking_services', 'Serviços', [], False)) as advance:
            started = ig.respond(RecentReply(), 1, self.message('Agendar'))
        self.assertEqual(started[2]['step'], 'services')
        self.assertEqual(advance.call_args.kwargs['origin'], 'instagram')
        self.assertIsNone(ig.respond(RecentReply(), 1, self.message('0')))
        self.assertIsNone(ig.respond(RecentReply(), 1, self.message('5')))
        self.assertIsNone(ig.respond(RecentReply(), 1, self.message('1')))

    def test_invalid_choice_does_not_create_or_confirm_booking(self):
        row = {'status': 'confirmed', 'text': self.options(), 'created_at': datetime.now(timezone.utc)}
        with patch('instagram_booking_flow.flow.advance',
                   side_effect=AssertionError('never called for unknown choice')):
            state, result, selected = ig.respond(RecentReply(row), 1, self.message('99'))
        self.assertEqual(state, 'menu')
        self.assertEqual(result['action'], 'booking_invalid_choice')
        self.assertEqual(selected['step'], 'services')

    def test_slot_reference_omits_full_offer_and_requires_same_datetime(self):
        resource = str(uuid4())
        raw = {
            'service_id': 31, 'resource_id': resource,
            'scheduled_for': '2026-11-14T09:00:00-03:00',
            'confirmation': 'SECRET_SIGNED_OFFER',
        }
        selection = {'step': 'slots', 'day': '2026-11-14', 'page': 1}
        text = ig.render(shared.response('booking_slots', 'Escolha um horário.',
            [shared.option('1', '09:00', 'review', offer=raw), *shared.navigation()], False)[1], selection)
        self.assertNotIn(raw['confirmation'], text)
        target = ig._decode_reference(text)[0][1]
        self.assertEqual(target['step'], 'review_ref')
        self.assertEqual(target['scheduled_for'], raw['scheduled_for'])
        self.assertEqual(target['page'], 1)
        with patch('instagram_booking_flow.booking.signing_key_for_context', return_value='key'), \
                patch('instagram_booking_flow.booking.slots_for_message',
                      return_value={'items': [{**raw, 'confirmation': 'REVALIDATED'}]}) as slots:
            offer = ig._review_offer(RecentReply(), 77, self.message('1'), target)
        self.assertEqual(offer['offer']['confirmation'], 'REVALIDATED')
        self.assertEqual(slots.call_args.kwargs['page'], 1)
        self.assertEqual(slots.call_args.args[3], 'instagram')
        with patch('instagram_booking_flow.booking.signing_key_for_context', return_value='key'), \
                patch('instagram_booking_flow.booking.slots_for_message',
                      return_value={'items': []}):
            with self.assertRaisesRegex(Exception, 'horário mudou'):
                ig._review_offer(RecentReply(), 77, self.message('1'), target)

    def test_confirm_is_persisted_only_after_validated_target_and_never_on_text_alone(self):
        output = shared.response('booking_review', 'Confirme o horário.',
            [shared.option('1', 'Confirmar', 'confirm', confirmation='signed-fixture'),
             *shared.navigation()], False)[1]
        text = ig.render(output, {'step': 'review'})
        row = {'status': 'confirmed', 'text': text, 'created_at': datetime.now(timezone.utc)}
        with patch('instagram_booking_flow.flow.advance',
                   return_value=shared.response('booking_confirmed', 'Confirmado.', [], False)) as advance:
            state, result, selected = ig.respond(RecentReply(row), 77, self.message('1'))
        self.assertEqual(selected['confirmation'], 'signed-fixture')
        self.assertEqual(result['action'], 'booking_confirmed')
        self.assertEqual(advance.call_args.kwargs['origin'], 'instagram')
        self.assertIsNone(ig.respond(RecentReply({**row, 'status': 'uncertain'}), 77, self.message('1')))

    def test_bounded_decoding_and_oversized_reply_fail_closed(self):
        self.assertEqual(ig._decode_reference('No booking reference'), [])
        self.assertEqual(ig._decode_reference(ig.MARKER + '!' * 100), [])
        with self.assertRaises(ValueError):
            ig.render({'text': 'A' * 999, 'choices': [shared.option(
                '1', 'Profissional', 'resources', service_id=1)]}, {'step': 'services'})

    def test_booking_errors_return_handoff_or_restart_without_provider_calls(self):
        from fastapi import HTTPException
        for status, detail, expected in [
            (409, 'Sem horários.', 'booking_unavailable'),
            (409, 'Nossa equipe precisa associar seu cadastro antes de confirmar um horário.', 'booking_handoff'),
            (503, 'Serviço indisponível.', 'booking_handoff'),
        ]:
            with self.subTest(status=status, detail=detail), \
                    patch('instagram_booking_flow.flow.advance',
                          side_effect=HTTPException(status, detail)):
                state, result, _ = ig.respond(RecentReply(), 1, self.message('6'))
            self.assertEqual(result['action'], expected)
            self.assertEqual(state, 'human' if expected == 'booking_handoff' else 'menu')


if __name__ == '__main__':
    unittest.main()
