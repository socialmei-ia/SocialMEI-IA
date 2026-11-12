import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import FastAPI, HTTPException


class BoundSessionTests(unittest.TestCase):
    def module(self, configured='bound-session', actual='bound-session'):
        @contextmanager
        def database():
            class Connection:
                def execute(self, *args): return self
                def fetchall(self): return []
            yield Connection()
        original = types.SimpleNamespace(app=FastAPI(), require_bot=lambda: None,
            operation_database=database, authorize=lambda c, r: dict(workspace_id=1,
            channel_id=1, instancia='socialmei-equipe-piloto', sessao=actual,
            identificador_conta='123@c.us'))
        settings = types.SimpleNamespace(whatsapp_bot_allowed_contacts=lambda: None)
        spec = importlib.util.spec_from_file_location('bound_session_gate',
            Path(__file__).resolve().parents[1] / 'tools/whatsapp-public-continuous.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'settings': settings, 'public_app': original}), patch.dict(os.environ,
            SOCIALMEI_MENU_PUBLIC_INBOUND_ACTIVE='YES', SOCIALMEI_MENU_SESSION=configured,
            SOCIALMEI_CONTINUOUS_START_UTC='2026-01-01T00:00:00+00:00'):
            spec.loader.exec_module(module)
        return module

    def test_matching_configured_session_reads_only_new_sources(self):
        self.assertEqual(self.module().sources(None), {'sources': []})

    def test_other_session_cannot_supply_sources(self):
        with self.assertRaises(HTTPException) as error:
            self.module(actual='other-session').sources(None)
        self.assertEqual(error.exception.status_code, 403)

    def test_invalid_configured_session_fails_at_startup(self):
        with self.assertRaises(RuntimeError): self.module(configured='../other')
