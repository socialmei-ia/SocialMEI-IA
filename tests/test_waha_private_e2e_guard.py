"""The browser fixture must refuse production-looking targets before any DB/file I/O."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python-service'))
spec = importlib.util.spec_from_file_location('waha_private_e2e', ROOT / 'tests/fixtures/waha-private-e2e.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
ENV = {'SOCIALMEI_LOCAL_FIXTURE_KIND': 'wa-inbox-e2e', 'POSTGRES_DB': 'socialmei_wa_inbox_e2e',
       'POSTGRES_HOST': 'database', 'POSTGRES_USER': 'preview'}


class FixtureGuardTests(unittest.TestCase):
    def test_wrong_target_or_unprivileged_process_never_reaches_database(self):
        for key in ENV:
            with self.subTest(key=key), patch.dict(fixture.os.environ, {**ENV, key:'production'}, clear=True), patch.object(fixture.os, 'geteuid', return_value=0, create=True), patch.object(fixture, 'connect') as connect:
                with self.assertRaises(ValueError):
                    fixture.guard()
                connect.assert_not_called()
        with patch.dict(fixture.os.environ, ENV, clear=True), patch.object(fixture.os, 'geteuid', return_value=1000, create=True), patch.object(fixture, 'connect') as connect:
            with self.assertRaises(ValueError):
                fixture.guard()
            connect.assert_not_called()

    def test_actual_database_identity_is_checked_with_read_only_query(self):
        for actual in ('socialmei_team', 'socialmei_wa_inbox_e2e'):
            connection = MagicMock()
            connection.__enter__.return_value.execute.return_value.fetchone.return_value = (actual,)
            with self.subTest(actual=actual), patch.dict(fixture.os.environ, ENV, clear=True), patch.object(fixture.os, 'geteuid', return_value=0, create=True), patch.object(fixture, 'connect', return_value=connection):
                if actual == ENV['POSTGRES_DB']:
                    fixture.guard()
                else:
                    with self.assertRaises(ValueError):
                        fixture.guard()
                connection.__enter__.return_value.execute.assert_called_once_with('SELECT current_database()')

    def test_invalid_workspace_selection_never_reaches_database(self):
        for value in (None, [], [1], [1,1], [True,2], [0,2]):
            with self.subTest(value=value), patch.object(fixture, 'connect') as connect:
                with self.assertRaises(ValueError):
                    fixture.setup(value)
                connect.assert_not_called()
