"""Planning extends commercial opportunities without changing closing notes."""

import unittest
from uuid import uuid4
from decimal import Decimal
from opportunities import Create, Edit, Close, PlanningImport


class ContractTests(unittest.TestCase):
    def test_money_dates_unicode_and_closing_note_are_separate(self):
        base = dict(operation_id=uuid4(), client_id=1, title="Interest")
        self.assertEqual(
            Create(**base, estimated_amount="1000000000.00").estimated_amount,
            Decimal("1000000000.00"),
        )
        self.assertEqual(
            Create(**base, planning_note="😀" * 70).planning_note, "😀" * 70
        )
        for fields in (
            {"estimated_amount": "1.001"},
            {"estimated_amount": "NaN"},
            {"estimated_amount": "1000000000.01"},
            {"follow_up_date": "2026-02-30"},
            *[
                {"follow_up_date": value}
                for value in (
                    0,
                    86400,
                    "2026-01-01T00:00:00Z",
                    "20260101",
                    "2026-W01-1",
                )
            ],
            {"planning_note": "bad\x00text"},
            {"planning_note": "😀" * 71},
            {"planning_note": "bad\ud800"},
            {"contacted": 1},
        ):
            with self.subTest(fields=repr(fields)), self.assertRaises(ValueError):
                Create(**base, **fields)
        self.assertEqual(
            len(
                Close(
                    operation_id=uuid4(),
                    expected_revision=1,
                    outcome="lost",
                    reason="other",
                    note="x" * 1000,
                ).note
            ),
            1000,
        )
        self.assertEqual(
            Edit(
                operation_id=uuid4(), expected_revision=1, planning_note="  note  "
            ).planning_note,
            "  note  ",
        )

    def test_legacy_import_never_rounds_or_truncates(self):
        data = dict(
            operation_id=uuid4(),
            expected_revision=1,
            legacy=dict(
                amount=1.23,
                date="",
                note="note",
                contacted=False,
                updatedAt=1,
                events=[],
            ),
        )
        self.assertEqual(PlanningImport(**data).legacy.amount, Decimal("1.23"))
        for legacy in (
            {"amount": 1.234},
            {"note": "😀" * 71},
            {"date": "2026-02-30"},
            {"events": [{"t": 1, "s": "x"}] * 21},
        ):
            with self.assertRaises(ValueError):
                PlanningImport(**{**data, "legacy": {**data["legacy"], **legacy}})


import psycopg
from unittest.mock import patch
from uuid import UUID
from opportunities import mutate
import test_opportunities as base


