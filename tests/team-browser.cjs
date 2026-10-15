// Runs only in CI Docker: private HTTPS proxy, real Basic auth, mock API.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const { randomUUID } = require("node:crypto");
const root = path.resolve(__dirname, "..");
const directory = fs.mkdtempSync(path.join(os.tmpdir(), "socialmei-auth-"));
const name = "socialmei-auth-" + randomUUID().slice(0, 8);
const containers = [];
const docker = (...args) =>
  execFileSync("docker", args, { encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] }).trim();
async function run() {
  let browser,
    networkCreated = false;
  try {
    const password = "individual-ci-test-password";
    const hash = execFileSync(
      "docker",
      ["run", "--rm", "-i", "caddy:2-alpine", "caddy", "hash-password"],
      { input: password + "\n", encoding: "utf8" },
    ).trim();
    fs.mkdirSync(path.join(directory, "private"));
    fs.writeFileSync(path.join(directory, "private/users.Caddyfile"), "member " + hash + "\n");
    const config = { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "team" };
    fs.writeFileSync(
      path.join(directory, "config.js"),
      "const SOCIALMEI_CONFIG=" +
        JSON.stringify({
          n8nMessagesUrl: null,
          clientes: config,
          produtos: config,
          vendas: config,
          financeiro: config,
        }) +
        ";",
    );
    fs.writeFileSync(
      path.join(directory, "mock.py"),
      `import json
from http.server import BaseHTTPRequestHandler, HTTPServer
clients=[{'id':11,'versao':1,'nome':'Cliente protegido','tags':[]}]
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.headers.get('Authorization'):
   self.send_response(400); self.end_headers(); return
  payload=clients if self.path=='/api/v1/clientes' else next((c for c in clients if self.path=='/api/v1/clientes/'+str(c['id'])), [])
  self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(payload).encode())
 def do_POST(self):
  if self.headers.get('Authorization'):
   self.send_response(400); self.end_headers(); return
  data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  row=data['itens'][0]['cliente']; row.update(id=12,versao=1); clients.append(row)
  reply={'origem':data['origem'],'itens':[{'local_id':0,'cliente_id':12,'acao':'criar'}]}
  self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(reply).encode())
HTTPServer(('0.0.0.0',8000),Handler).serve_forever()
`,
    );
    docker("network", "create", name);
    networkCreated = true;
    function start(suffix, args) {
      const id = name + suffix;
      docker(
        "run",
        "-d",
        "--name",
        id,
        "--network",
        name,
        "-e",
        "NO_PROXY=team-api,socialmei-team-gateway,localhost,127.0.0.1",
        ...args,
      );
      containers.push(id);
      return id;
    }
    start("-api", [
      "--network-alias",
      "team-api",
      "-v",
      directory + ":/srv:ro",
      "python:3.12-alpine",
      "python",
      "/srv/mock.py",
    ]);
    fs.writeFileSync(
      path.join(directory, "Proxy.Caddyfile"),
      "https://localhost {\n tls internal\n reverse_proxy socialmei-team-gateway:80\n}\n",
    );
    const proxy = start("-proxy", [
      "-p",
      "127.0.0.1::443",
      "-v",
      path.join(directory, "Proxy.Caddyfile") + ":/etc/caddy/Caddyfile:ro",
      "caddy:2-alpine",
    ]);
    const port = docker("port", proxy, "443/tcp").split(":").pop();
    const origin = "https://localhost:" + port;
    start("-gateway", [
      "--network-alias",
      "socialmei-team-gateway",
      "-e",
      "SOCIALMEI_TEAM_HOST=localhost:" + port,
      "-v",
      path.join(root, "deploy/team/Caddyfile") + ":/etc/caddy/Caddyfile:ro",
      "-v",
      path.join(directory, "private") + ":/etc/caddy/private:ro",
      "-v",
      path.join(root, "frontend") + ":/srv/frontend:ro",
      "-v",
      path.join(directory, "config.js") + ":/srv/frontend/config.js:ro",
      "caddy:2-alpine",
    ]);
    browser = await chromium.launch(
      process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
    );
    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
      httpCredentials: { username: "member", password },
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", (route) =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
    );
    let response;
    for (let i = 0; i < 30; i++) {
      try {
        response = await context.request.get(origin + "/frontend/config.js");
        if (response.ok()) break;
      } catch (_) {}
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    assert(
      response?.ok(),
      `HTTPS authenticated gateway must start (HTTP ${response?.status() ?? "unavailable"})`,
    );
    const document = await page.goto(origin + "/");
    assert.equal(document.status(), 200);
    assert.equal(page.url(), origin + "/", "Short URL must remain in the address bar");
    await page.evaluate(() => SocialMEIExperience.enterApp("Clientes"));
    await page.waitForFunction(() =>
      [
        "clientsSourceStatus",
        "productsSourceStatus",
        "salesSourceStatus",
        "financeSourceStatus",
      ].every((id) => document.getElementById(id).textContent.includes("conectado")),
    );
    assert.equal(await page.evaluate(() => appData.clientes[0].nome), "Cliente protegido");
    await page.evaluate(() => openCreate("cliente"));
    await page.locator("#f_nome").fill("Criado via HTTPS autenticado");
    await page.locator("#createSubmit").click();
    await page.waitForFunction(() =>
      appData.clientes.some((c) => c.nome === "Criado via HTTPS autenticado"),
    );
    const anonymous = await browser.newContext({ ignoreHTTPSErrors: true });
    assert.equal((await anonymous.request.get(origin + "/api/v1/clientes")).status(), 401);
    assert.deepEqual(errors, []);
    console.log(
      "HTTPS + Basic auth: quatro módulos conectados, escrita autenticada e API anônima recusada.",
    );
  } finally {
    await browser?.close();
    for (const id of containers.reverse()) docker("rm", "-f", id);
    if (networkCreated) docker("network", "rm", name);
    fs.rmSync(directory, { recursive: true, force: true });
  }
}
run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
