import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('worker_db', Path(__file__).resolve().parents[1] / 'tools/instagram-worker-database.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class WorkerDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.api = {'Name': '/' + m.API, 'Config': {'Env': [
            'POSTGRES_HOST=' + m.HOST, 'POSTGRES_DB=' + m.DATABASE,
            'POSTGRES_USER=synthetic', 'POSTGRES_PASSWORD=private-sentinel']}}
        self.worker = {'Name': '/' + m.WORKER, 'Config': {'Env': [
            'DATABASE_URL=postgresql://synthetic@db.prisma.io/postgres',
            'POSTGRES_DB=historical', 'SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED=true',
            'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=true', 'PRIVATE_OAUTH=preserved']}}

    def test_old_prisma_override_is_removed_and_sender_remains_disabled(self):
        before = copy.deepcopy((self.api, self.worker))
        result = m.candidate(self.api, self.worker, 60)
        self.assertNotIn('DATABASE_URL', result)
        self.assertEqual(result['POSTGRES_DB'], m.DATABASE)
        self.assertEqual(result['POSTGRES_PASSWORD'], 'private-sentinel')
        self.assertEqual(result['PRIVATE_OAUTH'], 'preserved')
        self.assertEqual(result['SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED'], 'false')
        self.assertEqual(result['SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED'], 'false')
        self.assertEqual((self.api, self.worker), before)

    def test_explicit_api_url_is_preserved_exactly_with_encoded_credentials(self):
        url = 'postgresql://synthetic:p%40ss@' + m.HOST + '/' + m.DATABASE
        self.api['Config']['Env'] = ['DATABASE_URL=' + url]
        self.assertEqual(m.candidate(self.api, self.worker, 61)['DATABASE_URL'], url)

    def test_each_workspace_has_independent_worker_scope(self):
        for workspace in (60, 61):
            result = m.candidate(self.api, self.worker, workspace)
            self.assertEqual(result['SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES'], str(workspace))
            self.assertEqual(result['SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID'], str(workspace))
        for invalid in (1, True, '60'):
            with self.assertRaises(RuntimeError):
                m.candidate(self.api, self.worker, invalid)

    def test_unknown_api_database_or_duplicate_key_fails_closed(self):
        for value in ('postgresql://synthetic@db.prisma.io/postgres',
                      'postgresql://synthetic@' + m.HOST + '/historical'):
            self.api['Config']['Env'] = ['DATABASE_URL=' + value]
            with self.assertRaises(RuntimeError):
                m.candidate(self.api, self.worker, 60)
        self.api['Config']['Env'] = ['DATABASE_URL=a', 'DATABASE_URL=b']
        with self.assertRaises(RuntimeError):
            m.candidate(self.api, self.worker, 60)


if __name__ == '__main__':
    unittest.main()
