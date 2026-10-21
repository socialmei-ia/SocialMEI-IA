const assert = require("node:assert/strict");
module.exports = async function paymentDialog(browser, origin) {
  for (const action of ["pagar", "duplicar"]) {
    const page = await browser.newPage({ reducedMotion: "reduce" });
    const sale = {
      id: 31,
      versao: 1,
      cliente_id: 11,
      produto_id: 21,
      cliente: "Cliente fictício",
      item: "Produto fictício",
      data: "2026-10-20",
      quantidade: 2,
      preco: 30,
      desconto: 0,
      valor: 60,
      pagamento: "Pix",
      status: "Pendente",
      importada: false,
      excluida: false,
      estoque_aplicado: true,
    };
    await page.route("**/*", (r) => {
      const u = new URL(r.request().url());
      if (u.origin !== origin) return r.abort();
      if (u.pathname === "/frontend/config.js")
        return r.fulfill({
          contentType: "application/javascript",
          body:
            "const SOCIALMEI_CONFIG=" +
            JSON.stringify({
              n8nMessagesUrl: null,
              vendas: { mode: "remote", apiBaseUrl: origin + "/api/v1", workspaceKey: "qa76" },
              clientes: { mode: "remote", apiBaseUrl: origin + "/api/v1", workspaceKey: "qa76" },
              produtos: { mode: "remote", apiBaseUrl: origin + "/api/v1", workspaceKey: "qa76" },
            }) +
            ";",
        });
      if (u.pathname.startsWith("/api/"))
        return r.fulfill({ json: u.pathname === "/api/v1/vendas" ? [sale] : [] });
      return r.continue();
    });
    try {
      await page.goto(origin + "/frontend/socialmei-app.html");
      await page.waitForFunction(() => appData.vendas.length === 1);
      await page.evaluate((action) => {
        SocialMEIExperience.enterApp("Vendas");
        const hold = () =>
          new Promise((resolve) => {
            window.qaFinishPayment = resolve;
          });
        if (action === "pagar") SocialMEISales.transition = hold;
        else SocialMEISales.duplicate = hold;
        openRecord("sales", 31);
      }, action);
      await page
        .locator(action === "pagar" ? '[data-sale-paid="31"]' : '[data-sale-duplicate="31"]')
        .first()
        .click();
      await page.evaluate(() => closeModal("recordModal"));
      await page.evaluate(() => {
        setView("Financeiro");
        openCreate("receita");
      });
      await page.evaluate(
        async ({ sale, action }) => {
          const saved = {
            ...sale,
            id: action === "pagar" ? 31 : 32,
            status: action === "pagar" ? "Pago" : "Rascunho",
          };
          if (action === "duplicar") appData.vendas.push(saved);
          qaFinishPayment(saved);
          await Promise.resolve();
        },
        { sale, action },
      );
      assert.equal(
        await page.locator("#recordModal").evaluate((e) => e.classList.contains("open")),
        false,
        `A completed ${action} must not reopen a dismissed drawer over a newer form`,
      );
      assert(await page.locator("#createModal").evaluate((e) => e.classList.contains("open")));
      assert(await page.locator("#createSubmit").isEnabled());
    } finally {
      await page.close();
    }
  }
  return "Pagamento/duplicação tardios mantêm drawer fechado e formulário mais recente acessível";
};
