const assert = require("node:assert/strict");

module.exports = async (browser, origin) => {
  for (const width of [390, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 850 }, acceptDownloads: true });
    const errors = [];
    const writes = [];
    const identity = {
      usuario: { id: 91, nome: "Pessoa teste", email: "fixture@example.test" },
      negocio: { id: 17, nome: "Negocio teste", slug: "fixture", configuracao: {} },
      papel: "owner",
      csrf_token: "a".repeat(64),
    };
    let entries = [
      {
        id: 1,
        descricao: "Sem data de caixa",
        tipo: "receita",
        vencimento: "2026-01-02",
        valor: 570,
        data_pagamento: null,
        status: "pago",
        versao: 1,
      },
    ];
    const period = { start: "2026-11-01", end: "2026-11-30", timezone: "America/Recife" };
    const paid = { count: 1, incoming: "20.00", outgoing: "3.00", balance: "17.00" };
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
    await page.route("**/*", (route) => {
      const req = route.request(),
        u = new URL(req.url());
      if (u.origin !== origin) return route.abort();
      if (u.pathname.endsWith("/config.js"))
        return route.fulfill({
          contentType: "text/javascript",
          body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
        });
      if (!u.pathname.startsWith("/api/v1/")) return route.continue();
      const path = u.pathname.replace("/api/v1", "");
      let json = [];
      if (path === "/auth/session") json = identity;
      if (path === "/auth/preferences") json = { preferences: { theme: "dark" }, revision: 0 };
      if (path === "/workspace-profile") json = { profile: {} };
      if (path === "/message-enrichment/capabilities") json = { mode: "disabled" };
      if (path === "/produtos")
        json = [
          {
            id: 9,
            nome: "Limpeza",
            tipo: "Serviço",
            categoria: "Serviços",
            status: "Ativo",
            preco: 40,
            estoque: 0,
          },
        ];
      if (path === "/clientes")
        json = [
          {
            id: 4,
            nome: "Cliente teste",
            email: "",
            telefone: "85955550123",
            instagram: "contatoteste",
            tags: [],
          },
        ];
      if (path === "/financeiro" && req.method() === "POST") {
        const data = req.postDataJSON();
        writes.push(data);
        json = { ...data, id: 2, versao: 1, data_pagamento: null };
        entries.push(json);
      } else if (path === "/financeiro") json = entries;
      if (path === "/financeiro/2/liquidacoes") {
        const item = req.postDataJSON();
        writes.push(item);
        entries[1] = {
          ...entries[1],
          versao: 2,
          liquidado_parcial: "10.00",
          parcelas: [{ valor: "10.00", data: item.data }],
        };
        json = entries[1];
      }
      if (path === "/financeiro/2/pagar") {
        writes.push(req.postDataJSON());
        entries[1] = {
          ...entries[1],
          status: "pago",
          versao: 3,
          liquidado_parcial: "29.50",
          data_pagamento: "2026-11-27",
          parcelas: [...entries[1].parcelas, { valor: "19.50", data: "2026-11-27" }],
        };
        json = entries[1];
      }
      if (path === "/reporting/finance")
        json = {
          workspace_id: 17,
          period,
          paid,
          previous: { start: "2026-10-01", end: "2026-10-31", ...paid },
          balance_change: "0.00",
          pending: { incoming: "3.00", outgoing: "5.00" },
          overdue: { incoming: "3.00", outgoing: "5.00", count: 2, as_of: "2026-11-30" },
          daily: [{ date: "2026-11-01", ...paid }],
          undated_paid_count: 1,
          description: "",
          pending_description: "",
        };
      if (path === "/reporting/mei")
        json = {
          workspace_id: 17,
          year: 2026,
          opened_on: "2026-06-01",
          revision: 1,
          system_sales: "100.00",
          estimate: "100.00",
          limit: "47250.00",
          level: "below",
          limit_source: "https://example.test/",
          source_note: "",
        };
      return route.fulfill({ json });
    });
    const base = origin + "/frontend/socialmei-app.html";
    await page.goto(base + "#/negocio/financeiro");
    await page.getByRole("heading", { name: "Contas em aberto" }).waitFor();
    assert.equal(await page.getByText("Sem data de caixa", { exact: true }).count(), 0);
    await page.locator('button[data-a="novo:lanc"]').first().click();
    const form = page.locator("dialog[open]");
    await form.locator("#f_d").fill("Conta futura de teste");
    await form.locator("#f_v").fill("29,50");
    await form.locator("#f_cc").fill("Material");
    await form.locator("#f_due").fill("2026-12-07");
    await form.locator("button[type=submit]").click();
    await page.getByText(/^A receber .*Conta futura de teste/).waitFor();
    assert.equal(writes[0].status, "aberto");
    assert.equal(writes[0].categoria, "Material");
    assert.equal(writes[0].vencimento, "2026-12-07");
    await page.getByRole("button", { name: "Registrar parcela" }).click();
    await form.locator("#f_v").fill("10,00");
    await form.locator("#f_pd").fill("2026-11-26");
    await form.locator("button[type=submit]").click();
    await page.getByText(/^A receber .*19,50 em aberto/).waitFor();
    assert.equal(writes[1].valor, "10");
    assert.equal(writes[1].expected_version, 1);
    page.once("dialog", (dlg) => dlg.accept());
    await page.getByRole("button", { name: "Registrar recebimento" }).click();
    await page.getByText("Nenhuma conta a pagar ou a receber.").waitFor();
    assert.equal(writes[2].expected_version, 2);

    await page.evaluate(() => {
      location.hash = "/relatorios";
    });
    await page.getByText(/Recebimentos em atraso/).waitFor();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Exportar financeiro em CSV" }).click(),
    ]);
    assert.match(download.suggestedFilename(), /financeiro-2026-11-01/);
    await page.evaluate(() => window.SocialMEILia.ask("Contas em atraso"));
    await page.locator(".lia-panel").getByText("A receber em atraso", { exact: true }).waitFor();
    await page.evaluate(() => window.SocialMEILia.ask("Preço de Limpeza"));
    await page.locator(".lia-panel").getByText("Limpeza", { exact: true }).waitFor();
    await page.evaluate(() => window.SocialMEILia.close());

    await page.evaluate(() => {
      location.hash = "/negocio/resumo";
    });
    await page.getByText(/Limite de refer/).waitFor();
    await page.keyboard.press("Control+k");
    await page.locator("#pal-in").fill("95555-0123");
    await page.locator("#pal-ul").getByText("Cliente teste").waitFor();
    await page.locator("#pal-in").fill("contatoteste");
    await page.locator("#pal-ul").getByText("Cliente teste").click();
    await page.waitForURL(/#\/negocio\/clientes$/);
    identity.papel = "viewer";
    await page.goto(base + "?viewer=1#/negocio/financeiro");
    await page.getByRole("heading", { name: "Contas em aberto" }).waitFor();
    assert.ok(await page.locator('button[data-a="novo:lanc"]').first().isDisabled());
    assert.equal(writes.length, 3);
    assert.deepEqual(errors, []);
    await page.close();
  }
};
