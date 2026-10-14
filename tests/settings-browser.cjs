const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const resultDirectory = path.join(root, "test-results/settings");
const contentTypes = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".woff2": "font/woff2",
  ".png": "image/png",
};
const sections = [
  "conta",
  "negocio",
  "aparencia",
  "notificacoes",
  "integracoes",
  "equipe",
  "plano",
  "seguranca",
  "dados",
];
const server = http.createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const file = path.resolve(root, "." + pathname);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    response.writeHead(404).end();
    return;
  }
  response.setHeader(
    "Content-Type",
    contentTypes[path.extname(file)] || "application/octet-stream",
  );
  fs.createReadStream(file).pipe(response);
});

async function selectSection(page, section) {
  await page.locator(`[data-settings-tab="${section}"]`).click();
  await page.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
  );
}

async function run() {
  fs.mkdirSync(resultDirectory, { recursive: true });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const errors = [];
  const missingResources = [];
  let browser;
  let states = 0;
  try {
    browser = await chromium.launch(
      process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
    );
    for (const mode of ["local", "remote"]) {
      const page = await browser.newPage({
        reducedMotion: "reduce",
        viewport: { width: 1440, height: 1000 },
      });
      const profileRequests = [];
      const identity = {
        usuario: {
          id: 1,
          nome: "Beatriz Souza",
          email: "beatriz@example.com",
          telefone: "11999990000",
          administrador_plataforma: true,
        },
        negocio: { id: 1, slug: "studio", nome: "Studio Flor de Lis", configuracao: {} },
        papel: "owner",
        csrf_token: "a".repeat(64),
      };
      // O escopo conhecido evita apenas o reload inicial da fixture; a vinculação real é testada em account-browser.
      if (mode === "remote")
        await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "1:1"));
      page.on("pageerror", (error) => errors.push(error.name));
      page.on("response", (response) => {
        if (new URL(response.url()).origin === origin && response.status() >= 400) {
          missingResources.push(new URL(response.url()).pathname);
        }
      });
      await page.route("**/*", async (route) => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.origin !== origin) return route.abort();
        if (mode === "remote" && url.pathname === "/frontend/config.js") {
          const shared = { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "team" };
          return route.fulfill({
            contentType: "text/javascript",
            body:
              "const SOCIALMEI_CONFIG=" +
              JSON.stringify({
                n8nMessagesUrl: null,
                auth: { mode: "remote", apiBaseUrl: "/api/v1" },
                clientes: shared,
                produtos: shared,
                vendas: shared,
                financeiro: shared,
              }) +
              ";",
          });
        }
        if (url.pathname === "/api/v1/auth/profile") {
          assert.equal(request.method(), "PATCH");
          assert.equal(request.headers()["x-socialmei-csrf"], identity.csrf_token);
          const body = request.postDataJSON();
          profileRequests.push(body);
          identity.usuario.nome = body.nome || identity.usuario.nome;
          identity.usuario.telefone = body.telefone ?? identity.usuario.telefone;
          return route.fulfill({ json: identity });
        }
        if (url.pathname.startsWith("/api/v1/"))
          return route.fulfill({ json: url.pathname === "/api/v1/auth/me" ? identity : [] });
        return route.continue();
      });
      await page.clock.setFixedTime(new Date("2026-10-13T12:00:00Z"));
      await page.goto(origin + "/frontend/socialmei-app.html");
      if (mode === "remote")
        await page.waitForFunction(
          () => window.SocialMEIAuth?.current && document.body.classList.contains("experience-app"),
        );
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(() => {
        SocialMEIExperience.enterApp("Configurações");
        setView("Configurações");
      });
      const customId = await page.evaluate(
        () =>
          SocialMEIThemes.save({
            version: 1,
            name: "Settings QA",
            base: "dark",
            primary: "#2255BB",
            accent: "#FFCC00",
            intensity: 35,
            overrides: {},
          }).id,
      );

      for (const width of [1920, 1600, 1440, 1366, 1280, 1024, 900, 768, 430, 390, 360]) {
        await page.setViewportSize({ width, height: 1000 });
        for (const theme of ["light", "dark", "auto-light", "auto-dark", "custom"]) {
          await page.emulateMedia({
            colorScheme: ["dark", "auto-dark", "custom"].includes(theme) ? "dark" : "light",
          });
          await page.evaluate(
            ({ theme, customId }) =>
              theme === "custom"
                ? SocialMEIThemes.select(customId)
                : setTheme(theme.startsWith("auto") ? "auto" : theme),
            { theme, customId },
          );
          for (const section of sections) {
            await selectSection(page, section);
            const state = await page.evaluate(() => {
              const host = document.getElementById("settingsPanel");
              const ids = [...host.querySelectorAll("[id]")].map((element) => element.id);
              return {
                overflow:
                  document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
                current: document.querySelector('[data-settings-tab][aria-current="page"]').dataset
                  .settingsTab,
                activeCount: document.querySelectorAll('[data-settings-tab][aria-current="page"]')
                  .length,
                section: host.dataset.settingsSection,
                bodies: host.querySelectorAll(".settings-panel-body").length,
                duplicateIds: ids.filter((id, index) => ids.indexOf(id) !== index),
                animations: document.getAnimations().length,
                unnamedButtons: [...host.querySelectorAll("button")].filter(
                  (button) =>
                    !button.getAttribute("aria-label") &&
                    !button.textContent.trim() &&
                    !button.title,
                ).length,
              };
            });
            assert.equal(state.overflow, false, `${mode}/${width}/${theme}/${section}: overflow`);
            assert.equal(state.current, section);
            assert.equal(state.section, section);
            assert.equal(state.activeCount, 1);
            assert.equal(state.bodies, 1);
            assert.deepEqual(state.duplicateIds, []);
            assert.equal(state.animations, 0, "Reduced motion retained animation");
            assert.equal(state.unnamedButtons, 0);
            states++;
          }
        }
      }

      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.evaluate(() => setTheme("light"));
      await selectSection(page, "conta");
      await page.evaluate(() => setTheme("dark"));
      assert(
        (await page.locator("#settingsWorkspacePreview").innerText()).includes("SocialMEI Escuro"),
      );
      await page.evaluate(() => setTheme("light"));
      assert.equal(await page.locator("#accountSettingsNotice").count(), 1);
      assert.equal(await page.locator("#settingsView #accountSettingsNotice").count(), 1);
      assert(
        (await page.locator("#accountSettingsNotice").innerText()).includes(
          mode === "remote" ? "Conta conectada" : "Demonstração local",
        ),
      );
      assert.equal(
        await page.locator('#settingsPanel button[type="submit"]').count(),
        mode === "remote" ? 2 : 1,
      );
      assert.equal(await page.locator("#nvSettingsPrimary").count(), 1);
      await page.locator("#nvPref-nome").fill("Beatriz Atualizada");
      if (mode === "local") await page.locator("#nvPref-email").fill("beatriz@example.com");
      await page.locator("#nvSettingsPrimary").click();
      await page.waitForFunction(
        () => document.getElementById("nvSettingsFeedback")?.textContent === "Salvo",
      );
      assert.equal(
        profileRequests.length,
        mode === "remote" ? 1 : 0,
        "Native save submitted more than once",
      );
      assert.equal(await page.locator("#nvPref-nome").inputValue(), "Beatriz Atualizada");
      assert.equal(
        await page.locator(".account-overview-info b").innerText(),
        "Beatriz Atualizada",
      );
      if (mode === "remote")
        assert.deepEqual(profileRequests[0], {
          nome: "Beatriz Atualizada",
          telefone: "(11) 99999-0000",
        });
      else
        assert.equal(
          await page.evaluate(
            () => JSON.parse(localStorage.getItem("socialmei-app-data-v2")).prefs.conta.nome,
          ),
          "Beatriz Atualizada",
        );

      const phoneField = page.locator("#nvPref-telefone");
      const originalPhone = await phoneField.inputValue();
      const requestCount = profileRequests.length;
      await phoneField.fill("telefone_invalido");
      await page.locator("#nvSettingsPrimary").click();
      assert.equal(await phoneField.evaluate((input) => input.validity.valid), false);
      assert.equal(profileRequests.length, requestCount, "Contato inválido não deve chegar à API");
      await phoneField.fill(originalPhone);
      await phoneField.blur();
      assert.equal(await phoneField.evaluate((input) => input.validity.valid), true);

      const setup = page.locator(".settings-setup-disclosure");
      assert.equal(await setup.evaluate((element) => element.open), false);
      await setup.locator("summary").press("Enter");
      assert.equal(await setup.evaluate((element) => element.open), true);
      assert.equal(await setup.locator("[data-nv-setup]").count(), 6);
      assert.equal(await setup.locator("progress").getAttribute("max"), "6");
      await setup.locator("summary").press("Enter");
      await page.locator("[data-settings-appearance]").click();
      assert.equal(
        await page.locator("#settingsPanel").getAttribute("data-settings-section"),
        "aparencia",
      );
      await page.locator('#settingsPanel [data-theme-apply="dark"]').click();
      assert(
        (await page.locator("#settingsWorkspacePreview").innerText()).includes("SocialMEI Escuro"),
      );
      assert.equal(await page.locator("#settingsPanel .settings-panel-body").count(), 1);
      for (const width of [1440, 390, 360]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.locator("[data-theme-create]").first().click();
        assert.equal(
          await page
            .locator("#themeStudio")
            .evaluate((element) => element.classList.contains("open")),
          true,
        );
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        const panel = await page.locator("#themeStudio .modal").evaluate((element) => ({
          width: element.scrollWidth,
          clientWidth: element.clientWidth,
        }));
        assert(panel.width <= panel.clientWidth + 1, `Theme editor overflow at ${width}`);
        await page.screenshot({
          path: path.join(resultDirectory, `${mode}-theme-editor-${width}.png`),
          fullPage: true,
        });
        await page.keyboard.press("Escape");
        assert.equal(
          await page
            .locator("#themeStudio")
            .evaluate((element) => element.classList.contains("open")),
          false,
        );
      }
      await selectSection(page, "seguranca");
      assert.equal(await page.locator("#accountPasswordForm").count(), mode === "remote" ? 1 : 0);
      if (mode === "remote") {
        await page.locator(".account-password-disclosure > summary").press("Enter");
        assert.equal(await page.locator("#accountNewPassword").getAttribute("minlength"), "12");
        assert.equal(
          await page.locator("#accountConfirmPassword").getAttribute("autocomplete"),
          "new-password",
        );
        assert(
          !(await page.locator("#settingsPanel").innerText()).includes(
            "Autenticação externa indisponível",
          ),
        );
      }
      await selectSection(page, "dados");
      assert.deepEqual(
        await page.locator(".settings-data-source > span").allTextContents(),
        Array(4).fill(mode === "remote" ? "API do negócio" : "Neste navegador"),
      );
      await selectSection(page, "notificacoes");
      const notification = page.locator('[data-nv-notification="message"]');
      const oldValue = await notification.getAttribute("aria-checked");
      await notification.press("Enter");
      assert.notEqual(await notification.getAttribute("aria-checked"), oldValue);
      await page.locator("#nvSettingsPrimary").click();
      await page.waitForFunction(
        () => document.getElementById("nvSettingsFeedback")?.textContent === "Salvo",
      );
      await page.evaluate(() => {
        setView("Automações");
      });
      assert(
        !(await page.locator('[data-view="Automações"]').innerText()).includes("Conta conectada"),
        "Settings notice overwrote automation status",
      );
      await page.emulateMedia({ reducedMotion: "no-preference" });
      await page.evaluate(() => setView("Configurações"));
      await selectSection(page, "negocio");
      const motionDuration = await page
        .locator(".settings-panel-body")
        .evaluate((element) => getComputedStyle(element).animationDuration);
      assert.equal(motionDuration, "0.34s");
      await page
        .locator(".settings-panel-body")
        .evaluate((element) =>
          Promise.all(element.getAnimations().map((animation) => animation.finished)),
        );
      await page.close();
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(missingResources, []);
    console.log(
      `${states} estados de Configurações passaram; salvar, temas, teclado e modos local/conectado conferidos.`,
    );
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}
run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
