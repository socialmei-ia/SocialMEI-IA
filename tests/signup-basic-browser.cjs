const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const expected = "Basic " + Buffer.from("fixture:isolated-browser-test").toString("base64");
const types = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".woff2": "font/woff2",
  ".png": "image/png",
};
const identity = {
  usuario: {
    id: 21,
    nome: "Pessoa QA",
    email: "signup@example.com",
    telefone: "11999998888",
    administrador_plataforma: false,
  },
  negocio: { id: 21, slug: "isolated-signup", nome: "Teste isolado", configuracao: {} },
  papel: "owner",
  csrf_token: "a".repeat(64),
};
let signedIn = false;
let attempts = 0;
const server = http.createServer((request, response) => {
  if (request.headers.authorization !== expected) {
    response.writeHead(401, { "WWW-Authenticate": 'Basic realm="pilot"' }).end();
    return;
  }
  const pathname = new URL(request.url, "http://localhost").pathname;
  const json = (value, status = 200) =>
    response
      .writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" })
      .end(JSON.stringify(value));
  if (pathname === "/api/v1/auth/session") return json(signedIn ? identity : null);
  if (pathname === "/api/v1/auth/registration") return json({ mode: "open" });
  if (pathname === "/api/v1/auth/me") return json({ detail: "Entre na sua conta." }, 401);
  if (pathname === "/api/v1/auth/login") {
    request.resume();
    return json({ detail: "E-mail ou senha inválidos." }, 400);
  }
  if (pathname === "/api/v1/auth/register") {
    attempts++;
    request.resume();
    signedIn = true;
    return json(identity, 201);
  }
  if (pathname.startsWith("/api/v1/")) return json([]);
  if (pathname === "/frontend/config.js") {
    const shared = { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "team" };
    response.writeHead(200, { "Content-Type": "text/javascript" }).end(
      "const SOCIALMEI_CONFIG=" +
        JSON.stringify({
          n8nMessagesUrl: null,
          auth: shared,
          clientes: shared,
          produtos: shared,
          vendas: shared,
          financeiro: shared,
        }) +
        ";",
    );
    return;
  }
  const file = path.resolve(root, "." + pathname);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())
    return response.writeHead(404).end();
  response.writeHead(200, {
    "Content-Type": types[path.extname(file)] || "application/octet-stream",
  });
  fs.createReadStream(file).pipe(response);
});

async function run() {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    browser = await chromium.launch(
      process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
    );
    const origin = `http://127.0.0.1:${server.address().port}`;
    for (const width of [1440, 390]) {
      signedIn = false;
      const context = await browser.newContext({
        viewport: { width, height: 900 },
        reducedMotion: "reduce",
      });
      const page = await context.newPage();
      const cdp = await context.newCDPSession(page);
      let challenges = 0;
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("**/*", (route) =>
        new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
      );
      await cdp.send("Fetch.enable", { handleAuthRequests: true });
      cdp.on("Fetch.requestPaused", (event) =>
        cdp.send("Fetch.continueRequest", { requestId: event.requestId }),
      );
      cdp.on("Fetch.authRequired", (event) => {
        challenges++;
        // Só o primeiro desafio recebe a senha, como um acesso humano inicial.
        cdp.send("Fetch.continueWithAuth", {
          requestId: event.requestId,
          authChallengeResponse:
            challenges === 1
              ? {
                  response: "ProvideCredentials",
                  username: "fixture",
                  password: "isolated-browser-test",
                }
              : { response: "CancelAuth" },
        });
      });
      await page.goto(origin + "/frontend/socialmei-app.html");
      await page.locator("#loginEmail").fill("signup@example.com");
      await page.locator("#loginPassword").fill("Wrong-password-123!");
      await page.locator("#xpLoginForm [type=submit]").click();
      await page.waitForFunction(() =>
        document.querySelector("#authConfirmation").textContent.includes("E-mail ou senha"),
      );
      await page.locator("[data-auth-tab=register]").click();
      await page.waitForFunction(
        () => !document.querySelector("#xpRegisterForm [type=submit]").disabled,
      );
      await page.locator("#registerName").fill("Pessoa QA");
      await page.locator("#registerEmail").fill("signup@example.com");
      await page.locator("#registerPhone").fill("11999998888");
      await page.locator("#registerPassword").fill("Valid-password-123!");
      const before = attempts;
      await page.locator("#xpRegisterForm [type=submit]").click();
      await page.locator(".contact-confirmation button[value=confirm]").click();
      await page.waitForFunction(() => window.SocialMEIAuth?.current?.usuario.id === 21);
      assert.equal(attempts, before + 1);
      assert.equal(challenges, 1, "Application auth must not invalidate the initial Basic login");
      assert.deepEqual(errors, []);

      // Controle: um 401 da aplicação realmente invalida o Basic neste navegador.
      const statuses = await page.evaluate(async () => {
        const first = await fetch("/api/v1/auth/me");
        const second = await fetch("/api/v1/auth/registration");
        return [first.status, second.status];
      });
      assert.deepEqual(statuses, [401, 401]);
      assert(challenges > 1);
      await context.close();
    }
    console.log(
      "Basic humano: sessão anônima, erro de login e cadastro passaram em desktop/mobile; controle reproduziu a invalidação por 401.",
    );
  } finally {
    await browser?.close();
    server.close();
  }
}
run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
