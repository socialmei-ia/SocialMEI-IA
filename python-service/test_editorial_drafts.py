import base64
import io
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
from PIL import Image
import test_account_auth as accounts


@unittest.skipUnless(accounts.DB, "Disposable PostgreSQL required")
class EditorialDraftTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    register = accounts.AccountDatabaseTests.register
    invited = accounts.AccountDatabaseTests.invited

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)

    def test_library_revisions_duplicate_archive_and_permissions(self):
        base = "/api/v1/instagram/publishing/drafts"
        draft = f"{base}/{uuid4()}"
        request = {"operation_id": str(uuid4()), "expected_revision": 0,
                   "document": {"f": "feed", "titulo": "Agenda de junho", "leg": "Guarde o horário."}}
        def save(_):
            return self.admin_client.put(draft, json=request)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, duplicate = list(pool.map(save, range(2)))
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), duplicate.json())
        self.assertEqual(len(self.admin_client.get(base).json()["items"]), 1)
        document = {**request["document"], "leg": "Horários revisados."}
        updated = self.admin_client.put(draft, json={
            **request, "operation_id": str(uuid4()), "expected_revision": 1, "document": document,
        })
        self.assertEqual(updated.json()["revision"], 2)
        self.assertEqual(self.admin_client.put(draft, json={
            **request, "operation_id": str(uuid4()), "expected_revision": 1,
        }).status_code, 409)
        copy = f"{base}/{uuid4()}"
        self.assertEqual(self.admin_client.put(copy, json={
            **request, "operation_id": str(uuid4()), "document": document,
        }).status_code, 200)
        self.assertEqual(self.admin_client.put(draft, json={
            **request, "operation_id": str(uuid4()), "expected_revision": 2,
            "document": document, "archived": True,
        }).status_code, 200)
        self.assertEqual(len(self.admin_client.get(base).json()["items"]), 1)
        other = self.register("editorial-draft-other@example.test")
        self.assertEqual(other.get(base).json()["items"], [])
        self.assertEqual(other.put(copy, json={**request, "expected_revision": 1}).status_code, 409)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='viewer' WHERE user_id=%s", (self.admin_id,))
        self.assertEqual(self.admin_client.get(base).status_code, 200)
        self.assertEqual(self.admin_client.put(copy, json=request).status_code, 403)

    def test_private_photo_is_reusable_and_tenant_scoped(self):
        base = "/api/v1/instagram/publishing"
        buffer = io.BytesIO()
        Image.new("RGB", (16, 28), "navy").save(buffer, format="PNG")
        payload = {"image_base64": base64.b64encode(buffer.getvalue()).decode()}
        create = self.admin_client.post(base + "/draft-assets", json=payload)
        self.assertEqual(create.status_code, 200, create.text)
        asset = create.json()["id"]
        self.assertEqual(self.admin_client.post(base + "/draft-assets", json=payload).json()["id"], asset)
        path = base + "/draft-assets/" + asset
        renewed = self.login("admin@example.com")
        restored = renewed.get(path)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.headers["Cache-Control"], "no-store")
        self.assertTrue(base64.b64decode(restored.json()["image_base64"]).startswith(b"\xff\xd8"))
        self.assertEqual(len(renewed.get(base + "/draft-assets").json()["items"]), 1)
        write = {"operation_id": str(uuid4()), "expected_revision": 0,
                 "document": {"f": "story", "titulo": "Foto", "image_id": asset, "image_x": 37}}
        draft = base + "/drafts/" + str(uuid4())
        saved = renewed.put(draft, json=write)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(renewed.get(base + "/drafts").json()["items"][0]["document"]["image_x"], 37)
        self.assertEqual(self.admin_client.post(base + "/draft-assets", json={"image_base64": "aGVsbG8="}).status_code, 422)
        other = self.register("private-asset-other@example.test")
        self.assertEqual(other.get(path).status_code, 404)
        self.assertEqual(other.get(base + "/draft-assets").json()["items"], [])
        self.assertEqual(other.put(draft, json=write).status_code, 404)
