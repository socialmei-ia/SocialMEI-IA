/* Real V22 shell, synthetic authenticated PDF/report API; no external provider. */
const assert = require("node:assert/strict");

module.exports = async function v22KnowledgeReporting(browser, origin) {
  const page = await browser.newPage({
    viewport: { width: 390, height: 880 },
    reducedMotion: "reduce",
    acceptDownloads: true,
  });
  const errors = [];
  const uploads = [];
  const identity = {
    usuario: { id: 87, nome: "Empresa Teste", email: "teste@example.test" },
    negocio: { id: 91, slug: "empresa-teste", nome: "Negócio Teste", configuracao: {} },
    papel: "owner",
    csrf_token: "b".repeat(64),
  };
  let stored = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    localStorage.setItem("socialmei-auth-browser-scope", "87:91");
  });
  await page.route("**/*", (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === "/frontend/config.js") {
      return route.fulfill({
        contentType: "text/javascript",
        body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
      });
    }
    if (!url.pathname.startsWith("/api/v1/")) return route.continue();
    const endpoint = url.pathname.slice("/api/v1".length);
    if (endpoint === "/auth/session") return route.fulfill({ json: identity });
    if (endpoint === "/auth/preferences") {
      return route.fulfill({ json: { revision: 0, preferences: {} } });
    }
    if (endpoint === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
    if (endpoint === "/message-enrichment/capabilities") {
      return route.fulfill({ json: { mode: "disabled" } });
    }
    if (endpoint === "/knowledge/pdf") {
      if (request.method() === "POST") {
        assert.equal(request.headers()["x-socialmei-csrf"], "b".repeat(64));
        assert.equal(request.headers()["x-socialmei-identity"], "87:91");
        assert.match(request.headers()["content-type"], /application\/pdf/);
        assert.equal(url.searchParams.get("filename"), "cliente.pdf");
        uploads.push(request.postDataBuffer());
        stored = [
          {
            id: "11111111-1111-4111-8111-111111111111",
            filename: "cliente.pdf",
            page_count: 2,
            status: "indexed",
          },
        ];
        return route.fulfill({ status: 201, json: stored[0] });
      }
      return route.fulfill({ json: { items: stored } });
    }
    if (endpoint === "/knowledge/pdf/search") {
      return route.fulfill({
        json: {
          items: [
            {
              document_id: "11111111-1111-4111-8111-111111111111",
              filename: "cliente.pdf",
              page: 2,
              excerpt: "Prazo de entrega: 5 dias úteis.",
            },
          ],
        },
      });
    }
    if (endpoint === "/reporting/overview") {
      return route.fulfill({
        json: { period_days: 30, totals: { clientes: 6, itens_ativos: 3, estoque_baixo: 1 } },
      });
    }
    if (endpoint === "/reporting/overview.csv") {
      return route.fulfill({
        status: 200,
        contentType: "text/csv",
        headers: { "Content-Disposition": 'attachment; filename="socialmei-relatorio.csv"' },
        body: "Secao,Quantidade\nClientes,6\n",
      });
    }
    return route.fulfill({ json: [] });
  });
  try {
    await page.goto(origin + "/frontend/socialmei-app.html#/config/ia");
    await page.locator("[data-sm-knowledge]").waitFor();
    assert.match(await page.locator("[data-sm-knowledge]").innerText(), /Documentos da IA/);
    assert.match(await page.locator("[data-sm-knowledge]").innerText(), /Nenhum PDF cadastrado/);
    await page.locator("[data-sm-knowledge] input[type=file]").setInputFiles({
      name: "cliente.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.7 synthetic only"),
    });
    await page
      .locator("[data-sm-knowledge]")
      .getByRole("button", { name: "Adicionar PDF" })
      .click();
    await page.getByText(/Documento indexado/).waitFor();
    assert.equal(uploads.length, 1);
    assert.match(await page.locator("[data-sm-knowledge]").innerText(), /cliente.pdf/);
    await page.locator("[data-sm-knowledge] input[type=search]").fill("prazo");
    await page.getByRole("button", { name: "Buscar", exact: true }).click();
    await page.getByText(/Prazo de entrega: 5 dias úteis/).waitFor();

    await page.evaluate(() => go("/relatorios"));
    await page.locator("[data-sm-reports]").waitFor();
    await page.getByText("6 clientes").waitFor();
    const pending = page.waitForEvent("download");
    await page.getByRole("button", { name: "Exportar CSV" }).click();
    const download = await pending;
    assert.equal(download.suggestedFilename(), "socialmei-relatorio.csv");
    assert.deepEqual(errors, []);
  } finally {
    await page.close();
  }
};
