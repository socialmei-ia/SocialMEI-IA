"""Local upload validation: synthetic image bytes only."""
import base64
import io
import unittest
from PIL import Image
from fastapi import HTTPException
from instagram_media import MAX_IMAGE_BYTES, normalize_image


def picture(kind='JPEG', size=(800, 800)):
    output = io.BytesIO()
    Image.new('RGB', size, 'navy').save(output, format=kind)
    return output.getvalue()


class LocalMediaTests(unittest.TestCase):
    def test_jpeg_and_png_are_clean_jpegs(self):
        for kind in ('JPEG', 'PNG', 'WEBP'):
            raw = normalize_image(base64.b64encode(picture(kind)).decode())
            with Image.open(io.BytesIO(raw)) as image:
                self.assertEqual(image.format, 'JPEG')
                self.assertEqual(image.size, (800, 800))
                self.assertNotIn('exif', image.info)

    def test_invalid_base64_fake_image_and_oversize_are_rejected(self):
        for raw in ('!', base64.b64encode(b'<script>private</script>').decode(),
                    base64.b64encode(b'x' * (MAX_IMAGE_BYTES + 1)).decode()):
            with self.subTest(), self.assertRaises(HTTPException) as error:
                normalize_image(raw)
            self.assertIn(error.exception.status_code, (413, 422))
            self.assertNotIn('private', error.exception.detail)

    def test_unsupported_animation_and_ratio_rejected(self):
        for raw in (picture('GIF'), picture(size=(100, 1000)), picture(size=(1000, 100))):
            with self.subTest(), self.assertRaises(HTTPException):
                normalize_image(base64.b64encode(raw).decode())


class MediaPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_media_capability_never_reaches_access_log_scope(self):
        from instagram_media import InstagramMediaPrivacy
        marker = 'private-key-do-not-log'
        scope = {'type':'http','path':'/media/instagram/'+marker+'.jpg','raw_path':('/media/instagram/'+marker+'.jpg').encode(),'query_string':b'extra=private'}
        seen = []
        async def app(scope, receive, send):
            self.assertIn(marker, scope['path'])
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b''})
        async def send(message):
            seen.append(dict(scope))
        await InstagramMediaPrivacy(app)(scope, None, send)
        for record in seen:
            self.assertNotIn(marker,str(record))
            self.assertNotIn('extra=private',str(record))

    async def test_exception_path_is_redacted_before_outer_500_logging(self):
        from instagram_media import InstagramMediaPrivacy
        scope = {'type':'http','path':'/media/instagram/private.jpg','raw_path':b'/media/instagram/private.jpg','query_string':b''}
        async def fail(scope, receive, send):
            raise RuntimeError('synthetic storage failure')
        with self.assertRaises(RuntimeError):
            await InstagramMediaPrivacy(fail)(scope,None,None)
        self.assertNotIn('private',scope['path'])
        self.assertNotIn(b'private',scope['raw_path'])

    def test_real_uvicorn_access_log_redacts_media_canary(self):
        import http.client
        import os
        from pathlib import Path
        import socket
        import subprocess
        import sys
        import time
        marker = 'private-key-never-log-this'
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            env = {**os.environ, 'SOCIALMEI_INSTAGRAM_RUNTIME_MODE':'disabled'}
            process = subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--fd',str(listener.fileno())],
                                       pass_fds=(listener.fileno(),), cwd=Path(__file__).parent,
                                       env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                for _ in range(100):
                    try:
                        client = http.client.HTTPConnection('127.0.0.1',port,timeout=1)
                        client.request('GET','/media/instagram/'+marker+'.jpg')
                        response=client.getresponse()
                        self.assertEqual(response.status,404)
                        response.read(); client.close(); break
                    except (OSError, http.client.HTTPException):
                        time.sleep(.05)
                else:
                    self.fail('Disposable Uvicorn did not become ready')
            finally:
                process.terminate()
                output,_=process.communicate(timeout=10)
        self.assertIn('404',output)
        self.assertIn('redacted',output)
        self.assertNotIn(marker,output)
