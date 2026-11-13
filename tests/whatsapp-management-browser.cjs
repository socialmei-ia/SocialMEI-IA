const assert = require("node:assert/strict");
const path = require("node:path");
const { chromium } = require("playwright");

async function run() {
  const browser = await chromium.launch();
  try {
    for (const width of [390, 1440]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("https://management.example.test/**", (route) =>
        route.fulfill({
          contentType: "text/html",
          body: '<html><body><div id="v"></div></body></html>',
        }),
      );
      await page.goto("https://management.example.test/#/config/integracoes");
      await page.evaluate(() => {
        window.render = () => {};
        window.active = { usuario: { id: 1 }, negocio: { id: 10 }, papel: "owner" };
        window.requests = [];
        window.revision = 0;
        window.intent = null;
        window.receipts = {};
        window.uncertain = true;
        window.SocialMEIV22 = {
          remote: true,
          get identity() {
            return active;
          },
          request: async (url, method = "GET", value) => {
            requests.push({ url, method, value: value ? structuredClone(value) : null });
            if (url === "/whatsapp/connection" && method === "GET") {
              if (window.delayRead) {
                window.delayRead = false;
                await new Promise((resolve) => (window.finishRead = resolve));
              }
              return {
                source: "server",
                workspace_id: active.negocio.id,
                revision,
                connection_state: intent ? "configuration_pending" : "not_connected",
                private_binding_verified: false,
                session_live_verified: false,
                receiving_messages: false,
                sending_enabled: false,
                probe_available: false,
                management_available: true,
                pairing_available: false,
                request: intent,
                next_step: "A equipe precisa conferir o vínculo.",
              };
            }
            if (url === "/whatsapp/connection/requests" && method === "POST") {
              if (value.phone?.endsWith("1111")) {
                const error = Error("Confira o número.");
                error.status = 422;
                throw error;
              }
              if (!receipts[value.operation_id]) {
                revision++;
                intent = { action: value.action, phone_hint: "•••• 0000" };
                receipts[value.operation_id] = {
                  accepted: true,
                  executed: false,
                  status: "awaiting_operator_approval",
                  revision,
                };
              }
              if (uncertain) {
                uncertain = false;
                throw Error("Resposta não confirmada.");
              }
              return receipts[value.operation_id];
            }
            throw Error("Unexpected request: " + method + " " + url);
          },
        };
      });
      await page.addScriptTag({
        path: path.join(__dirname, "../frontend/scripts/v22-whatsapp-management.js"),
      });
      const panel = page.locator("[data-whatsapp-management]");
      await panel.getByRole("button", { name: "Registrar solicitação", exact: true }).waitFor();
      assert.match(await panel.innerText(), /Não conectado/);
      assert.equal(await panel.getByRole("button", { name: /QR/ }).count(), 0);
      const phone = panel.getByLabel("Número com DDD e código do país");
      await phone.fill("+5581999991111");
      await panel.getByRole("checkbox").check();
      await panel.getByRole("button", { name: "Registrar solicitação", exact: true }).click();
      await panel.getByText("Confira o número.", { exact: true }).waitFor();
      assert.equal(await phone.isEditable(), true);
      await phone.fill("+5581999990000");
      await panel.getByRole("button", { name: "Registrar solicitação", exact: true }).click();
      await panel
        .getByRole("button", { name: "Conferir a mesma solicitação", exact: true })
        .waitFor();
      assert.equal(await phone.isEditable(), false);
      await panel
        .getByRole("button", { name: "Conferir a mesma solicitação", exact: true })
        .click();
      await panel.getByText(/Solicitação registrada\. A equipe/).waitFor();
      const posts = await page.evaluate(() => requests.filter((r) => r.method === "POST"));
      assert.deepEqual(posts[1].value, posts[2].value);
      assert.equal(await page.evaluate(() => revision), 1);
      assert.match(await panel.innerText(), /A sessão ainda não foi alterada/);
      // A mounted old-business form must not dispatch under the next business.
      const before = posts.length;
      await page.evaluate(
        () => (active = { usuario: { id: 1 }, negocio: { id: 20 }, papel: "owner" }),
      );
      await panel.getByLabel("Número com DDD e código do país").fill("+5581999990001");
      await panel.getByRole("checkbox").check();
      await panel.getByRole("button", { name: "Registrar solicitação", exact: true }).click();
      assert.equal(
        await page.evaluate(() => requests.filter((r) => r.method === "POST").length),
        before,
      );
      await page.evaluate(() => {
        active.papel = "admin";
        document.getElementById("v").replaceChildren();
        render();
      });
      await panel.getByRole("button", { name: "Atualizar estado salvo", exact: true }).waitFor();
      assert.equal(
        await panel.getByRole("button", { name: "Registrar solicitação", exact: true }).count(),
        0,
      );
      assert.match(await panel.innerText(), /Somente o proprietário/);
      assert.deepEqual(errors, []);
      await page.close();
    }
  } finally {
    await browser.close();
  }
  console.log(
    "WhatsApp management: mobile/desktop, truthful pending state, exact uncertain retry, validation correction, stale workspace and admin read-only PASS (controlled API).",
  );
}

if (require.main === module)
  run().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
module.exports = run;
