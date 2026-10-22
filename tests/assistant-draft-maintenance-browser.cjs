const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
module.exports = async function assistantDraftMaintenance(browser, origin) {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
  );
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.evaluate(() => {
      SocialMEIExperience.enterApp("Caixa Unificada");
      sessionData.conversas = [
        {
          id: 101,
          nome: "Ana fictícia",
          canal: "whatsapp",
          status: "aberto",
          telefone: "—",
          usuario: "—",
          naoLidas: 0,
          mensagens: [{ de: "cliente", texto: "Quero saber sobre o serviço.", hora: "10:00" }],
        },
        {
          id: 102,
          nome: "Ana fictícia",
          canal: "instagram",
          status: "aberto",
          telefone: "—",
          usuario: "@ana.ficticia",
          naoLidas: 0,
          mensagens: [{ de: "cliente", texto: "Preciso de ajuda com meu pedido.", hora: "10:01" }],
        },
      ];
      conversationDrafts.set(102, { text: "Rascunho separado do Instagram", note: true });
      renderConversationList();
    });
    await page.evaluate(() => selectConversation(101));
    await page.locator("#messageInput").fill("Minha edição humana ainda não enviada.");
    await page.evaluate(() => saveCurrentDraft());
    await page.evaluate(() => setView("Assistente"));
    await page.locator('[data-ai-conversation="101"]').click();
    await page.locator('[data-ai-intent="reply"]').click();
    await page.locator("[data-ai-prepare]").first().click();
    const draft = await page.locator(".assistant-draft-text").innerText();
    const beforeMessages = await page.evaluate(() =>
      sessionData.conversas.map((item) => item.mensagens.length),
    );
    await page.locator("[data-ai-insert]").click();
    assert.equal(
      await page.locator("#messageInput").inputValue(),
      "Minha edição humana ainda não enviada.\n\n" + draft,
      "Assistant insertion into the already active conversation must keep the human draft and the prepared reply",
    );
    assert.equal(await page.evaluate(() => activeConversationId), 101);
    assert.deepEqual(
      await page.evaluate(() => sessionData.conversas.map((item) => item.mensagens.length)),
      beforeMessages,
      "Inserting a draft must never send a message",
    );
    assert.equal(
      await page.evaluate(() => conversationDrafts.get(102)?.text || ""),
      "Rascunho separado do Instagram",
      "Names shared by different channels must not share drafts",
    );
    await page.evaluate(() => setView("Assistente"));
    await page.locator("[data-ai-insert]").click();
    assert.equal(
      await page.locator("#messageInput").inputValue(),
      "Minha edição humana ainda não enviada.\n\n" + draft,
      "Repeated insertion must not duplicate the same prepared reply",
    );
    const edited =
      "Minha edição humana ainda não enviada.\n\n" + draft + "\n\nFecho escrito por mim.";
    await page.locator("#messageInput").fill(edited);
    await page.evaluate(() => saveCurrentDraft());
    await page.evaluate(() => setView("Assistente"));
    await page.locator("[data-ai-insert]").click();
    assert.equal(
      await page.locator("#messageInput").inputValue(),
      edited,
      "Reinsertion must preserve text added after the suggestion without duplicating it",
    );
    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((value) => SocialMEIThemes.select(value, { persist: false }), theme);
        for (const view of ["Assistente", "Caixa Unificada"]) {
          await page.evaluate((value) => setView(value), view);
          assert(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
            `overflow ${view} ${width} ${theme}`,
          );
        }
      }
    }
    assert.deepEqual(errors, []);
    return "Assistente: edição humana preservada na mesma conversa, reinserção idempotente, homônimos/canais separados e nenhum envio; cinco larguras/dois temas PASS";
  } finally {
    await page.close();
  }
};
if (require.main === module) {
  const server = http.createServer((req, res) => {
    const file = path.resolve(root, "." + new URL(req.url, "http://localhost").pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404).end();
      return;
    }
    res.setHeader(
      "Content-Type",
      {
        ".html": "text/html",
        ".js": "application/javascript",
        ".css": "text/css",
        ".png": "image/png",
        ".woff2": "font/woff2",
      }[path.extname(file)] || "application/octet-stream",
    );
    fs.createReadStream(file).pipe(res);
  });
  (async () => {
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const browser = await chromium.launch(
      process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
    );
    try {
      console.log(await module.exports(browser, `http://127.0.0.1:${server.address().port}`));
    } finally {
      await browser.close();
      server.close();
    }
  })().catch((error) => {
    console.error(error);
    server.close();
    process.exitCode = 1;
  });
}
