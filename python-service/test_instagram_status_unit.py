"""Status authorization uses the same row format as the OAuth service."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from psycopg.rows import dict_row
import instagram_publishing as publishing

class StatusTests(unittest.TestCase):
    def test_authenticated_owner_gets_disabled_status_without_tuple_error(self):
        class Connection:
            row_factory=None
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,sql,params):
                if 'SELECT m.role' in sql:
                    value={'role':'owner'} if self.row_factory is dict_row else ('owner',)
                else:value=None
                return SimpleNamespace(fetchone=lambda:value)
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(instagram_runtime=None)))
        with patch.object(publishing,'actor',return_value=({'id':1,'workspace_id':2},'a'*64)), patch.object(publishing,'connect',return_value=Connection()), patch.object(publishing,'permitted',return_value=False):
            self.assertEqual(publishing.status(request),{'available':False,'connected':False,'format':'local_image_or_public_url','upload_available':False})
