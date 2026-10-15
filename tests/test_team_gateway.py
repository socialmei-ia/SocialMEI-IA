"""Real Caddy boundary tests, opt-in only; never touches an existing stack."""

import base64
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def docker(*args, **kwargs):
    return subprocess.run(
        ["docker", *args], text=True, capture_output=True, check=True, **kwargs
    ).stdout.strip()


@unittest.skipUnless(
    os.getenv("SOCIALMEI_TEAM_GATEWAY_TEST") == "true",
    "Docker gateway integration opt-in",
)
class TeamGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        directory = Path(cls.directory.name)
        cls.password = "gateway-ci-test-password"
        hashed = docker(
            "run",
            "--rm",
            "-i",
            "caddy:2-alpine",
            "caddy",
            "hash-password",
            input=cls.password + "\n",
        )
        (directory / "private").mkdir()
        (directory / "private/users.Caddyfile").write_text("member " + hashed + "\n")
        (directory / "mock.py").write_text(
            """from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/v1/integracoes/'):
            allowed = self.headers.get('Authorization') == 'Bearer gateway-read-test-key'
            self.send_response(200 if allowed else 401); self.end_headers()
            if allowed: self.wfile.write(b'{"workspace":"team","acesso":"leitura"}')
            return
        if self.headers.get('Authorization'):
            self.send_response(400); self.end_headers(); return
        self.send_response(200 if self.path == '/api/v1/clientes' else 404)
        self.end_headers()
        if self.path == '/api/v1/clientes': self.wfile.write(b'[{"id":1}]')
HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
"""
        )
        (directory / "frontend").mkdir()
        (directory / "frontend/socialmei-app.html").write_text(
            "<h1>Private application</h1>"
        )
        (directory / "frontend/config.js").write_text(
            'const SOCIALMEI_CONFIG={apiBaseUrl:"/api/v1"};'
        )
        (directory / "frontend/scripts").mkdir()
        (directory / "frontend/scripts/app.js").write_text("window.testApp = true;")
        (directory / ".env").write_text("must-never-be-served")
        name = "socialmei-team-test-" + uuid4().hex[:10]
        cls.network = name
        docker("network", "create", name)
        cls.addClassCleanup(lambda: docker("network", "rm", name))
        api = name + "-api"
        docker(
            "run",
            "-d",
            "--name",
            api,
            "--network",
            name,
            "--network-alias",
            "team-api",
            "-v",
            str(directory) + ":/srv:ro",
            "-w",
            "/srv",
            "python:3.12-alpine",
            "python",
            "/srv/mock.py",
        )
        cls.addClassCleanup(lambda: docker("rm", "-f", api))
        (directory / "api/v1").mkdir(parents=True)
        (directory / "api/v1/clientes").write_text('[{"id":1}]')
        gateway = name + "-gateway"
        docker(
            "run",
            "-d",
            "--name",
            gateway,
            "--network",
            name,
            "-p",
            "127.0.0.1::80",
            "-e",
            "SOCIALMEI_TEAM_HOST=app.example.com",
            "-e",
            "NO_PROXY=team-api,127.0.0.1,localhost",
            "-v",
            str(ROOT / "deploy/team/Caddyfile") + ":/etc/caddy/Caddyfile:ro",
            "-v",
            str(directory / "private") + ":/etc/caddy/private:ro",
            "-v",
            str(directory) + ":/srv:ro",
            "caddy:2-alpine",
        )
        cls.addClassCleanup(lambda: docker("rm", "-f", gateway))
        port = docker("port", gateway, "80/tcp").split(":")[-1]
        cls.origin = "http://127.0.0.1:" + port
        for _ in range(50):
            try:
                code, _ = cls.request("/")
                if code == 401:
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Test gateway did not start")

    @classmethod
    def request(cls, path, authenticated=False, origin=None, password=None):
        headers = {}
        if authenticated:
            encoded = base64.b64encode(
                ("member:" + (password or cls.password)).encode()
            ).decode()
            headers["Authorization"] = "Basic " + encoded
        if origin:
            headers["Origin"] = origin
        try:
            with urlopen(
                Request(cls.origin + path, headers=headers), timeout=3
            ) as response:
                return response.status, response.read().decode()
        except HTTPError as error:
            return error.code, error.read().decode()

    def test_site_and_api_are_denied_without_credentials(self):
        for path in [
            "/",
            "/frontend/socialmei-app.html",
            "/frontend/config.js",
            "/config.js",
            "/scripts/app.js",
            "/api/v1/clientes",
            "/api/v1/auth/registration",
            "/api/v1/auth/session",
            "/health/db",
        ]:
            self.assertEqual(self.request(path)[0], 401, path)
        self.assertEqual(
            self.request("/api/v1/clientes", True, password="wrong-password")[0], 401
        )

    def test_authenticated_frontend_and_original_api_prefix(self):
        for path in ["/", "/frontend/socialmei-app.html", "/index.html"]:
            code, body = self.request(path, True)
            self.assertEqual(code, 200, path)
            self.assertIn("Private application", body, path)
        code, body = self.request("/config.js", True)
        self.assertEqual(code, 200)
        self.assertIn("SOCIALMEI_CONFIG", body)
        code, body = self.request("/scripts/app.js", True)
        self.assertEqual(code, 200)
        self.assertIn("window.testApp", body)
        code, body = self.request("/api/v1/clientes", True)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), [{"id": 1}])

    def test_secrets_and_unlisted_routes_are_never_served(self):
        for path in [
            "/.env",
            "/tools/team-admin.py",
            "/docs",
            "/frontend/../.env",
            "/api/v1/../../.env",
            "/docs/openapi.json",
        ]:
            code, body = self.request(path, True)
            self.assertNotEqual(code, 200, path)
            self.assertNotIn("must-never-be-served", body)

    def test_foreign_origin_denied_even_with_correct_password(self):
        self.assertEqual(
            self.request("/api/v1/clientes", True, origin="https://evil.example.com")[
                0
            ],
            403,
        )
        self.assertEqual(
            self.request("/api/v1/clientes", True, origin="https://app.example.com")[0],
            200,
        )

    def test_technical_bearer_does_not_bypass_human_login(self):
        self.assertEqual(self.request("/api/v1/integracoes/resumo")[0], 401)
        headers = {"Authorization": "Bearer gateway-read-test-key"}
        with urlopen(
            Request(self.origin + "/api/v1/integracoes/resumo", headers=headers),
            timeout=3,
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response)["acesso"], "leitura")
        for path in [
            "/",
            "/api/v1/clientes",
            "/frontend/config.js",
            "/api/v1/integracoes/unknown",
            "/api/v1/integracoes/%2e%2e/clientes",
        ]:
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(self.origin + path, headers=headers), timeout=3)
            self.assertEqual(error.exception.code, 401)
        with self.assertRaises(HTTPError) as error:
            urlopen(
                Request(
                    self.origin + "/api/v1/integracoes/clientes",
                    headers=headers,
                    method="POST",
                    data=b"{}",
                ),
                timeout=3,
            )
        self.assertEqual(error.exception.code, 401)
        with self.assertRaises(HTTPError) as error:
            urlopen(
                Request(
                    self.origin + "/api/v1/integracoes/resumo",
                    headers={**headers, "Origin": "https://evil.example.com"},
                ),
                timeout=3,
            )
        self.assertEqual(error.exception.code, 403)
