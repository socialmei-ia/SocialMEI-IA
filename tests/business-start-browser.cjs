const assert = require("node:assert/strict"),
  path = require("node:path"),
  { chromium } = require("playwright");
async function run() {
  const browser = await chromium.launch();
  try {
    for (const width of [390, 1440])
      for (const dark of [false, true]) {
        const page = await browser.newPage({ viewport: { width, height: 1000 } });
        await page.setContent(
          `<html style="--b:#888;--w:${dark ? "#202030" : "#fff"};--t:${dark ? "#fff" : "#111"}"><body style="margin:8px;background:var(--w);color:var(--t)"><div id="v"></div></body></html>`,
        );
        await page.evaluate(() => {
          location.hash = "#/inicio";
          window.render = () => {};
          window.mode = "error";
          window.calls = [];
          window.SocialMEIAuth = {
            remote: true,
            current: {
              usuario: { id: 1 },
              negocio: { id: 10, nome: "<img src=x onerror=alert(1)>" + "A".repeat(100) },
              papel: "owner",
            },
          };
          window.SocialMEIV22 = {
            remote: true,
            request: async (route) => {
              calls.push(route);
              if (mode === "error") throw Error("Consulta indisponível.");
              if (mode === "delay")
                await new Promise((resolve) => {
                  window.finish = resolve;
                });
              const service = mode === "services",
                empty = mode === "empty" || mode === "problem";
              return {
                workspace_id: mode === "foreign" ? 99 : 10,
                profile_complete: !empty,
                profile_problem: mode === "problem",
                offers: empty ? [] : service ? ["services"] : ["products"],
                counts: {
                  customers: service ? 1 : 0,
                  products: !empty && !service ? 1 : 0,
                  services: service ? 1 : 0,
                  resources: service ? 1 : 0,
                  appointments_created: service ? 1 : 0,
                  valid_sales: !empty && !service ? 1 : 0,
                },
                description:
                  "Somente registros persistidos. Agendamentos cadastrados não comprovam atendimento.",
              };
            },
          };
        });
        await page.addScriptTag({
          path: path.join(__dirname, "../frontend/scripts/v22-business-start.js"),
        });
        const panel = page.locator("[data-business-start]"),
          refresh = panel.getByRole("button", { name: "Atualizar primeiros passos", exact: true });
        await panel.getByText("Consulta indisponível.", { exact: true }).waitFor();
        await page.evaluate(() => {
          mode = "products";
        });
        await refresh.click();
        await panel
          .getByText("3 de 3 passos essenciais registrados neste negócio.", { exact: true })
          .waitFor();
        assert.equal(await panel.locator("img").count(), 0);
        assert.equal(
          await panel.getByRole("link", { name: "Abrir agenda", exact: true }).count(),
          0,
        );
        assert.equal(
          await panel
            .getByRole("link", { name: "Abrir produtos e estoque", exact: true })
            .getAttribute("href"),
          "#/negocio/produtos",
        );
        assert.equal(
          await panel
            .getByRole("link", { name: "Rever configuração", exact: true })
            .getAttribute("href"),
          "/frontend/entrada.html?setup=1#/comecar",
        );
        await page.evaluate(() => {
          mode = "services";
        });
        await refresh.click();
        await panel
          .getByText("5 de 5 passos essenciais registrados neste negócio.", { exact: true })
          .waitFor();
        assert.equal(
          await panel.getByRole("link", { name: "Abrir produtos e estoque", exact: true }).count(),
          0,
        );
        assert.equal(
          await panel.getByRole("link", { name: "Abrir agenda", exact: true }).getAttribute("href"),
          "#/agenda",
        );
        await page.evaluate(() => {
          mode = "empty";
        });
        await refresh.click();
        await panel.getByText("Perfil do negócio salvo — Pendente", { exact: true }).waitFor();
        assert.equal(await panel.locator("[data-state=complete]").count(), 0);
        assert.equal(
          await panel
            .getByRole("link", { name: "Configurar negócio", exact: true })
            .getAttribute("href"),
          "/frontend/entrada.html?setup=1#/comecar",
        );
        await page.evaluate(() => {
          mode = "problem";
        });
        await refresh.click();
        await panel.getByText(/O perfil salvo precisa de revisão/).waitFor();
        await page.evaluate(() => {
          mode = "foreign";
        });
        await refresh.click();
        await panel
          .getByText("Não foi possível confirmar seus primeiros passos.", { exact: true })
          .waitFor();
        assert.equal(await panel.locator("li").count(), 0);
        await page.evaluate(() => {
          mode = "delay";
        });
        await refresh.click();
        await page.waitForFunction(() => !!window.finish);
        await page.evaluate(() => {
          SocialMEIAuth.current.negocio.id = 20;
          finish();
        });
        await page.waitForTimeout(40);
        assert.equal(await panel.locator("li").count(), 0);
        assert.ok(
          (await page.evaluate(() => calls)).every((path) => path === "/onboarding/status"),
        );
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
          false,
        );
        await page.evaluate(() => {
          SocialMEIAuth.current.papel = "member";
          document.getElementById("v").replaceChildren();
          SocialMEIBusinessStart.refresh();
        });
        assert.equal(await page.locator("[data-business-start]").count(), 0);
        await page.close();
      }
  } finally {
    await browser.close();
  }
  console.log(
    "Business start guide: persisted status contract, product/service paths, optional customer, existing wizard links, empty/error/retry, role/privacy, stale/foreign scope and mobile/desktop light/dark PASS (controlled API)",
  );
}
if (require.main === module)
  run().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
module.exports = run;
