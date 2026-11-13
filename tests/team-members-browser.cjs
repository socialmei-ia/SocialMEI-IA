// Existing-account team UI with controlled transport. No real users or sends.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
async function run(browser, origin) {
  for (const width of [390, 1440])
    for (const theme of ["light", "dark"]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const page = await context.newPage();
      const errors = [],
        writes = [],
        external = [];
      const inviteWrites = [];
      let role = "owner";
      let records = [
        {
          id: 91,
          nome: "Responsável fictício",
          email: "owner@example.test",
          role: "owner",
          ativo: true,
        },
      ];
      const identity = {
        usuario: { id: 91, nome: "Responsável fictício", email: "owner@example.test" },
        negocio: { id: 17, nome: "Negócio fictício", slug: "fixture", configuracao: {} },
        papel: "owner",
        csrf_token: "a".repeat(64),
      };
      page.on("pageerror", (e) => errors.push(e.message));
      page.on("dialog", (dialog) => dialog.accept());
      await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
      await page.route("**/*", async (route) => {
        const request = route.request(),
          url = new URL(request.url()),
          method = request.method(),
          p = url.pathname.replace("/api/v1", "");
        if (url.origin !== origin) {
          external.push("external");
          return route.abort();
        }
        if (url.pathname.endsWith("/config.js"))
          return route.fulfill({
            contentType: "application/javascript",
            body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
          });
        if (!url.pathname.startsWith("/api/v1/")) return route.continue();
        if (p === "/auth/session") return route.fulfill({ json: { ...identity, papel: role } });
        if (p === "/auth/preferences")
          return route.fulfill({ json: { preferences: { theme }, revision: 0 } });
        if (p === "/workspace-profile") return route.fulfill({ json: { profile: {} } });
        if (p === "/auth/workspaces")
          return route.fulfill({
            json: { active_workspace_id: 17, items: [{ id: 17, nome: "Negócio fictício", role }] },
          });
        if (p === "/message-enrichment/capabilities")
          return route.fulfill({ json: { mode: "disabled" } });
        if (p === "/team/invitations" && method === "GET")
          return route.fulfill({
            json: {
              items: [
                {
                  id: "00000000-0000-4000-8000-000000000001",
                  email: "admin-invited@example.test",
                  role: "admin",
                  status: "used",
                },
              ],
            },
          });
        if (p.startsWith("/team/invitations") && method !== "GET") {
          assert.equal(request.headers()["x-socialmei-identity"], "91:17");
          assert.equal(request.headers()["x-socialmei-csrf"], identity.csrf_token);
          inviteWrites.push({ path: p, method, data: request.postDataJSON() });
          return route.fulfill(
            method === "POST"
              ? { status: 202, json: { id: "00000000-0000-4000-8000-000000000002", queued: true } }
              : { status: 204, body: "" },
          );
        }
        if (p === "/team/members" && method === "GET")
          return route.fulfill({
            json: {
              items: records,
              workspace_id: 17,
              can_manage: role === "owner",
              truncated: false,
            },
          });
        if (p.startsWith("/team/members") && method !== "GET") {
          const data = request.postDataJSON();
          assert.equal(request.headers()["x-socialmei-identity"], "91:17");
          assert.equal(request.headers()["x-socialmei-csrf"], identity.csrf_token);
          writes.push({ path: p, method, data });
          if (method === "POST") {
            if (data.email !== "person@example.test")
              return route.fulfill({
                status: 409,
                json: {
                  detail:
                    "Use uma conta SocialMEI já cadastrada e ativa. Nenhum convite será enviado.",
                },
              });
            records.push({
              id: 92,
              nome: "Colaboradora fictícia",
              email: data.email,
              role: data.role,
              ativo: true,
            });
            return route.fulfill({ json: { granted: true, already_member: false } });
          }
          if (method === "PATCH") {
            records[1].role = data.role;
            return route.fulfill({ json: { changed: true } });
          }
          if (method === "DELETE") {
            records = records.filter((r) => r.id !== 92);
            return route.fulfill({ status: 204, body: "" });
          }
        }
        return route.fulfill({ json: [] });
      });
      try {
        await page.goto(origin + "/frontend/socialmei-app.html#/config/conta");
        const panel = page.locator("[data-team-members]");
        await panel.getByText("Responsável fictício", { exact: true }).waitFor();
        assert.equal(
          await panel.getByRole("button", { name: "Revogar acesso", exact: true }).count(),
          0,
        );
        await panel.getByLabel("E-mail da conta existente").fill("missing@example.test");
        await panel.getByRole("button", { name: "Adicionar à equipe", exact: true }).click();
        await panel.getByText(/Use uma conta SocialMEI já cadastrada/).waitFor();
        await panel.getByLabel("E-mail da conta existente").fill("person@example.test");
        await panel.getByRole("button", { name: "Adicionar à equipe", exact: true }).click();
        await panel.getByText("Colaboradora fictícia", { exact: true }).waitFor();
        await page.reload();
        await panel.getByText("Colaboradora fictícia", { exact: true }).waitFor();
        await panel.getByLabel("Acesso de Colaboradora fictícia").selectOption("report_viewer");
        await panel.getByRole("button", { name: "Alterar acesso", exact: true }).click();
        await panel
          .getByText("Acesso alterado. A pessoa deverá entrar novamente neste negócio.", {
            exact: true,
          })
          .waitFor();
        assert.equal(records[1].role, "report_viewer");
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        fs.mkdirSync(path.join(__dirname, "../test-results/team"), { recursive: true });
        await page.screenshot({
          path: path.join(__dirname, `../test-results/team/equipe-${width}-${theme}.png`),
          fullPage: true,
        });
        await panel.getByRole("button", { name: "Revogar acesso", exact: true }).click();
        await panel.getByText("Acesso revogado neste negócio.", { exact: true }).waitFor();
        assert.equal(records.length, 1);
        await panel.getByRole("button", { name: "Convidar por e-mail", exact: true }).click();
        await panel
          .getByRole("button", { name: "Revogar acesso deste convite", exact: true })
          .click();
        await panel
          .getByLabel("E-mail do convidado", { exact: true })
          .fill("new-employee@example.test");
        await panel.getByLabel("Permissão a conceder", { exact: true }).selectOption("member");
        await panel.getByRole("button", { name: "Enviar convite", exact: true }).click();
        await panel
          .getByText("Convite registrado na fila de e-mail. Isso ainda não concede acesso.", {
            exact: true,
          })
          .waitFor();
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        await page.screenshot({
          path: path.join(__dirname, `../test-results/team/convites-${width}-${theme}.png`),
          fullPage: true,
        });
        await panel.getByRole("button", { name: "Revogar convite", exact: true }).click();
        assert.equal(inviteWrites.length, 3);
        assert.equal(inviteWrites[0].data.expected_role, "admin");
        assert.equal(inviteWrites[1].data.email, "new-employee@example.test");
        assert(inviteWrites[2].path.endsWith("000000000002"));
        role = "admin";
        await page.reload();
        await panel
          .getByText("Somente o proprietário pode adicionar, alterar ou revogar integrantes.", {
            exact: true,
          })
          .waitFor();
        assert.equal(
          await panel.getByRole("button", { name: "Adicionar à equipe", exact: true }).count(),
          0,
        );
        assert.equal(writes.length, 4);
        assert.equal(
          await panel.getByRole("button", { name: "Convidar por e-mail", exact: true }).count(),
          0,
        );
        assert.deepEqual(errors, []);
        assert.deepEqual(external, []);
      } finally {
        await context.close();
      }
    }
  console.log(
    "Equipe: grant existing account, reload, owner protection, role change, revoke, admin read-only, CSRF/identity, mobile/desktop/light/dark PASS (controlled transport).",
  );
}
module.exports = run;
if (require.main === module) {
  const root = path.resolve(__dirname, ".."),
    server = http.createServer((req, res) => {
      let file;
      try {
        file = path.resolve(root, "." + new URL(req.url, "http://localhost").pathname);
      } catch {
        return res.writeHead(400).end();
      }
      if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())
        return res.writeHead(404).end();
      res.setHeader(
        "Content-Type",
        { ".js": "text/javascript", ".html": "text/html", ".css": "text/css", ".png": "image/png" }[
          path.extname(file)
        ] || "application/octet-stream",
      );
      fs.createReadStream(file).pipe(res);
    });
  (async () => {
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    const browser = await chromium.launch();
    try {
      await run(browser, `http://127.0.0.1:${server.address().port}`);
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
