const assert = require("node:assert/strict");
const path = require("node:path");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  try {
    for (const width of [390, 1280]) {
      const page = await browser.newPage({ viewport: { width, height: 800 } });
      const failures = [];
      page.on("pageerror", (error) => failures.push(error.message));
      await page.setContent('<main id="v"><section data-appointments></section></main>');
      await page.evaluate(() => {
        location.hash = "#/agenda";
        window.SocialMEIV22 = {
          remote: true,
          identity: { usuario: { id: 1 }, negocio: { id: 2 }, papel: "owner" },
        };
        window.savedHours = {
          revision: 4,
          policy: { timezone: "America/Recife", enabled: false, hours: [], special_days: [] },
        };
        window.SocialMEIAuth = {
          current: { negocio: { configuracao: {} } },
          async request(path, method, payload) {
            if (path !== "/agenda/channel-booking") throw Error("Wrong API path");
            if (method === "PUT") {
              if (payload.expected_revision !== window.savedHours.revision) throw Object.assign(Error(), { status: 409 });
              window.savedHours = { revision: payload.expected_revision + 1, policy: payload.policy };
            }
            return structuredClone(window.savedHours);
          },
        };
      });
      await page.addScriptTag({ path: path.join(__dirname, "../frontend/scripts/agenda-hours.js") });
      await page.getByText("Funcionamento e disponibilidade", { exact: true }).click();
      await page.locator(".sm-hub-prepared > summary").click();
      await page.locator('[data-ah-action="specialDays"]').click();
      const dialog = page.getByRole("dialog", { name: "Horários especiais e feriados" });
      await dialog.getByText("Horários no fuso America/Recife.").waitFor();
      await dialog.getByLabel("Data", { exact: true }).fill("2026-12-25");
      await dialog.getByLabel("Funcionamento").selectOption("closed");
      await dialog.getByRole("button", { name: "Salvar data" }).click();
      await dialog.getByText("Horário salvo para os canais.").waitFor();
      let state = await page.evaluate(() => window.savedHours);
      assert.equal(state.revision, 5);
      assert.deepEqual(state.policy.special_days, [{ day: "2026-12-25", hours: [] }]);
      assert.equal(state.policy.enabled, false);
      await dialog.getByLabel("Funcionamento").selectOption("hours");
      await dialog.getByLabel("Abre", { exact: true }).fill("09:00");
      await dialog.getByLabel("Fecha", { exact: true }).fill("12:00");
      await dialog.getByRole("button", { name: "Salvar data" }).click();
      await dialog.getByText("Horário salvo para os canais.").waitFor();
      state = await page.evaluate(() => window.savedHours);
      assert.deepEqual(state.policy.special_days[0].hours, [{ opens: "09:00", closes: "12:00" }]);
      await page.evaluate(() => { window.savedHours.revision++; });
      await dialog.getByRole("button", { name: "Salvar data" }).click();
      await dialog.getByText("A configuração mudou em outra sessão.", { exact: false }).waitFor();
      await page.evaluate(() => {
        window.SocialMEIV22.identity.negocio.id = 3;
        document.dispatchEvent(new Event("socialmei-agenda-painted"));
      });
      await dialog.waitFor({ state: "detached" });
      assert.deepEqual(failures, []);
      await page.close();
    }
    console.log("Agenda: closure, intervals, revision conflict and workspace switch passed at 390px and 1280px");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
