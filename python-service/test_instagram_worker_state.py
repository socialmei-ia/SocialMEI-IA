from datetime import datetime, timezone
import unittest

from instagram_worker_state import reconcile


class WorkerStateTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 11, 21, tzinfo=timezone.utc)
        self.state = reconcile(None, 60, self.start, unresolved=False)

    def test_crash_before_job_or_after_durable_confirmation_can_resume(self):
        self.state['in_flight'] = True
        recovered = reconcile(self.state, 60, self.start, unresolved=False)
        self.assertFalse(recovered['in_flight'])
        self.assertEqual(recovered['recovered_after_restart'], 1)
        self.assertTrue(self.state['in_flight'])

    def test_dispatching_or_uncertain_job_always_blocks_restart(self):
        for state in (None, self.state, {**self.state, 'in_flight': True}):
            with self.assertRaisesRegex(RuntimeError, 'delivery requires reconciliation'):
                reconcile(state, 60, self.start, unresolved=True)

    def test_other_workspace_never_reuses_checkpoint(self):
        for workspace in (61, True):
            with self.assertRaises(RuntimeError):
                reconcile(self.state, workspace, self.start, unresolved=False)

    def test_paused_state_or_other_cutoff_requires_review(self):
        for changes in ({'status': 'paused'}, {'start': 'another-cutoff'}, {'confirmed': -1},
                        {'in_flight': 'false'}, {'workspace_id': True}):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                reconcile({**self.state, **changes}, 60, self.start, unresolved=False)

    def test_only_idle_legacy_checkpoint_can_be_adopted(self):
        del self.state['workspace_id']
        self.assertEqual(reconcile(self.state, 60, self.start, unresolved=False)['workspace_id'], 60)
        self.state['in_flight'] = True
        with self.assertRaises(RuntimeError):
            reconcile(self.state, 60, self.start, unresolved=False)


if __name__ == '__main__':
    unittest.main()
