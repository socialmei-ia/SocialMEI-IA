"""Release boundaries use synthetic metadata and never access Docker or providers."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'gows_catalog_source', Path(__file__).resolve().parents[1] / 'tools/gows_catalog_source.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class CatalogReleaseTests(unittest.TestCase):
    def test_registry_keeps_boundary_for_event_already_in_edge_spool(self):
        registry = {'version': 1, 'bindings': [{'engine': 'GOWS', 'ingress_after': 100}]}
        snapshot = source.catalog_registry_snapshot(registry)
        self.assertEqual(snapshot, registry)
        # Accepted at 110, cut at 120, delivered at 130: preserve eligibility.
        self.assertGreater(110, snapshot['bindings'][0]['ingress_after'])
        snapshot['bindings'][0]['ingress_after'] = 200
        self.assertEqual(registry['bindings'][0]['ingress_after'], 100)

    def test_registry_rejects_ambiguous_or_missing_cutoff(self):
        for bindings in [[], [{'engine': 'WEBJS', 'ingress_after': 100}],
                         [{'engine': 'GOWS'}], [{'engine': 'GOWS', 'ingress_after': True}]]:
            with self.subTest(bindings=bindings), self.assertRaises(ValueError):
                source.catalog_registry_snapshot({'bindings': bindings})

    def test_source_boundary_is_preserved_on_catalog_update(self):
        value = '2026-11-11T20:00:00+00:00'
        self.assertEqual(source.catalog_source_boundary({'SOCIALMEI_CONTINUOUS_START_UTC': value}), value)
        for raw in ['', 'invalid', '2026-11-11T20:00:00', None]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                source.catalog_source_boundary({'SOCIALMEI_CONTINUOUS_START_UTC': raw})

    def prepared(self):
        return {'images': {kind: 'candidate:' + kind for kind in ['api', 'menu', 'worker']},
                'image_ids': {kind: 'sha256:' + str(i) * 64
                              for i, kind in enumerate(['api', 'menu', 'worker'], 1)}}

    def test_candidate_pins_are_verified_and_used_as_immutable_ids(self):
        prepared = self.prepared()
        identities = {**prepared['image_ids'], **{
            tag: prepared['image_ids'][kind] for kind, tag in prepared['images'].items()}}
        identities.update({value: value for value in prepared['image_ids'].values()})
        result = source.verified_candidate_images(prepared, identities.__getitem__)
        self.assertEqual(result, prepared['image_ids'])
        self.assertTrue(all(value.startswith('sha256:') for value in result.values()))

    def test_retag_of_any_candidate_rejects_before_service_actions(self):
        for changed in ['api', 'menu', 'worker']:
            prepared = self.prepared()
            identities = {tag: prepared['image_ids'][kind] for kind, tag in prepared['images'].items()}
            identities.update({value: value for value in prepared['image_ids'].values()})
            identities[prepared['images'][changed]] = 'sha256:' + 'f' * 64
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'identity changed'):
                source.verified_candidate_images(prepared, identities.__getitem__)

    def test_legacy_preparation_without_image_ids_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'identities required'):
            source.verified_candidate_images({'images': self.prepared()['images']},
                                             lambda _: self.fail('No lookup before valid receipt'))
