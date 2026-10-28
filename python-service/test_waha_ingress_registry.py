"""Private registry fixtures only; no provider, production DB or network access."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from waha_ingress import WahaIngressService, waha_service


KEY = "private-test-only-hmac-key-never-production-123"


def registry(**changes):
    entry = {
        "instance": "trusted-a", "session": "default", "account_id": "111@c.us",
        "workspace_id": 1, "channel_id": 2, "hmac_key": KEY, "revision": 3,
    }
    entry.update(changes)
    return {"version": 1, "bindings": [entry]}


class WahaPrivateRegistryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "waha.private.json"
        self.write(registry())
        env = patch.dict(os.environ, {"SOCIALMEI_WAHA_REGISTRY_FILE": str(self.path)})
        env.start()
        self.addCleanup(env.stop)

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")
        self.path.chmod(0o600)

    def reject(self):
        with patch("waha_ingress.connect", side_effect=AssertionError("Unexpected DB")) as database:
            with self.assertRaises(HTTPException) as error:
                waha_service()
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(error.exception.detail, "Recepção WAHA ainda não configurada.")
        self.assertNotIn(KEY, str(error.exception))
        self.assertNotIn(str(self.path), str(error.exception))
        database.assert_not_called()

    def test_private_file_installs_exact_bindings_without_database_or_provider_io(self):
        with patch("waha_ingress.connect", side_effect=AssertionError("Unexpected DB")) as database:
            service = waha_service()
        self.assertIsInstance(service, WahaIngressService)
        entry = service.registry["trusted-a"]
        self.assertEqual((entry.workspace_id, entry.channel_id, entry.revision), (1, 2, 3))
        self.assertEqual(entry.account_id, "111@c.us")
        self.assertNotIn(KEY, repr(entry))
        self.assertNotIn("111@c.us", repr(entry))
        database.assert_not_called()

    def test_read_only_permissions_work_and_replacement_is_not_cached(self):
        self.path.chmod(0o400)
        self.assertEqual(waha_service().registry["trusted-a"].revision, 3)
        replacement = self.path.with_suffix(".new")
        replacement.write_text(json.dumps(registry(revision=4)), encoding="utf-8")
        replacement.chmod(0o400)
        replacement.replace(self.path)
        self.assertEqual(waha_service().registry["trusted-a"].revision, 4)

    def test_missing_relative_directory_symlink_and_public_files_fail_closed(self):
        for location in ("", "relative.json", str(self.path.parent), str(self.path) + ".missing"):
            with self.subTest(location=location), patch.dict(os.environ, {"SOCIALMEI_WAHA_REGISTRY_FILE": location}):
                self.reject()
        link = self.path.with_suffix(".link")
        link.symlink_to(self.path)
        with patch.dict(os.environ, {"SOCIALMEI_WAHA_REGISTRY_FILE": str(link)}):
            self.reject()
        for mode in (0o644, 0o640, 0o660, 0o700):
            self.path.chmod(mode)
            self.reject()

    def test_fifo_and_foreign_owner_rejected(self):
        fifo = self.path.with_suffix(".fifo")
        os.mkfifo(fifo, 0o600)
        with patch.dict(os.environ, {"SOCIALMEI_WAHA_REGISTRY_FILE": str(fifo)}):
            self.reject()
        if os.geteuid() == 0:
            os.chown(self.path, 65534, 65534)
            self.reject()

    def test_invalid_schema_duplicate_keys_bad_binding_and_collisions_are_private(self):
        values = [
            {}, [], {"version": True, "bindings": []}, {"version": 2, "bindings": []},
            {"version": 1, "bindings": []}, {"version": 1, "bindings": "wrong"},
            {**registry(), "token": KEY}, registry(workspace_id=True),
            registry(channel_id=0), registry(hmac_key="short"), registry(revision=0),
            registry(secret=KEY), {"version": 1, "bindings": [registry()["bindings"][0]] * 2},
            {"version": 1, "bindings": [registry()["bindings"][0]] * 101},
            {"version": 1, "bindings": [{"instance": "missing-fields"}]},
        ]
        for value in values:
            with self.subTest(value_type=type(value).__name__):
                self.write(value)
                self.reject()
        for raw in (
            '{"version":1,"version":1,"bindings":[]}',
            '{"version":1,"bindings":[{"hmac_key":"' + KEY + '","hmac_key":"duplicate"}]}',
            '{"version":NaN,"bindings":[]}', "[" * 2000, "not-json", "x" * 65537,
        ):
            self.path.write_text(raw)
            self.reject()

    def test_distinct_aliases_cannot_share_accounts_channels_or_hmacs(self):
        first = registry()["bindings"][0]
        second = {
            **first, "instance": "trusted-b", "account_id": "333@c.us",
            "channel_id": 4, "hmac_key": KEY + "-other",
        }
        self.write({"version": 1, "bindings": [first, second]})
        self.assertEqual(set(waha_service().registry), {"trusted-a", "trusted-b"})
        for field in ("account_id", "channel_id", "hmac_key"):
            with self.subTest(field=field):
                self.write({"version": 1, "bindings": [first, {**second, field: first[field]}]})
                self.reject()

    def test_valid_service_still_revalidates_live_channel_revision(self):
        service = waha_service()
        from unittest.mock import Mock
        database = Mock()
        database.execute.return_value.fetchone.return_value = None
        with self.assertRaises(HTTPException) as error:
            service._channel(database, service.registry["trusted-a"])
        self.assertEqual(error.exception.status_code, 404)
        sql, parameters = database.execute.call_args.args
        self.assertIn("NOT envio_habilitado", sql)
        self.assertIn("versao=%s", sql)
        self.assertEqual(parameters, (1, 2, "trusted-a", "default", "111@c.us", 3))


if __name__ == "__main__":
    unittest.main()
