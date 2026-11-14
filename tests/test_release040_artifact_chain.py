"""Directed proof-rejection tests only; no Docker, database, migration or restore."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


chain = load('chain_tests', 'release040-artifact-chain.py')
gate = load('chain_gate_tests', 'release040-preflight.py')


def proof():
    return json.loads((ROOT / 'docs/evidence/20261114-release040-artifact-chain.json').read_text())


def manifest():
    return json.loads((ROOT / 'deploy/team/release040-artifact-sources.json').read_text())


def historical():
    return json.loads((ROOT / 'docs/evidence/20261113-mission3-schema040-rehearsal.json').read_text())


class ChainTests(unittest.TestCase):
    def verify(self, receipt):
        return chain.validate(receipt, manifest(), historical(), gate.profile)

    def test_actual_new_chain_uses_historical_schema_proof_without_relabeling_it(self):
        self.assertTrue(self.verify(proof()))
        self.assertEqual(historical()['source_sha'], chain.BASE_SOURCE)
        self.assertNotEqual(historical()['api_image_id'], chain.IMAGES['api'])

    def test_missing_guard_wrong_ids_or_false_environment_claims_fail_closed(self):
        changes = [lambda p: p['images'].update(api='sha256:' + 'f' * 64),
                   lambda p: p.update(source_sha=chain.BASE_SOURCE),
                   lambda p: p.update(runner_sha256='f' * 64),
                   lambda p: p.update(historical_migration_receipt_sha256='f' * 64),
                   lambda p: p.update(mail_fixture_count=0),
                   lambda p: p.update(schema_evidence_scope='new_migration_rehearsal'),
                   lambda p: p.update(migrations_executed=True),
                   lambda p: p.update(restores_executed=True),
                   lambda p: p.update(production_ready=True),
                   lambda p: p['checks'].update(pending_email_guard_verified=False)]
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                receipt = proof(); change(receipt)
                with self.assertRaises(ValueError): self.verify(receipt)

    def test_full_file_sets_detect_missing_worker_extra_stale_module_and_modified_code(self):
        for role in chain.IMAGES:
            with self.subTest(role=role):
                receipt = proof(); receipt['audits'][role]['files']['/extra-stale-code.py'] = 'a' * 64
                with self.assertRaises(ValueError): self.verify(receipt)
        receipt = proof(); receipt['audits']['api']['files'].pop('/app/instagram-auto-menu-worker.py')
        with self.assertRaises(ValueError): self.verify(receipt)
        receipt = proof(); receipt['audits']['fallback']['files']['/app/account_auth.py'] = 'b' * 64
        with self.assertRaises(ValueError): self.verify(receipt)

    def test_manifest_or_commands_cannot_be_forged_together_with_receipt(self):
        altered = manifest(); altered['files']['api'].clear()
        receipt = proof(); receipt['source_manifest_sha256'] = chain.digest(altered)
        with self.assertRaises(ValueError): chain.validate(receipt, altered, historical(), gate.profile)
        for field, value in [('command', ['python', 'unknown.py']), ('entrypoint', ['unknown']),
                             ('sensitive_env_keys', ['DATABASE_URL']), ('source', chain.B2)]:
            with self.subTest(field=field):
                receipt = proof(); receipt['audits']['api'][field] = value
                with self.assertRaises(ValueError): self.verify(receipt)

    def test_additive_preflight_passes_new_images_and_preserves_legacy_rejection(self):
        import sys
        sys.path.insert(0, str(ROOT / 'tests'))
        from test_release040_preflight import inputs
        model, images, _, _, rollback = inputs()
        for role in ('api', 'gateway'):
            images[role]['Id'] = chain.IMAGES[role]
            images[role]['Config']['Labels']['org.opencontainers.image.revision'] = chain.SOURCE
        for name in ('team-api', *gate.WORKERS): model['services'][name]['image'] = chain.IMAGES['api']
        model['services']['team-gateway']['image'] = chain.IMAGES['gateway']
        rollback.update(candidate_source_sha=chain.BASE_SOURCE, candidate_image_id=historical()['api_image_id'])
        result = gate.validate(model, images, chain.SOURCE, historical(), rollback,
                               artifact_chain=proof(), source_manifest=manifest())
        self.assertTrue(result['artifact_checks_passed'])
        self.assertTrue(result['artifact_chain_verified'])
        self.assertFalse(result['production_ready'])
        self.assertEqual(result['fallback_image_id'], chain.IMAGES['fallback'])
        with self.assertRaises(RuntimeError):
            gate.validate(model, images, chain.SOURCE, historical(), rollback)


if __name__ == '__main__': unittest.main()