@unittest.skipUnless(base.DB, "Disposable PostgreSQL not configured")
class DatabaseTests(unittest.TestCase):
    setUpClass = classmethod(base.DatabaseTests.setUpClass.__func__)
    setUp = base.DatabaseTests.setUp
    tearDown = base.DatabaseTests.tearDown

    def create(self, **fields):
        return mutate(
            "create",
            Create(
                operation_id=uuid4(),
                client_id=self.clients[0],
                title="Planning",
                **fields
            ),
        )

    def test_atomic_create_planning_and_close_note_remain_independent(self):
        row = self.create(
            estimated_amount="12.34",
            planning_note="😀" * 70,
            follow_up_date="2028-02-29",
            contacted=True,
        )
        self.assertTrue(row["planning_initialized"])
        self.assertEqual(row["estimated_amount"], 12.34)
        self.assertEqual(row["follow_up_date"], "2028-02-29")
        closed = mutate(
            "close",
            Close(
                operation_id=uuid4(),
                expected_revision=1,
                outcome="lost",
                reason="other",
                note="x" * 1000,
            ),
            UUID(row["id"]),
        )
        self.assertEqual(closed["planning_note"], "😀" * 70)
        changed = mutate(
            "edit",
            Edit(operation_id=uuid4(), expected_revision=2, planning_note="note"),
            UUID(row["id"]),
        )
        self.assertEqual(changed["outcome_note"], "x" * 1000)
        self.assertEqual(changed["planning_note"], "note")
        with psycopg.connect(base.DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.crm_opportunity_events WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                3,
            )

    def test_legacy_import_cas_replay_and_no_overwrite_after_explicit_zero(self):
        row = self.create()
        self.assertFalse(row["planning_initialized"])
        payload = PlanningImport(
            operation_id=uuid4(),
            expected_revision=1,
            legacy={
                "amount": "0",
                "date": "",
                "note": "",
                "contacted": False,
                "updatedAt": 10,
                "events": [{"t": 1, "s": "untrusted client history"}],
            },
        )
        imported = mutate("import_planning", payload, UUID(row["id"]))
        self.assertTrue(imported["planning_initialized"])
        self.assertEqual(
            mutate("import_planning", payload, UUID(row["id"]))["revision"], 2
        )
        with self.assertRaises(base.HTTPException) as error:
            mutate(
                "import_planning",
                payload.model_copy(
                    update={"operation_id": uuid4(), "expected_revision": 2}
                ),
                UUID(row["id"]),
            )
        self.assertEqual(error.exception.status_code, 409)
        with psycopg.connect(base.DB) as conn:
            events = conn.execute(
                "SELECT action,reason,current FROM socialmei.crm_opportunity_events WHERE workspace_id=%s ORDER BY id",
                (self.identity["workspace_id"],),
            ).fetchall()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1][0:2], ("edit", "planning_import"))
        self.assertEqual(
            events[-1][2]["legacy_planning"]["events"][0]["s"],
            "untrusted client history",
        )
        zero = self.create(estimated_amount="0")
        with self.assertRaises(base.HTTPException):
            mutate(
                "import_planning",
                payload.model_copy(update={"operation_id": uuid4()}),
                UUID(zero["id"]),
            )

    def test_normal_planning_write_blocks_stale_import_and_preserves_empty_values(self):
        row = self.create()
        changed = mutate(
            "edit",
            Edit(
                operation_id=uuid4(),
                expected_revision=1,
                planning_note="",
                follow_up_date=None,
                contacted=False,
                estimated_amount="0",
            ),
            UUID(row["id"]),
        )
        self.assertTrue(changed["planning_initialized"])
        payload = PlanningImport(
            operation_id=uuid4(),
            expected_revision=1,
            legacy={
                "amount": 1,
                "date": "",
                "note": "legacy",
                "contacted": False,
                "updatedAt": 0,
                "events": [],
            },
        )
        with self.assertRaises(base.HTTPException):
            mutate("import_planning", payload, UUID(row["id"]))
        self.assertEqual(changed["planning_note"], "")

    def test_planning_tenants_viewer_and_operation_conflicts(self):
        row = self.create()
        self.identity = self.users[1]
        with self.assertRaises(base.HTTPException) as error:
            mutate(
                "edit",
                Edit(
                    operation_id=uuid4(), expected_revision=1, planning_note="foreign"
                ),
                UUID(row["id"]),
            )
        self.assertEqual(error.exception.status_code, 404)
        self.identity = {**self.users[0], "role": "viewer"}
        with self.assertRaises(base.HTTPException) as error:
            mutate(
                "edit",
                Edit(operation_id=uuid4(), expected_revision=1, planning_note="viewer"),
                UUID(row["id"]),
            )
        self.assertEqual(error.exception.status_code, 403)
        self.identity = self.users[0]
        operation = uuid4()
        mutate(
            "edit",
            Edit(operation_id=operation, expected_revision=1, estimated_amount="1.23"),
            UUID(row["id"]),
        )
        with self.assertRaises(base.HTTPException):
            mutate(
                "edit",
                Edit(
                    operation_id=operation, expected_revision=1, estimated_amount="1.24"
                ),
                UUID(row["id"]),
            )

    def test_database_unicode_note_limit_and_import_transaction_rollback(self):
        row = self.create()
        with psycopg.connect(base.DB) as conn:
            with self.assertRaises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute(
                        "UPDATE socialmei.crm_opportunities SET planning_note=%s WHERE workspace_id=%s AND id=%s",
                        ("😀" * 71, self.identity["workspace_id"], row["id"]),
                    )
        payload = PlanningImport(
            operation_id=uuid4(),
            expected_revision=1,
            legacy={
                "amount": "1.23",
                "date": "",
                "note": "note",
                "contacted": False,
                "updatedAt": 0,
                "events": [],
            },
        )
        from opportunities import record

        original = record

        def fail_after_update(cur, workspace, oid):
            result = original(cur, workspace, oid)
            if result["revision"] > 1:
                raise RuntimeError("fixture rollback")
            return result

        with patch(
            "opportunities.record", side_effect=fail_after_update
        ), self.assertRaises(RuntimeError):
            mutate("import_planning", payload, UUID(row["id"]))
        with psycopg.connect(base.DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT revision,planning_initialized FROM socialmei.crm_opportunities WHERE workspace_id=%s AND id=%s",
                    (self.identity["workspace_id"], row["id"]),
                ).fetchone(),
                (1, False),
            )
        self.assertEqual(
            mutate("import_planning", payload, UUID(row["id"]))["revision"], 2
        )

    def test_operation_presence_is_semantic_and_old_fingerprint_replays(self):
        import hashlib, json

        operation = uuid4()
        plain = Create(operation_id=operation, client_id=self.clients[0], title="old")
        row = mutate("create", plain)
        with self.assertRaises(base.HTTPException):
            mutate(
                "create",
                Create(
                    operation_id=operation,
                    client_id=self.clients[0],
                    title="old",
                    contacted=False,
                ),
            )
        edit_op = uuid4()
        mutate(
            "edit",
            Edit(operation_id=edit_op, expected_revision=1, planning_note="note"),
            UUID(row["id"]),
        )
        with self.assertRaises(base.HTTPException):
            mutate(
                "edit",
                Edit(
                    operation_id=edit_op,
                    expected_revision=1,
                    planning_note="note",
                    estimated_amount=0,
                ),
                UUID(row["id"]),
            )
        old_payload = {
            "operation_id": str(operation),
            "client_id": self.clients[0],
            "title": "old",
            "interest_level": "unknown",
        }
        old_fp = hashlib.sha256(
            json.dumps(
                {"action": "create", "id": "None", "payload": old_payload},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        with psycopg.connect(base.DB) as conn:
            actual = conn.execute(
                "SELECT fingerprint FROM socialmei.crm_opportunity_operations WHERE workspace_id=%s AND operation_id=%s",
                (self.identity["workspace_id"], operation),
            ).fetchone()[0]
        self.assertEqual(actual, old_fp)
        self.assertEqual(mutate("create", plain)["id"], row["id"])

    def test_concurrent_distinct_imports_have_one_winner_and_one_server_audit(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading

        row = self.create()
        gate = threading.Barrier(2)

        def apply(number):
            payload = PlanningImport(
                operation_id=uuid4(),
                expected_revision=1,
                legacy={
                    "amount": number,
                    "date": "",
                    "note": "candidate " + str(number),
                    "contacted": False,
                    "updatedAt": number,
                    "events": [],
                },
            )
            gate.wait(5)
            try:
                return ("success", mutate("import_planning", payload, UUID(row["id"])))
            except base.HTTPException as error:
                return ("error", error.status_code)

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(apply, (1, 2)))
        self.assertEqual(sorted(status for status, _ in results), ["error", "success"])
        self.assertEqual(
            next(value for status, value in results if status == "error"), 409
        )
        winner = next(value for status, value in results if status == "success")
        self.assertEqual(winner["revision"], 2)
        with psycopg.connect(base.DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.crm_opportunity_events WHERE workspace_id=%s AND opportunity_id=%s AND action='edit' AND reason='planning_import'",
                    (self.identity["workspace_id"], row["id"]),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.crm_opportunity_operations WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                2,
            )
