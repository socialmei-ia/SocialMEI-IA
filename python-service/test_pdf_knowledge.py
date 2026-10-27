"""Private PDF ingestion and search contract, no network or real documents."""
import io
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app import app
from pdf_knowledge import extract_chunks, validated_name, MAX_BYTES


class PdfKnowledgeContracts(unittest.TestCase):
    def test_reject_bad_filename_and_invalid_documents(self):
        for name in ("", "../segredo.pdf", "arquivo.txt", "/tmp/doc.pdf", "doc.pdf\n", "doc.pdf\x00"):
            with self.subTest(name=name), self.assertRaises(HTTPException):
                validated_name(name)
        self.assertEqual(validated_name("tabela-precos.pdf"), "tabela-precos.pdf")
        for raw in (b"%PDF-", b"not a pdf", b"%PDF-1.7" + b"x" * (MAX_BYTES + 1)):
            with self.subTest(length=len(raw)), self.assertRaises(HTTPException):
                extract_chunks(raw)

    def test_blank_pdf_flags_no_text_not_fake_knowledge(self):
        output = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=400)
        writer.write(output)
        pages, chunks = extract_chunks(output.getvalue())
        self.assertEqual(pages, 1)
        self.assertEqual(chunks, [])

    def test_off_by_default_before_upload_or_database_access(self):
        with patch.dict(os.environ, {
            "SOCIALMEI_KNOWLEDGE_PDF_ENABLED": "false",
            "SOCIALMEI_AUTH_ENABLED": "true",
            "SOCIALMEI_AUTH_ORIGIN": "https://app.example.com",
            "SOCIALMEI_SHARED_DATA_ENABLED": "true",
        }):
            client = TestClient(app, base_url="https://app.example.com")
            self.assertEqual(client.get("/api/v1/knowledge/pdf").status_code, 401)
            # An authenticated request is needed; disabled endpoint never opens PDF.
            self.assertEqual(
                client.post("/api/v1/knowledge/pdf?filename=test.pdf",
                            headers={"Origin": "https://app.example.com", "Content-Type": "application/pdf"},
                            content=b"%PDF-1.7").status_code,
                401,
            )


class PdfResourceContracts(unittest.TestCase):
    def test_worker_does_not_inherit_application_secrets(self):
        import subprocess
        with patch.dict(os.environ, {'DATABASE_URL':'synthetic-private','SOCIALMEI_INSTAGRAM_CLIENT_SECRET':'synthetic-private'}), patch('pdf_knowledge.subprocess.run',return_value=subprocess.CompletedProcess([],0,b'[1,[]]',b'')) as run:
            self.assertEqual(extract_chunks(text_pdf()),(1,[]))
        self.assertEqual(set(run.call_args.kwargs['env']),{'PATH','LANG','LC_ALL'})
        self.assertEqual(run.call_args.kwargs['timeout'],8)
        self.assertNotIn('synthetic-private',str(run.call_args.kwargs['env']))

    def test_active_pdf_content_is_rejected_before_indexing(self):
        from pypdf.generic import DictionaryObject, NameObject, TextStringObject
        writer = PdfWriter(); writer.add_blank_page(width=300,height=400)
        writer._root_object[NameObject('/OpenAction')] = DictionaryObject({NameObject('/S'):NameObject('/JavaScript'),NameObject('/JS'):TextStringObject('private-pdf-command')})
        raw=io.BytesIO();writer.write(raw)
        with self.assertRaises(HTTPException) as failure:extract_chunks(raw.getvalue())
        self.assertEqual(failure.exception.status_code,422)
        self.assertNotIn('private-pdf-command',str(failure.exception.detail))

    def test_pdf_extraction_has_an_enforced_subprocess_deadline(self):
        import subprocess
        output=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=300,height=400);writer.write(output)
        with patch('pdf_knowledge.subprocess.run',side_effect=subprocess.TimeoutExpired('private-pdf-name',8)), self.assertRaises(HTTPException) as failure:
            extract_chunks(output.getvalue())
        self.assertEqual(failure.exception.status_code,422)

    def test_worker_slot_exhaustion_does_not_open_another_parser(self):
        from pdf_knowledge import EXTRACTION_SLOTS
        output=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=300,height=400);writer.write(output)
        EXTRACTION_SLOTS.acquire();EXTRACTION_SLOTS.acquire()
        try:
            with patch('pdf_knowledge.subprocess.run',side_effect=AssertionError('Spawned despite capacity')), self.assertRaises(HTTPException) as failure:
                extract_chunks(output.getvalue())
            self.assertEqual(failure.exception.status_code,503)
        finally:
            EXTRACTION_SLOTS.release();EXTRACTION_SLOTS.release()


