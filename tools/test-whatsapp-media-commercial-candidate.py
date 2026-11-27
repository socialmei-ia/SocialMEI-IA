"""Run inside the API candidate after the signed media menu lab, with no network egress."""
import json
import os
import unittest

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from provider_sentiment import router


class CommercialMediaTests(unittest.TestCase):
    def test_only_normalized_media_evidence_is_leased_to_the_existing_queue(self):
        db = os.environ['DATABASE_URL']
        self.assertTrue(db.endswith('/media_candidate_test'))
        key = 'synthetic-commercial-key-valid-only-in-the-isolated-lab'
        os.environ.update({
            'SOCIALMEI_AUTH_ENABLED': 'true',
            'SOCIALMEI_SHARED_DATA_ENABLED': 'true',
            'SOCIALMEI_PROVIDER_SENTIMENT_ENABLED': 'true',
            'SOCIALMEI_PROVIDER_SENTIMENT_KEY': key,
            'SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS': '60',
        })
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, headers={'Authorization': 'Bearer ' + key})
        path = '/internal/message-enrichment/provider'
        self.assertEqual(client.post(path+'/claims').json()['items'], [])
        os.environ['SOCIALMEI_WHATSAPP_MEDIA_COMMERCIAL_ENABLED'] = 'YES'
        os.environ['SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS'] = '61'
        self.assertEqual(client.post(path+'/claims').json()['items'], [])
        os.environ['SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS'] = '60'
        response = client.post(path+'/claims')
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertFalse(data['send_enabled'])
        self.assertEqual(len(data['items']), 2)
        by_text = {item['text']: item for item in data['items']}
        self.assertEqual(set(by_text), {
            'Quero consultar o catálogo, os preços ou a disponibilidade de produtos.',
            'Quero consultar opções de agendamento.',
        })
        self.assertNotIn('Produto sintético', json.dumps(data, ensure_ascii=False))
        self.assertEqual(client.post(path+'/claims').json()['items'], [])
        for text, item in by_text.items():
            receipt = {'claim_id': item['claim_id'], 'sentiment': 'neutral',
                       'confidence': 'high', 'explanation': 'Pedido identificado.',
                       'intent': 'booking' if 'agendamento' in text else 'inquiry'}
            for _ in range(2):
                self.assertEqual(client.post(path+'/results', json=receipt).status_code, 200)
        with psycopg.connect(db) as conn:
            self.assertEqual(conn.execute(
                "SELECT m.text,j.commercial_intent FROM socialmei.me_provider_sentiment_jobs j "
                "JOIN socialmei.me_messages m ON m.workspace_id=j.workspace_id AND m.id=j.message_id ORDER BY j.commercial_intent"
            ).fetchall(), [('Áudio recebido', 'booking'), ('Áudio recebido', 'inquiry')])


if __name__ == '__main__':
    unittest.main()
