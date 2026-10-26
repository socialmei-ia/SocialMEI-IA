// New UI failure boundaries with a controlled API; no service credentials or external calls.
const assert = require("node:assert/strict"),
  fs = require("node:fs");
module.exports = async function (browser, origin) {
  const page = await browser.newPage({ reducedMotion: "reduce" });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript(() => {
    localStorage.setItem("socialmei-auth-browser-scope", "91:17");
    localStorage.setItem("smei-perfil", JSON.stringify({ nome: "OUTRO-USUARIO-PRIVADO" }));
    localStorage.setItem("smei-opp-v6", JSON.stringify([{ c: "OUTRO-USUARIO-PRIVADO" }]));
    localStorage.setItem("smei4_d", JSON.stringify([{ titulo: "OUTRO-USUARIO-PRIVADO" }]));
  });
  let posts = 0,
    failRefresh = false;
  const identity = {
    usuario: { id: 91, nome: "Conta V22", email: "v22@example.test" },
    negocio: { id: 17, slug: "v22", nome: "Negócio V22", configuracao: {} },
    papel: "owner",
    csrf_token: "a".repeat(64),
  };
  await page.route("**/*", (route) => {
    const req = route.request(),
      url = new URL(req.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname.endsWith("/config.js"))
      return route.fulfill({
        contentType: "text/javascript",
        body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
      });
    if (!url.pathname.startsWith("/api/v1/")) return route.continue();
    const p = url.pathname.replace("/api/v1", "");
    if (p === "/auth/session") return route.fulfill({ json: identity });
    assert.equal(req.headers()["x-socialmei-identity"], "91:17");
    if (p === "/auth/preferences")
      return route.fulfill({
        json: { schema_version: 1, revision: 0, preferences: { theme: "auto" } },
      });
    if (p === "/workspace-profile")
      return route.fulfill({ json: { schema_version: 1, revision: 0, profile: null } });
    if (p === "/message-enrichment/capabilities")
      return route.fulfill({ json: { mode: "disabled" } });
    if (p === "/opportunities") return route.fulfill({ json: { workspace_id: 17, items: [] } });
    if (p === "/clientes" && req.method() === "POST") {
      posts++;
      assert.equal(req.headers()["x-socialmei-csrf"], "a".repeat(64));
      failRefresh = true;
      return route.fulfill({ status: 201, json: { id: 1, ...req.postDataJSON(), versao: 1 } });
    }
    if (p === "/clientes" && failRefresh)
      return route.fulfill({ status: 503, json: { detail: "Indisponível no teste" } });
    if (p === "/vendas")
      return route.fulfill({
        json: [
          {
            id: 1,
            cliente_id: 1,
            produto_id: 1,
            cliente: "=SUM(1,1)",
            item: "Serviço",
            data: new Date().toLocaleDateString("en-CA"),
            quantidade: 1,
            valor: 30,
            status: "Pago",
            versao: 1,
          },
        ],
      });
    return route.fulfill({ json: [] });
  });
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () => window.SocialMEIV22?.identity && !document.getElementById("app").hidden,
    );
    assert(!(await page.locator("body").innerText()).includes("OUTRO-USUARIO-PRIVADO"));
    assert.equal(await page.locator(".bellb .bcn").count(), 0, "No invented AI notifications");
    await page.evaluate(() => go("/config/negocio"));
    assert.equal(await page.locator("#b_seg").isDisabled(), true);
    await page.evaluate(() => go("/oport"));
    const op = page.frameLocator("#v iframe");
    await op.locator("#client").waitFor();
    assert(!(await op.locator("body").innerText()).includes("OUTRO-USUARIO-PRIVADO"));
    await page.evaluate(() => go("/relatorios"));
    const downloadPromise = page.waitForEvent("download");
    await page.evaluate(() => exportCsv());
    const download = await downloadPromise;
    const csv = fs.readFileSync(await download.path(), "utf8");
    assert(csv.includes('"\'=SUM(1,1)"'), csv);
    await page.evaluate(() => go("/negocio/clientes"));
    await page.getByRole("button", { name: "Novo cliente", exact: true }).click();
    await page.locator("#f_n").fill("Registro confirmado");
    await page.locator("dialog button[type=submit]").click();
    await page.locator("dialog").waitFor({ state: "hidden" });
    assert.equal(posts, 1);
    await page.getByRole("button", { name: "Novo cliente", exact: true }).click();
    await page.locator("#f_n").fill("Não duplicar");
    await page.locator("dialog button[type=submit]").click();
    await page.getByText("Aguarde o carregamento dos dados.", { exact: true }).waitFor();
    assert.equal(posts, 1);
    assert.deepEqual(errors, []);
    return "V22: identity-scoped drafts, CSV formula protection and acknowledged-write/refresh failure verified";
  } finally {
    await page.close();
  }
};
