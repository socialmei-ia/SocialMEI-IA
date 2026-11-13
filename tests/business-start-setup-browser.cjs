const assert = require("node:assert/strict"),
  path = require("node:path"),
  { chromium } = require("playwright");

async function run() {
  const browser = await chromium.launch();
  try {
    for (const width of [390, 1440]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      await page.route("https://setup.example.test/**", (route) =>
        route.fulfill({
          contentType: "text/html",
          body: '<html style="--b:#888;--w:#fff;--t:#111"><body><div id="v"></div></body></html>',
        }),
      );
      await page.goto("https://setup.example.test/#/inicio");
      await page.evaluate(() => {
        window.render = () => {};
        window.calls = [];
        window.draft = [];
        window.revision = 0;
        window.posts = [];
        window.registered = false;
        window.uncertain = false;
        window.SocialMEIAuth = {
          remote: true,
          current: {
            usuario: { id: 1 },
            negocio: { id: 10, nome: "Negócio controlado" },
            papel: "owner",
          },
        };
        window.SocialMEIV22 = {
          remote: true,
          request: async (url, method = "GET", value) => {
            calls.push({ url, method, value: value ? structuredClone(value) : undefined });
            if (url === "/onboarding/status")
              return {
                workspace_id: 10,
                profile_complete: true,
                profile_problem: false,
                offers: ["services"],
                counts: {
                  customers: 0,
                  products: 0,
                  services: registered ? 1 : 0,
                  resources: 0,
                  appointments_created: 0,
                  valid_sales: 0,
                },
                setup: { hours_configured: false },
                description: "Somente dados persistidos.",
              };
            if (url === "/onboarding/catalog" && method === "GET") {
              if (window.delaySetup) {
                window.delaySetup = false;
                await new Promise((resolve) => {
                  window.finishSetup = resolve;
                });
              }
              return {
                workspace_id: 10,
                revision,
                items: draft,
                receipt: null,
                suggestions: ["Serviço escolhido no perfil"],
              };
            }
            if (url === "/onboarding/catalog" && method === "PUT") {
              revision++;
              draft = value.items;
              return { workspace_id: 10, revision, items: draft };
            }
            if (url === "/onboarding/catalog" && method === "POST") {
              posts.push(structuredClone(value));
              if (uncertain) {
                uncertain = false;
                throw Error("Entrega da resposta incerta.");
              }
              registered = true;
              return { workspace_id: 10, registered: true, items: [{ id: 77 }] };
            }
            throw Error("Unexpected request");
          },
        };
      });
      await page.addScriptTag({
        path: path.join(__dirname, "../frontend/scripts/v22-business-start.js"),
      });
      const panel = page.locator("[data-business-start]");
      await panel.getByRole("button", { name: "Conferir ofertas iniciais", exact: true }).click();
      const name = panel.getByLabel("Nome", { exact: true }),
        price = panel.getByLabel("Preço (R$)", { exact: true }),
        duration = panel.getByLabel("Duração (minutos)", { exact: true });
      await name.waitFor();
      assert.equal(await name.inputValue(), "Serviço escolhido no perfil");
      assert.equal(await price.inputValue(), "");
      assert.equal(await duration.inputValue(), "");
      await panel.getByRole("button", { name: "Salvar e continuar depois", exact: true }).click();
      await panel.getByText(/Configuração salva/).waitFor();
      assert.equal(await page.evaluate(() => posts.length), 0);
      await panel.getByRole("button", { name: "Atualizar primeiros passos", exact: true }).click();
      await panel.getByRole("button", { name: "Conferir ofertas iniciais", exact: true }).click();
      await name.waitFor();
      assert.equal(await name.inputValue(), "Serviço escolhido no perfil");
      await price.fill("79.90");
      await duration.fill("45");
      await panel
        .getByLabel("Conferi nomes, preços e duração destas ofertas.", { exact: true })
        .check();
      await page.evaluate(() => {
        uncertain = true;
      });
      await panel
        .getByRole("button", { name: "Cadastrar ofertas confirmadas", exact: true })
        .click();
      await panel.getByText("Entrega da resposta incerta.", { exact: true }).waitFor();
      assert.equal(await name.isDisabled(), true);
      await panel.getByRole("button", { name: "Conferir tentativa anterior", exact: true }).click();
      await panel.getByText("Serviço ativo com duração — Registrado", { exact: true }).waitFor();
      const requests = await page.evaluate(() => posts);
      assert.equal(requests.length, 2);
      assert.deepEqual(requests[0], requests[1]);
      assert.equal(requests[0].items[0].preco, 79.9);
      assert.equal(requests[0].items[0].duracao_minutos, 45);
      assert.equal(await page.evaluate(() => sessionStorage.length), 0);
      assert.equal(
        await panel
          .getByRole("link", { name: "Configurar horários e profissionais na Agenda" })
          .getAttribute("href"),
        "#/agenda",
      );
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
        false,
      );
      await page.evaluate(() => {
        window.delaySetup = true;
      });
      await panel.getByRole("button", { name: "Conferir ofertas iniciais", exact: true }).click();
      await page.waitForFunction(() => !!window.finishSetup);
      await panel.getByRole("button", { name: "Conferir ofertas iniciais", exact: true }).click();
      await name.waitFor();
      await name.fill("Alteração mais recente");
      await page.evaluate(() => {
        finishSetup();
        window.finishSetup = null;
      });
      await page.waitForTimeout(30);
      assert.equal(await name.inputValue(), "Alteração mais recente");
      await price.fill("80");
      await duration.fill("45");
      await panel
        .getByLabel("Conferi nomes, preços e duração destas ofertas.", { exact: true })
        .check();
      const callsBeforeSwitch = await page.evaluate(() => calls.length);
      await page.evaluate(() => {
        SocialMEIAuth.current.negocio.id = 20;
      });
      await panel.getByRole("button", { name: "Salvar e continuar depois", exact: true }).click();
      await panel
        .getByRole("button", { name: "Cadastrar ofertas confirmadas", exact: true })
        .click();
      assert.equal(await page.evaluate(() => calls.length), callsBeforeSwitch);
      await page.evaluate(() => {
        SocialMEIAuth.current.negocio.id = 10;
      });
      await page.evaluate(() => {
        window.delaySetup = true;
      });
      await panel.getByRole("button", { name: "Conferir ofertas iniciais", exact: true }).click();
      await page.waitForFunction(() => !!window.finishSetup);
      await page.evaluate(() => {
        SocialMEIAuth.current.negocio.id = 20;
        finishSetup();
      });
      await page.waitForTimeout(30);
      assert.equal(await panel.locator("form").count(), 0);
      await page.close();
    }
  } finally {
    await browser.close();
  }
  console.log(
    "Initial catalog setup: explicit prices/duration, durable draft/resume, exact uncertain retry, persisted progress and mobile/desktop PASS (controlled API)",
  );
}
if (require.main === module)
  run().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
module.exports = run;
