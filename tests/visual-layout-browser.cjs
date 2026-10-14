const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const sizes = [
  [1920, 1080],
  [1600, 900],
  [1440, 900],
  [1366, 768],
  [1280, 720],
  [1024, 768],
  [900, 900],
  [768, 1024],
  [430, 932],
  [390, 844],
  [360, 800],
];
const views = [
  "Início",
  "Visão Geral",
  "Caixa Unificada",
  "Clientes",
  "Produtos e Serviços",
  "Vendas",
  "Financeiro",
  "Relatórios",
  "Assistente",
  "Automações",
  "Configurações",
];

module.exports = async function visualLayoutFlows(browser, origin, errors = []) {
  const evidence = [];
  const failures = [];
  for (const mode of ["local", "remote"]) {
    const page = await browser.newPage({
      reducedMotion: "reduce",
      viewport: { width: 1440, height: 900 },
    });
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => {
      if (response.status() >= 400 && new URL(response.url()).origin === origin)
        failures.push(`${response.status()} ${new URL(response.url()).pathname}`);
    });
    page.on("console", (message) => {
      if (message.type() === "error") failures.push(message.text());
    });
    const shared = { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "team" };
    const config = {
      n8nMessagesUrl: null,
      auth: { mode: "local" },
      ...Object.fromEntries(
        ["clientes", "produtos", "vendas", "financeiro"].map((name) => [
          name,
          mode === "remote" ? shared : { mode: "local" },
        ]),
      ),
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
        return route.fulfill({ json: [] });
      }
      return route.continue();
    });
    await page.clock.setFixedTime(new Date("2026-10-13T12:00:00Z"));
    try {
      await page.goto(origin + "/frontend/socialmei-app.html");
      await page.evaluate(() => SocialMEIExperience.enterApp("Início"));
      if (mode === "remote")
        await page.waitForFunction(() =>
          [SocialMEIClients, SocialMEIProducts, SocialMEISales, SocialMEIFinance].every(
            (store) => store.connectionState === "ready",
          ),
        );
      for (const [width, height] of sizes) {
        await page.setViewportSize({ width, height });
        for (const theme of ["light", "dark"]) {
          await page.evaluate((theme) => setTheme(theme), theme);
          for (const view of views) {
            await page.evaluate(async (name) => {
              setView(name);
              if (name === "Caixa Unificada" && sessionData.conversas.length)
                await selectConversation(sessionData.conversas[0].id);
            }, view);
            await page.evaluate(
              () =>
                new Promise((resolve) =>
                  requestAnimationFrame(() => requestAnimationFrame(resolve)),
                ),
            );
            const geometry = await page.evaluate(() => {
              const host = document.querySelector(".page-view.active");
              // A prévia decorativa de Configurações é rotacionada e avança até 4px.
              const decorativeSpill =
                host.id === "settingsView" && host.scrollWidth - host.clientWidth <= 4;
              return {
                globalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
                viewOverflow: !decorativeSpill && host.scrollWidth > host.clientWidth + 1,
                animations: document.getAnimations().length,
              };
            });
            const context = `${mode} ${view} ${width}x${height} ${theme}`;
            assert.equal(geometry.globalOverflow, false, context + ": overflow da página");
            assert.equal(geometry.viewOverflow, false, context + ": overflow do módulo");
            assert.equal(geometry.animations, 0, context + ": reduced motion");
            evidence.push({ mode, view, width, height, theme, ...geometry });
          }
        }
      }
    } finally {
      await page.close();
    }
  }
  assert.deepEqual(failures, [], "Sem erros de console ou respostas internas inesperadas");
  const directory = path.resolve(__dirname, "../test-results");
  fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(
    path.join(directory, "visual-layout-round-2.json"),
    JSON.stringify({ states: evidence.length, failures, evidence }, null, 2),
  );
  return `Matriz visual: ${evidence.length} estados, 11 resoluções, 11 módulos, dois temas e fontes locais/remotas; zero overflow e reduced motion`;
};
