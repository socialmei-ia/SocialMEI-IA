"""Synthetic candidates; no provider or production database access."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock


class RefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('refresh', Path(__file__).resolve().parents[1] / 'tools/team-whatsapp-contact-refresh.py')
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def test_dry_run_does_not_resolve_or_write_and_honors_backoff(self):
        resolve = Mock()
        state = {'2': {'failures': 1, 'retry_at': 1200}}
        result, after = self.m.refresh([1, 2, 3], state, 1000, 3, False, resolve)
        self.assertEqual(result['eligible'], 2)
        self.assertEqual(result['attempted'], 0)
        self.assertEqual(after, state)
        resolve.assert_not_called()

    def test_bounded_attempts_failure_backoff_and_no_identifiers_in_output(self):
        resolve = Mock(side_effect=[RuntimeError('private provider body'), {'action': 'verified_contact_number_displayed'}])
        result, state = self.m.refresh([1, 2, 3], {}, 1000, 2, True, resolve)
        self.assertEqual(resolve.call_count, 2)
        self.assertEqual(result['identified'], 1)
        self.assertEqual(result['deferred'], 1)
        self.assertEqual(state, {'1': {'failures': 1, 'retry_at': 1300}})
        self.assertNotIn('private', str(result))

    def test_backoff_is_capped_and_stale_state_is_removed(self):
        state = {'1': {'failures': 99, 'retry_at': 0}, '9': {'failures': 1, 'retry_at': 0}}
        result, state = self.m.refresh([1], state, 1000, 1, True, Mock(side_effect=RuntimeError()))
        self.assertEqual(state, {'1': {'failures': 100, 'retry_at': 87400}})

    def test_rejects_malformed_state_candidates_and_limits(self):
        for candidates, state, limit in [([True], {}, 1), ([1, 1], {}, 1), ([1], {}, 4),
                                         ([1], {'1': {'failures': -1, 'retry_at': 0}}, 1),
                                         ([1], {'1': {'failures': 1, 'retry_at': 'secret'}}, 1)]:
            with self.subTest(candidates=candidates, state=state, limit=limit), self.assertRaises(ValueError):
                self.m.refresh(candidates, state, 1000, limit, True, Mock())
