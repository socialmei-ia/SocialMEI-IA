// V22 entry UI contract with controlled account API. Real sessions/SQL are tested in backend.
const assert = require("node:assert/strict");
module.exports = async function v22EntryFlow(browser, origin) {
  const checks = [];
  for (const mode of ["register", "login", "onboarding", "failure", "recovery"]) {
    const page = await browser.newPage({
      viewport: { width: 390, height: 1000 },
      reducedMotion: "reduce",
    });
    let identity =
      mode === "onboarding"
        ? {
            usuario: {
              id: 15,
              nome: "Pessoa Teste",
              email: "teste@example.test",
              telefone: "",
              administrador_plataforma: false,
            },
            negocio: { id: 24, slug: "teste", nome: "Negócio teste", configuracao: {} },
            papel: "owner",
            csrf_token: "a".repeat(64),
          }
        : null;
    let profile = null;
    const writes = [],
      errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.addInitScript(
      (scope) => {
        if (!localStorage.getItem("socialmei-auth-browser-scope"))
          localStorage.setItem("socialmei-auth-browser-scope", scope);
        localStorage.setItem(
          "smei-perfil",
          JSON.stringify({ nome: "Outro usuário", negocio: "Não carregar" }),
        );
      },
      mode === "onboarding" ? "15:24" : "",
    );
    await page.route("**/*", async (route) => {
      const u = new URL(route.request().url());
      if (u.origin !== origin) return route.abort();
      if (u.pathname.startsWith("/api/v1/") && route.request().method() !== "GET") {
        assert.equal(route.request().headers()["x-socialmei-client"], "browser");
        if (["/api/v1/auth/profile", "/api/v1/workspace-profile"].includes(u.pathname))
          assert.equal(route.request().headers()["x-socialmei-csrf"], identity.csrf_token);
      }
      if (u.pathname === "/frontend/config.js")
        return route.fulfill({
          contentType: "text/javascript",
          body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
        });
      if (u.pathname === "/frontend/socialmei-app.html")
        return route.fulfill({ contentType: "text/html", body: "<h1>App destino</h1>" });
      if (u.pathname === "/api/v1/auth/session") return route.fulfill({ json: identity });
      if (u.pathname === "/api/v1/auth/registration")
        return route.fulfill({ json: { mode: "open" } });
      if (u.pathname === "/api/v1/workspace-profile") {
        if (route.request().method() === "PATCH") {
          profile = route.request().postDataJSON();
          writes.push(profile);
          return route.fulfill({
            json: { schema_version: 1, revision: 1, profile: profile.profile },
          });
        }
        return route.fulfill({ json: { schema_version: 1, revision: 0, profile: null } });
      }
      if (u.pathname === "/api/v1/auth/profile") {
        writes.push(route.request().postDataJSON());
        return route.fulfill({ json: identity });
      }
      if (u.pathname === "/api/v1/auth/recovery/request") {
        writes.push(route.request().postDataJSON());
        return route.fulfill({
          status: 202,
          json: { message: "Se houver uma conta ativa, enviaremos um código." },
        });
      }
      if (u.pathname === "/api/v1/auth/recovery/confirm") {
        writes.push(route.request().postDataJSON());
        return route.fulfill({ status: 204 });
      }
      if (u.pathname === "/api/v1/auth/register" || u.pathname === "/api/v1/auth/login") {
        if (mode === "failure")
          return route.fulfill({ status: 400, json: { detail: "E-mail ou senha inválidos." } });
        writes.push(route.request().postDataJSON());
        identity = {
          usuario: {
            id: 15,
            nome: "Pessoa Teste",
            email: "teste@example.test",
            telefone: "",
            administrador_plataforma: false,
          },
          negocio: { id: 24, slug: "teste", nome: "Negócio teste", configuracao: {} },
          papel: "owner",
          csrf_token: "a".repeat(64),
        };
        return route.fulfill({ json: identity });
      }
      return route.continue();
    });
    await page.goto(
      origin +
        "/frontend/entrada.html#/" +
        (mode === "onboarding" ? "comecar" : mode === "register" ? "cadastro" : "entrar"),
    );
    if (mode === "register") {
      assert.match(await page.locator("#panC .pxb").innerText(), /conta.*verdade/i);
      assert.doesNotMatch(await page.locator("#panC .pxb").innerText(), /nenhuma conta real/i);
      assert.match(await page.locator(".hero-top .badge").innerText(), /dados de negócio/i);
      assert.doesNotMatch(
        await page.locator(".steps .step").first().locator("p").textContent(),
        /nada é enviado/i,
      );
      assert.match(
        await page
          .locator(".faq")
          .filter({ hasText: "Meus dados vão" })
          .locator(".fa")
          .textContent(),
        /servidor|SocialMEI/,
      );
    }
    if (mode === "login") {
      assert.match(await page.locator("#panE > .pxb").innerText(), /conta real/i);
      assert(await page.locator("#waOpen").isDisabled());
      assert.match(await page.locator("#waOpenUnavailable").innerText(), /não está disponível/);
    }
    if (mode === "register") {
      await page.locator("#cNome").fill("Pessoa Teste");
      await page.locator("#cMail").fill("teste@example.test");
      await page.locator("#cPass").fill("FlorSol!");
      await page.locator("#cTermos").check();
      await page.locator("#fC [type=submit]").click();
      await page.waitForURL("**/entrada.html?setup=1#/comecar");
      await page.waitForFunction(() => window.SocialMEIAuth?.current?.usuario.id === 15);
      assert.equal(writes[0].senha, "FlorSol!");
    }
    if (mode === "login") {
      await page.locator("#eMailL").fill("teste@example.test");
      await page.locator("#ePassL").fill("FlorSol!");
      await page.locator("#fE [type=submit]").click();
      await page.waitForURL("**/socialmei-app.html#/inicio");
      assert.equal(writes[0].senha, "FlorSol!");
    }
    if (mode === "onboarding") {
      await page.locator("#oNeg").waitFor();
      assert.equal(await page.locator("#oNome").inputValue(), "Pessoa Teste");
      await page.locator("#oNeg").fill("Barbearia real");
      await page.locator('[data-area="beleza"]').click();
      await page.locator('[data-tipo="servicos"]').click();
      await page.locator('[data-ob="prox"]').click();
      await page.locator('[data-of="Corte e escova"]').click();
      await page.locator('[data-ob="prox"]').click();
      await page.locator('[data-ob="prox"]').click();
      await page.locator('[data-ob="prox"]').click();
      await page.locator('[data-ob="fim"]').click();
      await page.waitForURL("**/socialmei-app.html#/bemvindo");
      assert.equal(profile.expected_revision, 0);
      assert.equal(profile.profile.segment, "hairdresser");
      assert.deepEqual(profile.profile.services, ["Corte e escova"]);
    }
    if (mode === "failure") {
      await page.locator("#eMailL").fill("teste@example.test");
      await page.locator("#ePassL").fill("Wrong-pass-123");
      await page.locator("#fE [type=submit]").click();
      await page.waitForFunction(() =>
        document.getElementById("ePassLe").textContent.includes("inválidos"),
      );
      assert.equal(await page.locator("#eMailL").inputValue(), "teste@example.test");
      assert.equal(await page.locator("#ePassL").inputValue(), "Wrong-pass-123");
      assert.equal(await page.locator("#fE [type=submit]").isEnabled(), true);
    }
    if (mode === "recovery") {
      await page.locator("#eMailL").fill("teste@example.test");
      await page.locator("#forgot").click();
      await page.locator("#fR [type=submit]").click();
      await page.waitForFunction(() =>
        document.getElementById("rStatus").textContent.includes("enviaremos"),
      );
      await page.locator("#rOpen").click();
      await page.locator("#nPass").fill("FlorSol!");
      await page.locator("#nPass2").fill("FlorSol!");
      await page.locator("#fN [type=submit]").click();
      assert.equal(writes.length, 1, "Missing recovery token must not call confirmation API");
      assert.match(await page.locator("#eRToken").innerText(), /código completo/);
      await page.locator("#rToken").fill("r".repeat(43));
      await page.locator("#nPass").fill("FlorSol!");
      await page.locator("#nPass2").fill("FlorSol!");
      await page.locator("#fN [type=submit]").click();
      await page.waitForFunction(() =>
        document.getElementById("rStatus").textContent.includes("redefinida"),
      );
      assert.deepEqual(writes, [
        { email: "teste@example.test" },
        { token: "r".repeat(43), nova: "FlorSol!" },
      ]);
      assert.equal(await page.locator("#rToken").inputValue(), "");
      await page.locator("#rGo").click();
      assert.equal(await page.locator("#panR").isVisible(), false);
      assert.equal(
        await page.locator("#ePassL").evaluate((e) => e === document.activeElement),
        true,
      );
    }
    assert.deepEqual(errors, []);
    const stored = await page.evaluate(() => JSON.stringify({ ...localStorage }));
    assert(!stored.includes("FlorSol!"));
    checks.push({ case: mode, writes: writes.length });
    await page.close();
  }
  return checks;
};
