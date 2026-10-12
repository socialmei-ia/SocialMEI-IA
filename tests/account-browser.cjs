// UI contract against a controlled account API; real hashing/session/isolation are tested in PostgreSQL.
const assert = require("node:assert/strict");
module.exports = async function accountFlow(browser, origin) {
  const page = await browser.newPage({ reducedMotion: "reduce" });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let session = null;
  const passwords = [];
  const requests = [];
  const identity = (id) => ({
    usuario: {
      id,
      nome: id === 1 ? "Admin" : "MEI",
      email: `user${id}@example.com`,
      telefone: "11999998888",
      administrador_plataforma: id === 1,
    },
    negocio: {
      id,
      slug: id === 1 ? "team" : "mei-private",
      nome: id === 1 ? "Admin business" : "MEI business",
      configuracao: {},
    },
    papel: "owner",
    csrf_token: "a".repeat(64),
  });
  await page.route("**/*", async (route) => {
    const request = route.request(),
      url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === "/frontend/config.js") {
      const module = { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "team" };
      return route.fulfill({
        contentType: "application/javascript",
        body:
          "const SOCIALMEI_CONFIG=" +
          JSON.stringify({
            n8nMessagesUrl: null,
            auth: { mode: "remote", apiBaseUrl: "/api/v1" },
            clientes: module,
            produtos: module,
            vendas: module,
            financeiro: module,
          }) +
          ";",
      });
    }
    if (!url.pathname.startsWith("/api/v1/")) return route.continue();
    requests.push({ path: url.pathname, method: request.method(), headers: request.headers() });
    let status = 200,
      data = [];
    const body = request.postDataJSON();
    if (url.pathname === "/api/v1/auth/me") {
      status = session ? 200 : 401;
      data = session ? identity(session) : { detail: "Entre na sua conta." };
    } else if (url.pathname === "/api/v1/auth/login") {
      assert.equal(request.headers()["x-socialmei-client"], "browser");
      passwords.push(body.senha);
      if (body.senha !== "Valid-password-123!") {
        status = 401;
        data = { detail: "E-mail ou senha inválidos." };
      } else {
        session = body.email === "user1@example.com" ? 1 : 2;
        data = identity(session);
      }
    } else if (url.pathname === "/api/v1/auth/register") {
      assert.equal(body.convite, "b".repeat(64));
      assert.equal(body.senha, "Valid-password-123!");
      session = 2;
      status = 201;
      data = identity(2);
    } else if (!session) {
      status = 401;
      data = { detail: "Sessão expirada." };
    } else if (url.pathname === "/api/v1/auth/logout") {
      assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
      session = null;
      status = 204;
      data = null;
    } else if (url.pathname === "/api/v1/admin/users") {
      assert.equal(session, 1);
      data = [
        {
          id: 1,
          nome: "Admin",
          email: "user1@example.com",
          ativo: true,
          administrador_plataforma: true,
        },
      ];
    } else if (url.pathname === "/api/v1/auth/profile") {
      assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
      data = identity(session);
      data.usuario.nome = body.nome || data.usuario.nome;
    }
    return route.fulfill({
      status,
      contentType: "application/json",
      body: status === 204 ? "" : JSON.stringify(data),
    });
  });
  async function login(email, password = "Valid-password-123!") {
    await page.locator("[data-auth-tab=login]").click();
    await page.locator("#loginEmail").fill(email);
    await page.locator("#loginPassword").fill(password);
    await page.locator("#xpLoginForm [type=submit]").click();
  }
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () => SocialMEIAuth.remote && !!document.querySelector("[data-xp-screen=auth].is-active"),
    );
    assert(
      !requests.some((r) =>
        ["/api/v1/clientes", "/api/v1/produtos", "/api/v1/vendas", "/api/v1/financeiro"].includes(
          r.path,
        ),
      ),
    );
    await page.evaluate(() => SocialMEIExperience.enterApp("Clientes"));
    assert(!(await page.locator("body").evaluate((el) => el.classList.contains("experience-app"))));
    await login("user1@example.com", "Wrong-password-123!");
    await page.waitForFunction(() =>
      document.getElementById("authConfirmation").textContent.includes("E-mail ou senha"),
    );
    assert.equal(session, null);
    await page.locator("#loginRemember").check();
    assert(await page.locator("#loginRemember").isEnabled());
    await login("user1@example.com");
    await page.waitForFunction(
      () =>
        SocialMEIAuth.current?.usuario.id === 1 &&
        document.body.classList.contains("experience-app"),
    );
    await page.evaluate(() => localStorage.setItem("socialmei-private-test", "first-account"));
    await page.reload();
    await page.waitForFunction(
      () =>
        SocialMEIAuth.current?.usuario.id === 1 &&
        document.body.classList.contains("experience-app"),
    );
    await page.goto(origin + "/frontend/admin.html");
    await page.waitForFunction(() => !document.getElementById("adminContent").hidden);
    assert((await page.locator("#adminUsers").innerText()).includes("user1@example.com"));
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(() => SocialMEIAuth.current?.usuario.id === 1);
    await page.evaluate(() => SocialMEIAuth.logout());
    await page.waitForFunction(
      () =>
        SocialMEIAuth.remote &&
        !SocialMEIAuth.current &&
        !!document.querySelector("[data-xp-screen=auth].is-active"),
    );
    assert.equal(await page.evaluate(() => localStorage.getItem("socialmei-private-test")), null);
    await page.locator("[data-auth-tab=register]").click();
    await page.locator("#registerName").fill("MEI");
    await page.locator("#registerEmail").fill("user2@example.com");
    await page.locator("#registerPhone").fill("11999998888");
    await page.locator("#registerPassword").fill("Valid-password-123!");
    await page.locator("#registerInvite").fill("b".repeat(64));
    await page.locator("#xpRegisterForm [type=submit]").click();
    await page.waitForFunction(
      () =>
        SocialMEIAuth.current?.usuario.id === 2 &&
        document.body.classList.contains("experience-app"),
    );
    assert.equal(await page.evaluate(() => localStorage.getItem("socialmei-private-test")), null);
    const stored = await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    );
    for (const password of passwords) assert(!stored.includes(password));
    assert(!stored.includes("csrf_token"));
    await page.goto(origin + "/frontend/admin.html");
    await page.waitForFunction(() =>
      document.getElementById("adminStatus").textContent.includes("administrador"),
    );
    assert(await page.locator("#adminContent").isHidden());
    session = null;
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () =>
        SocialMEIAuth.remote &&
        !SocialMEIAuth.current &&
        !!document.querySelector("[data-xp-screen=auth].is-active"),
    );
    assert.deepEqual(errors, []);
    return "Contas: senha inválida, login/cadastro por convite, sessão, logout, troca de MEI e acesso ao administrador";
  } finally {
    await page.close();
  }
};