def text_pdf(text='Documentos exigidos: identidade e comprovante de residencia.'):
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer=PdfWriter();page=writer.add_blank_page(width=300,height=400)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 30 300 Td ('+text+') Tj ET').encode('ascii'))
    page[NameObject('/Contents')]=writer._add_object(stream)
    output=io.BytesIO();writer.write(output);return output.getvalue()


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL','').strip(),'Disposable PostgreSQL required')
class PdfPersistenceTests(unittest.TestCase):
    import test_account_auth as accounts
    setUpClass=classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login=accounts.AccountDatabaseTests.login
    invited=accounts.AccountDatabaseTests.invited
    register=accounts.AccountDatabaseTests.register

    def setUp(self):
        self.accounts.AccountDatabaseTests.setUp(self)
        flag=patch.dict(os.environ,{'SOCIALMEI_KNOWLEDGE_PDF_ENABLED':'true'});flag.start();self.addCleanup(flag.stop)
        self.first=self.register('pdf-a@example.test');self.second=self.register('pdf-b@example.test')

    def upload(self, client, raw=None):
        r=client.post('/api/v1/knowledge/pdf?filename=orientacao.pdf',headers={'Content-Type':'application/pdf'},content=raw or text_pdf())
        self.assertEqual(r.status_code,201,r.text);return r.json()

    def test_upload_survives_login_sources_and_private_document_isolation(self):
        row=self.upload(self.first);url='/api/v1/knowledge/pdf/'+row['id']
        again=self.login('pdf-a@example.test')
        self.assertEqual(again.get('/api/v1/knowledge/pdf').json()['items'][0]['id'],row['id'])
        results=again.get('/api/v1/knowledge/pdf/search?q=documentos').json()['items']
        self.assertEqual(results[0]['page'],1);self.assertIn('identidade',results[0]['excerpt'])
        self.assertEqual(self.second.get('/api/v1/knowledge/pdf/search?q=documentos').json()['items'],[])
        self.assertEqual(self.second.get(url+'/download').status_code,404)
        self.assertEqual(self.second.delete(url).status_code,404)
        self.assertEqual(self.second.post(url+'/reprocess',json={'sha256':row['sha256']}).status_code,404)
        download=again.get(url+'/download');self.assertEqual(download.content,text_pdf());self.assertIn('attachment',download.headers['content-disposition'])
        self.assertEqual(row['size_bytes'],len(download.content))
        self.assertEqual(again.delete(url).status_code,204)
        self.assertEqual(again.get('/api/v1/knowledge/pdf/search?q=documentos').json()['items'],[])
        self.assertEqual(again.get(url+'/download').status_code,404)

    def test_replace_reprocess_conflicts_and_old_index_are_transactional(self):
        row=self.upload(self.first);url='/api/v1/knowledge/pdf/'+row['id']
        self.assertEqual(self.first.post(url+'/reprocess',json={'sha256':row['sha256']}).status_code,200)
        headers={'Content-Type':'application/pdf','If-Match':row['sha256']}
        self.assertEqual(self.first.put(url+'?filename=novo.pdf',headers=headers,content=b'bad').status_code,413)
        self.assertTrue(self.first.get('/api/v1/knowledge/pdf/search?q=documentos').json()['items'])
        replaced=self.first.put(url+'?filename=novo.pdf',headers=headers,content=text_pdf('Prazo para entrega: cinco dias uteis.'))
        self.assertEqual(replaced.status_code,200,replaced.text)
        self.assertEqual(replaced.json()['id'],row['id'])
        self.assertEqual(self.first.get('/api/v1/knowledge/pdf/search?q=documentos').json()['items'],[])
        self.assertTrue(self.first.get('/api/v1/knowledge/pdf/search?q=prazo').json()['items'])
        self.assertEqual(self.first.put(url+'?filename=antigo.pdf',headers=headers,content=text_pdf()).status_code,409)
        self.assertEqual(self.first.post(url+'/reprocess',json={'sha256':row['sha256']}).status_code,409)
        import psycopg
        with psycopg.connect(os.environ['TEST_DATABASE_URL']) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='viewer' WHERE user_id=%s",(self.first.identity['usuario']['id'],))
        self.assertEqual(self.first.get('/api/v1/knowledge/pdf').status_code,200)
        self.assertEqual(self.first.post(url+'/reprocess',json={'sha256':replaced.json()['sha256']}).status_code,403)
        self.assertEqual(self.first.delete(url).status_code,403)

    def test_permission_revoked_during_extraction_cannot_persist_document(self):
        import psycopg
        original = extract_chunks
        def revoke_after_parse(raw):
            result = original(raw)
            with psycopg.connect(os.environ['TEST_DATABASE_URL']) as conn:
                conn.execute("UPDATE socialmei.workspace_members SET role='viewer' WHERE user_id=%s",(self.first.identity['usuario']['id'],))
            return result
        with patch('pdf_knowledge.extract_chunks',side_effect=revoke_after_parse):
            response = self.first.post('/api/v1/knowledge/pdf?filename=blocked.pdf',headers={'Content-Type':'application/pdf'},content=text_pdf())
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.first.get('/api/v1/knowledge/pdf').json()['items'],[])

    def test_deactivated_account_cannot_upload_replace_or_reprocess_after_extraction(self):
        import psycopg
        original = extract_chunks
        row = self.upload(self.first)
        url = '/api/v1/knowledge/pdf/' + row['id']
        user_id = self.first.identity['usuario']['id']
        def deactivate_after_parse(raw):
            result = original(raw)
            with psycopg.connect(os.environ['TEST_DATABASE_URL']) as conn:
                conn.execute('UPDATE socialmei.auth_credenciais SET ativo=false WHERE user_id=%s',(user_id,))
            return result
        for operation in ('upload','reprocess','replace'):
            with self.subTest(operation=operation):
                try:
                    with patch('pdf_knowledge.extract_chunks',side_effect=deactivate_after_parse):
                        if operation == 'upload':
                            response = self.first.post('/api/v1/knowledge/pdf?filename=blocked.pdf',headers={'Content-Type':'application/pdf'},content=text_pdf('Outro documento.'))
                        elif operation == 'replace':
                            response = self.first.put(url+'?filename=alterado.pdf',headers={'Content-Type':'application/pdf','If-Match':row['sha256']},content=text_pdf('Outro documento.'))
                        else:
                            response = self.first.post(url+'/reprocess',json={'sha256':row['sha256']})
                    self.assertEqual(response.status_code,403,response.text)
                finally:
                    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as conn:
                        conn.execute('UPDATE socialmei.auth_credenciais SET ativo=true WHERE user_id=%s',(user_id,))
                self.assertEqual(self.first.get('/api/v1/knowledge/pdf').json()['items'],[row])
                self.assertTrue(self.first.get('/api/v1/knowledge/pdf/search?q=documentos').json()['items'])
