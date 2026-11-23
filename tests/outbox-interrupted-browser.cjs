/* Native controllers, isolated synthetic API, no provider requests or screenshots. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
async function cases(browser, origin) {
  let passed = 0;
  for (const channel of ["wa", "ig"])
    for (const width of [390, 1440])
      for (const theme of ["light", "dark"])
        for (const role of ["owner", "viewer"])
          for (const scenario of role === "owner" ? ["success", "not-interrupted"] : ["success"]) {
            const context = await browser.newContext({
              viewport: { width, height: 1000 },
              reducedMotion: "reduce",
            });
            const page = await context.newPage(),
              errors = [],
              writes = [],
              external = [];
            const identity = {
              usuario: { id: 91, nome: "Operador", email: "operator@example.test" },
              negocio: { id: 17, nome: "Negocio ficticio", slug: "synthetic", configuracao: {} },
              papel: role,
              csrf_token: "a".repeat(64),
            };
            let job = {
              id: "11111111-1111-4111-8111-111111111111",
              conversation_id: 1,
              source_message_id: 11,
              text: "Resposta pendente ficticia",
              revision: 1,
              status: "dispatching",
              attempts: 1,
              provider_message_id: null,
              created_at: "2026-11-21T09:00:00Z",
              claimed_at: "2026-11-21T09:00:00Z",
              finished_at: null,
              updated_at: "2026-11-21T09:00:00Z",
            };
            const routeBase = channel === "wa" ? "/whatsapp/replies" : "/instagram/direct/jobs";
            const panel = channel === "wa" ? "[data-wa-replies]" : "[data-ig-reply]";
            const review = channel === "wa" ? "[data-wa-interrupted]" : "[data-ig-interrupted]";
            await page.addInitScript(() =>
              localStorage.setItem("socialmei-auth-browser-scope", "91:17"),
            );
            page.on("pageerror", (error) => errors.push(error.message));
            page.on("dialog", (dialog) => {
              assert.match(dialog.message(), /ser\u00e1 marcada como incerta/);
              return dialog.accept();
            });
            await page.route("**/*", async (route) => {
              const request = route.request(),
                url = new URL(request.url());
              if (url.origin !== origin) {
                external.push(url.hostname);
                return route.abort();
              }
              if (url.pathname.endsWith("/config.js"))
                return route.fulfill({
                  contentType: "text/javascript",
                  body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
                });
              if (!url.pathname.startsWith("/api/v1/")) return route.continue();
              const key = url.pathname.replace("/api/v1", "");
              if (request.method() === "POST") {
                writes.push(key);
                assert.equal(
                  key,
                  routeBase + "/" + job.id + "/mark-interrupted",
                  "No send/run or other write is allowed",
                );
                assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
                assert.equal(request.headers()["x-socialmei-identity"], "91:17");
                assert.deepEqual(
                  request.postDataJSON(),
                  channel === "wa" ? {} : { expected_revision: 1 },
                );
                assert.equal(role, "owner");
                if (scenario === "not-interrupted")
                  return route.fulfill({
                    status: 409,
                    json: { detail: "Tentativa ainda em andamento; aguarde." },
                  });
                job = { ...job, status: "uncertain", finished_at: "2026-11-21T09:03:00Z" };
                return route.fulfill({ json: job });
              }
              if (key === "/auth/session") return route.fulfill({ json: identity });
              if (key === "/auth/preferences")
                return route.fulfill({ json: { preferences: { theme }, revision: 0 } });
              if (key === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
              if (key === "/message-enrichment/capabilities")
                return route.fulfill({
                  json: {
                    mode: "disabled",
                    workspace_id: 17,
                    waha_inbox: channel === "wa",
                    instagram_inbox: channel === "ig",
                  },
                });
              if (key === "/message-enrichment/conversations")
                return route.fulfill({
                  json: {
                    workspace_id: 17,
                    items: [
                      {
                        id: 1,
                        revision: 1,
                        channel: channel === "wa" ? "whatsapp" : "instagram",
                        origin: channel === "wa" ? "waha" : "instagram",
                        contact_name: "Contato ficticio",
                        messages: [
                          {
                            id: 11,
                            text: "Pergunta ficticia",
                            occurred_at: "2026-11-21T08:59:00Z",
                          },
                        ],
                      },
                    ],
                  },
                });
              if (key === "/integrations/readiness")
                return route.fulfill({
                  json: {
                    instagram: {
                      oauth_available: true,
                      reply_preparation_available: true,
                      incoming_available: true,
                      account_connected: true,
                      send_enabled: false,
                      auto_menu_available: false,
                    },
                  },
                });
              if (key === routeBase)
                return route.fulfill({ json: { items: [job], send_enabled: false } });
              return route.fulfill({ json: [] });
            });
            try {
              await page.goto(origin + "/frontend/socialmei-app.html#/caixa/me-1");
              await page
                .locator(panel + ' select option[value="' + job.id + '"]')
                .waitFor({ state: "attached" });
              await page.locator(panel + " select").selectOption(job.id);
              if (role === "owner") {
                await page.locator(review).focus();
                await page.locator(review).press("Enter");
                if (scenario === "success") {
                  await page.locator(review).waitFor({ state: "hidden" });
                  assert.match(await page.locator(panel + " p").innerText(), /incerto/i);
                  assert.equal(
                    await page
                      .locator(panel + " select")
                      .evaluate((node) => node === document.activeElement),
                    true,
                  );
                } else {
                  await page
                    .locator(panel + " p")
                    .filter({ hasText: /aguarde/i })
                    .waitFor();
                  assert.equal(await page.locator(review).isVisible(), true);
                  assert.equal(
                    await page.locator(review).evaluate((node) => node === document.activeElement),
                    true,
                  );
                }
                assert.equal(writes.length, 1);
                if (channel === "wa")
                  assert.equal(await page.locator("[data-wa-send]").isDisabled(), true);
              } else {
                assert.equal(await page.locator(review).isHidden(), true);
                assert.equal(writes.length, 0);
              }
              assert.equal(job.provider_message_id, null);
              assert.deepEqual(errors, []);
              assert.deepEqual(external, []);
              assert.equal(
                await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
                true,
              );
              passed++;
            } finally {
              await context.close();
            }
          }
  return { cases: passed, external_messages_sent: 0 };
}
module.exports = cases;
if (require.main === module) {
  const server = http.createServer((req, res) => {
    const file = path.resolve(root, "." + new URL(req.url, "http://localhost").pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())
      return res.writeHead(404).end();
    res.setHeader(
      "Content-Type",
      {
        ".js": "text/javascript",
        ".html": "text/html",
        ".css": "text/css",
        ".png": "image/png",
        ".woff2": "font/woff2",
      }[path.extname(file)] || "application/octet-stream",
    );
    fs.createReadStream(file).pipe(res);
  });
  (async () => {
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const browser = await chromium.launch(
      process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
    );
    try {
      console.log(
        JSON.stringify(await cases(browser, `http://127.0.0.1:${server.address().port}`)),
      );
    } finally {
      await browser.close();
      server.close();
    }
  })().catch((error) => {
    console.error(error);
    server.close();
    process.exitCode = 1;
  });
}
