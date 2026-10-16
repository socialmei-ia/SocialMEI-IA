const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const server = http.createServer((request, response) => {
  const file = path.resolve(root, "." + new URL(request.url, "http://local").pathname);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    response.writeHead(404).end();
    return;
  }
  response.setHeader(
    "Content-Type",
    { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".woff2": "font/woff2" }[
      path.extname(file)
    ] || "application/octet-stream",
  );
  fs.createReadStream(file).pipe(response);
});
async function run() {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch(
    process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
  );
  const errors = [],
    external = [];
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: "reduce",
    });
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) {
        external.push(url.origin);
        return route.abort();
      }
      if (url.pathname === "/frontend/config.js")
        return route.fulfill({
          contentType: "text/javascript",
          body: "const SOCIALMEI_CONFIG={n8nMessagesUrl:null};",
        });
      return route.continue();
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => SocialMEIExperience.enterApp("Caixa Unificada"));
    const first = page.locator("#conversationList [data-conversation]").first();
    const id = await first.getAttribute("data-conversation");
    await first.click();
    await page.locator("#messageInput").fill("Rascunho de revisão, sem envio");
    assert(
      (await page.locator(`[data-conversation="${id}"] .preview-text`).textContent()).startsWith(
        "Rascunho:",
      ),
    );
    await page.locator("#conversationList [data-conversation]").nth(1).click();
    await page.locator(`#conversationList [data-conversation="${id}"]`).click();
    assert.equal(
      await page.locator("#messageInput").inputValue(),
      "Rascunho de revisão, sem envio",
    );
    await page.locator("#sendMessage").click();
    assert((await page.locator(".msg.out").last().textContent()).includes("não enviada"));
    assert(
      !(await page.locator(`[data-conversation="${id}"] .preview-text`).textContent()).startsWith(
        "Rascunho:",
      ),
    );
    await page.evaluate(() => setView("Assistente"));
    await page.locator("[data-ai-conversation]").first().click();
    await page.locator("[data-ai-intent=reply]").click();
    await page.locator("[data-ai-prepare]").first().click();
    await page.locator(".assistant-edit summary").click();
    await page
      .locator("#assistantDraftEditor")
      .fill("Texto revisado pelo empreendedor, sem envio.");
    assert.equal(
      await page.locator(".assistant-draft-text").textContent(),
      "Texto revisado pelo empreendedor, sem envio.",
    );
    const beforeInsert = await page.evaluate(() =>
      sessionData.conversas.reduce((n, c) => n + c.mensagens.length, 0),
    );
    await page.locator("[data-ai-insert]").click();
    assert(
      (await page.locator("#messageInput").inputValue()).includes(
        "Texto revisado pelo empreendedor, sem envio.",
      ),
    );
    assert.equal(
      await page.evaluate(() => sessionData.conversas.reduce((n, c) => n + c.mensagens.length, 0)),
      beforeInsert,
    );
    await page.evaluate(() => setView("Automações"));
    assert(
      (await page.locator(".automation-integration-state").textContent()).includes("Não conectada"),
    );
    await page.locator("#automationFeature [data-rule-test]").click();
    assert.match(await page.locator("#nvManagementDrawerTitle").innerText(), /simulado/);
    await page.keyboard.press("Escape");
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "Atendimento, edição do Assistente e simulação de Automações passaram, sem envio externo.",
    );
  } finally {
    await browser.close();
    server.close();
  }
}
run().catch((error) => {
  console.error(error);
  server.close();
  process.exitCode = 1;
});
