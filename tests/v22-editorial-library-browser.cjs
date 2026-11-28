const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  for (const width of [390, 1280]) {
    const page = await browser.newPage({
      viewport: { width, height: 850 },
      reducedMotion: "reduce",
    });
    const records = new Map(),
      errors = [];
    const assetId = "ddf729d5-d23c-4fae-8b0f-961522e67106";
    let image;
    page.on("dialog", (popup) => popup.accept());
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
      if (url.pathname === "/mock/instagram/publishing/draft-assets") {
        if (request.method() === "POST") {
          image = request.postDataJSON().image_base64;
          return route.fulfill({ json: { id: assetId } });
        }
        return route.fulfill({
          json: {
            workspace_id: 103,
            items: [{ id: assetId, created_at: new Date().toISOString() }],
          },
        });
      }
      if (url.pathname === "/mock/instagram/publishing/draft-assets/" + assetId)
        return route.fulfill({ json: { id: assetId, workspace_id: 103, image_base64: image } });
      if (url.pathname === "/mock/instagram/publishing/content-ai") {
        assert.equal(request.postDataJSON().mode, "caption");
        return route.fulfill({ json: { mode: "caption", text: "Sugestão de legenda teste" } });
      }
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
    await frame.locator("#d2 > summary").click();
    await frame.locator("#tema").fill("Tema de teste");
    await frame.getByRole("button", { name: "Gerar legenda com IA" }).click();
    await frame.getByText("Sugestão de legenda teste", { exact: true }).waitFor();
    await frame.getByRole("button", { name: "Usar como legenda" }).click();
    assert.equal(await frame.locator("#leg").inputValue(), "Sugestão de legenda teste");
    await frame.locator("#titulo").fill("Editorial persistente");
    await frame.locator("#leg").fill("Legenda do teste");
    const png = await page.evaluate(() => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 24;
      canvas.getContext("2d").fillRect(0, 0, 24, 24);
      return canvas.toDataURL("image/png").split(",")[1];
    });
    await frame.locator("#file").setInputFiles({
      name: "fixture.png",
      mimeType: "image/png",
      buffer: Buffer.from(png, "base64"),
    });
    await frame.locator("#media canvas, #media img").first().waitFor();
    await frame.locator("#d4 > summary").click();
    await frame.locator("#save").click();
    await frame
      .locator("#toast")
      .getByText(/Rascunho salvo no neg/)
      .waitFor();
    assert.equal([...records.values()][0].document.image_id, assetId);
    await page.reload();
    await frame.locator("#k1").click();
    const saved = frame.locator("#dg .dc").filter({ hasText: "Editorial persistente" });
    await saved.first().waitFor();
    await saved.first().getByRole("button", { name: "Editar" }).click();
    await frame.getByText("Imagem salva na biblioteca.", { exact: true }).waitFor();
    assert.match(
      await frame.locator("#media img").getAttribute("src"),
      /^data:image\/jpeg;base64,/,
    );
    await frame.locator("#k1").click();
    await saved.first().getByRole("button", { name: "Duplicar" }).click();
    await frame.locator("#dg .dc").nth(1).waitFor();
    assert.equal(records.size, 2);
    assert.ok([...records.values()].every((record) => record.document.image_id === assetId));
    await frame.locator("#dg .dc").first().getByRole("button", { name: "Excluir" }).click();
    await frame.locator("#dg .dc").nth(1).waitFor({ state: "detached" });
    assert.equal(records.size, 1);
    assert.deepEqual(errors, []);
    await page.close();
  }
};
