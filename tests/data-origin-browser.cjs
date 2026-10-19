const assert = require("node:assert/strict");

module.exports = async function dataOriginFlows(browser, origin, errors = []) {
  for (const mode of ["local", "remote", "hybrid", "unavailable"]) {
    const page = await browser.newPage({
      viewport: { width: 390, height: 844 },
      reducedMotion: "reduce",
    });
    page.on("pageerror", (error) => errors.push(error.message));
    const remote = { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "team" };
    const config = {
      n8nMessagesUrl: null,
      auth: { mode: "local" },
      clientes: mode === "local" ? { mode: "local" } : remote,
      produtos: mode === "remote" || mode === "unavailable" ? remote : { mode: "local" },
      vendas: mode === "remote" || mode === "unavailable" ? remote : { mode: "local" },
      financeiro: mode === "remote" || mode === "unavailable" ? remote : { mode: "local" },
    };
    await page.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) return route.abort();
      if (url.pathname === "/frontend/config.js")
        return route.fulfill({
          contentType: "text/javascript",
          body: "const SOCIALMEI_CONFIG = " + JSON.stringify(config) + ";",
        });
      if (url.pathname.startsWith("/api/v1/")) {
        assert.equal(route.request().method(), "GET");
        return route.fulfill({ status: mode === "unavailable" ? 503 : 200, json: [] });
      }
      return route.continue();
    });
    try {
      await page.goto(origin + "/frontend/socialmei-app.html");
      await page.evaluate(() => SocialMEIExperience.enterApp("Relatórios"));
      const expected =
        mode === "local"
          ? "Dados locais"
          : mode === "hybrid"
            ? "Fontes mistas"
            : "Dados compartilhados";
      // Business views use their own visible source disclosure; the global footer is omitted.
      assert.match(await page.locator("#appDataOrigin").textContent(), new RegExp(expected));
      await page.waitForFunction(() =>
        [SocialMEIClients, SocialMEIProducts, SocialMEISales, SocialMEIFinance].every((store) =>
          ["local", "ready", "unavailable"].includes(store.connectionState),
        ),
      );
      const sourceDetails = page.locator("#reportsView .rv2-source-details");
      if (!(await sourceDetails.evaluate((details) => details.open)))
        await sourceDetails.locator("summary").click();
      assert.match(
        await page.locator("#reportsDataSourceStatus").innerText(),
        new RegExp(expected),
      );
      assert(
        !/autenticação externa|Modo demonstração/.test(
          await page.locator("#reportsView").innerText(),
        ),
      );
      if (mode === "remote") {
        await page.waitForFunction(
          () => !appData.clientes.length && !appData.vendas.length && !appData.financeiro.length,
        );
        await page.getByRole("tab", { name: "Clientes", exact: true }).click();
        assert.match(await page.locator("#reportsGrid").innerText(), /Nenhum cliente cadastrado/);
      }
      if (mode === "unavailable") {
        await page.waitForFunction(() =>
          document.getElementById("clientsSourceStatus").textContent.includes("indisponível"),
        );
        assert(!/conectado/.test(await page.locator("#appDataOrigin").innerText()));
        assert.match(await page.locator("#reportsDataSourceStatus").innerText(), /indisponível/);
        assert.equal(
          await page.locator("#nvReportKpis .management-kpi >b").first().innerText(),
          "—",
        );
      }
      await page.evaluate(() => setView("Automações"));
      await page.locator("#contextHelpButton").click();
      await page.locator("#contextHelpSources > .context-help:not([hidden]) > summary").click();
      assert.match(
        await page.locator("#contextHelpSources > .context-help:not([hidden])").innerText(),
        /Salvar não agenda execuções nem envia mensagens/,
      );
      await page.keyboard.press("Escape");
      await page.waitForFunction(
        () => !document.getElementById("contextHelpModal").classList.contains("open"),
      );
      await page.evaluate(() => syncN8nMessages());
      assert.equal(
        await page.locator("#topSync").innerText(),
        "Integração de mensagens não configurada",
      );
    } finally {
      await page.close();
    }
  }
  return "Origem dos dados: local, remota, híbrida e API indisponível; vazio não é cadastro sem data";
};
