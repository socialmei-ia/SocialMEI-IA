const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  for (const width of [390, 1280]) {
    const page = await browser.newPage({
      viewport: { width, height: 850 },
      reducedMotion: "reduce",
    });
    const records = new Map(),
      errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => {
      if (window !== parent) return;
      const identity = {
        usuario: { id: 76 },
        negocio: { id: 103, nome: "Fixture" },
        papel: "owner",
      };
      window.SocialMEIAuth = { remote: true, current: identity };
      window.SocialMEIV22 = {
        remote: true,
        identity,
        ready: Promise.resolve(),
        request: async (route, method = "GET", payload) => {
          const response = await fetch("/mock" + route, {
            method,
            ...(payload
              ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }
              : {}),
          });
          if (!response.ok) throw Object.assign(Error("Conflito"), { status: response.status });
          return response.json();
        },
      };
    });
    await page.route("**/*", (route) => {
      const request = route.request(),
        url = new URL(request.url());
      if (url.origin !== origin) return route.abort();
      if (url.pathname === "/m10-fixture")
        return route.fulfill({
          contentType: "text/html",
          body: '<iframe src="/frontend/telas/divulgacao.html" style="width:100%;height:800px"></iframe>',
        });
      if (!url.pathname.startsWith("/mock/instagram/publishing/drafts")) return route.continue();
      if (request.method() === "GET")
        return route.fulfill({ json: { workspace_id: 103, items: [...records.values()] } });
      const id = url.pathname.split("/").at(-1),
        payload = request.postDataJSON();
      const current = records.get(id);
      assert.equal(payload.expected_revision, current?.revision || 0);
      const row = {
        id,
        revision: payload.expected_revision + 1,
        document: payload.document,
        updated_at: new Date().toISOString(),
      };
      if (payload.archived) records.delete(id);
      else records.set(id, row);
      return route.fulfill({ json: row });
    });
    const url = origin + "/m10-fixture";
    await page.goto(url);
    const frame = page.frameLocator("iframe");
    await frame.locator("#d3 > summary").click();
    await frame.locator("#titulo").fill("Editorial persistente");
    await frame.locator("#leg").fill("Legenda do teste");
    await frame.locator("#d4 > summary").click();
    await frame.locator("#save").click();
    await frame
      .locator("#toast")
      .getByText(/Rascunho salvo no neg/)
      .waitFor();
    await page.reload();
    await frame.locator("#k1").click();
    const saved = frame.locator("#dg .dc").filter({ hasText: "Editorial persistente" });
    await saved.first().waitFor();
    await saved.first().getByRole("button", { name: "Duplicar" }).click();
    await frame.locator("#dg .dc").nth(1).waitFor();
    assert.equal(records.size, 2);
    page.once("dialog", (popup) => popup.accept());
    await frame.locator("#dg .dc").first().getByRole("button", { name: "Excluir" }).click();
    await frame.locator("#dg .dc").nth(1).waitFor({ state: "detached" });
    assert.equal(records.size, 1);
    assert.deepEqual(errors, []);
    await page.close();
  }
};
