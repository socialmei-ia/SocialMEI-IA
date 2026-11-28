// Serve candidate assets in a browser against the live API without replacing the public site.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const origin = "https://socialmei-ia.54-94-213-7.sslip.io";
const routes = [
  "inicio", "caixa", "agenda", "oport", "divul", "negocio",
  "negocio/clientes", "negocio/vendas", "negocio/produtos",
  "negocio/financeiro", "catalogo", "automacoes", "relatorios", "config",
];
const authWrites = new Set([
  "/api/v1/auth/login", "/api/v1/auth/workspaces/switch", "/api/v1/auth/logout",
]);

async function run() {
  const credentials = JSON.parse(fs.readFileSync(process.env.SOCIALMEI_TEST_ACCOUNT, "utf8").replace(/^\uFEFF/, ""));
  const stage = process.env.SOCIALMEI_PREMIUM_STAGE;
  const browser = await chromium.launch({ channel: "chrome" });
  let count = 0;
  try {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      const context = await browser.newContext({ viewport });
      try {
        const page = await context.newPage();
        const failures = [];
        page.on("pageerror", (error) => failures.push(error.name));
        page.on("response", (response) => {
          const url = new URL(response.url());
          if (url.origin === origin && response.status() >= 400 &&
              /\.(html|js|css|woff2)$/.test(url.pathname))
            failures.push(`${response.status()} ${url.pathname}`);
        });
        await context.route("**/*", async (route) => {
          const request = route.request();
          const url = new URL(request.url());
          if (url.origin !== origin) return route.abort();
          if (url.pathname.startsWith("/api/")) {
            if (["GET", "HEAD"].includes(request.method()) || authWrites.has(url.pathname))
              return route.continue();
            return route.fulfill({ status: 403, json: { detail: "Somente leitura" } });
          }
          if (!stage || url.pathname === "/frontend/config.js") return route.continue();
          const rel = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/frontend\//, "");
          if (!rel || rel.startsWith("/") || rel.split("/").includes(".."))
            return route.fulfill({ status: 404 });
          const filename = path.join(stage, rel);
          if (!fs.existsSync(filename) || !fs.statSync(filename).isFile())
            return route.fulfill({ status: 404 });
          return route.fulfill({ path: filename });
        });
        await page.goto(origin + "/frontend/entrada.html");
        await page.waitForFunction(() => window.SocialMEIAuth?.login);
        const active = await page.evaluate(async (data) => {
          await window.SocialMEIAuth.ready;
          const identity = await window.SocialMEIAuth.login(data);
          return identity.negocio.id;
        }, credentials);
        assert.ok([60, 61].includes(active), "Unexpected initial workspace");
        for (const workspace of [active, active === 60 ? 61 : 60]) {
          await page.goto(origin + "/frontend/socialmei-app.html#/inicio");
          await page.waitForFunction(() => window.SocialMEIV22?.remote && window.SocialMEIVersion === "7.9.11");
          if (workspace !== active) {
            await page.evaluate((workspaceId) => window.SocialMEIAuth.switchWorkspace(workspaceId), workspace);
            await page.waitForFunction((workspaceId) => window.SocialMEIVersion === "7.9.11" &&
              window.SocialMEIV22?.remote && window.SocialMEIAuth?.current?.negocio.id === workspaceId, workspace);
          }
          for (const name of routes) {
            const previous = await page.evaluate(() => ({
              hash: location.hash, markup: document.querySelector("#v")?.innerHTML,
            }));
            await page.evaluate((name) => { location.hash = "#/" + name; }, name);
            await page.waitForFunction(({ name, previous }) => {
              const view = document.querySelector("#v");
              return location.hash === "#/" + name && view?.textContent.trim().length > 0 &&
                (previous.hash === location.hash || previous.markup !== view.innerHTML ||
                  view.querySelector("iframe"));
            }, { name, previous });
            const width = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
            assert.ok(width < 3, `Horizontal overflow at ${viewport.width}px: ${name}`);
            assert.equal(await page.evaluate(() => window.SocialMEIAuth.current.negocio.id), workspace);
            count++;
          }
        }
        assert.deepEqual(failures, []);
        await page.evaluate(() => window.SocialMEIAuth.logout());
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
  console.log(`${count} authenticated route checks on workspaces 60 and 61`);
}

run().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
