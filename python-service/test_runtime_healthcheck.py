import json
from pathlib import Path
import tempfile
import unittest

from runtime_healthcheck import check


class RuntimeHealthcheckTests(unittest.TestCase):
    def test_liveness_is_fresh_but_readiness_is_periodic(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "health.json"
            calls = []

            def request(path, **kwargs):
                calls.append(path)
                return True

            for now in (0, 15, 30, 45, 60):
                self.assertTrue(check(state_file=state, clock=lambda: now, request=request))
            self.assertEqual(calls.count("/health"), 5)
            self.assertEqual(calls.count("/health/db"), 2)

    def test_failed_readiness_is_not_hidden_and_can_recover(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "health.json"
            available = False

            def request(path, **kwargs):
                if path == "/health/db" and not available:
                    raise OSError("private connection error")
                return True

            self.assertFalse(check(state_file=state, clock=lambda: 0, request=request))
            self.assertNotIn("private", state.read_text())
            available = True
            self.assertFalse(check(state_file=state, clock=lambda: 15, request=request))
            self.assertTrue(check(state_file=state, clock=lambda: 60, request=request))

    def test_cached_readiness_never_hides_liveness_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "health.json"
            state.write_text(json.dumps({"checked_at": 0, "healthy": True}))
            self.assertFalse(check(state_file=state, clock=lambda: 15, request=lambda *a: False))

    def test_corrupt_or_future_state_rechecks_readiness(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "health.json"
            for value in ("bad", '{"checked_at":999,"healthy":true}', '{}'):
                state.write_text(value)
                calls = []

                def request(path, **kwargs):
                    calls.append(path)
                    return True

                self.assertTrue(check(state_file=state, clock=lambda: 1, request=request))
                self.assertIn("/health/db", calls)
