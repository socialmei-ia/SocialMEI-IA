// UI contract against a controlled account API; real hashing/session/isolation are tested in PostgreSQL.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
module.exports = async function accountFlow(browser, origin) {
  const page = await browser.newPage({ reducedMotion: "reduce" });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let session = null;
  let refuseLogout = false;
  const passwords = [];
  const validPasswords = new Map([
    [1, "Valid-password-123!"],
    [2, "Valid-password-123!"],
  ]);
  const requests = [];
  const users = [
    {
      id: 1,
      nome: "Admin",
      email: "user1@example.com",
      ativo: true,
      administrador_plataforma: true,
    },
    {
      id: 7,
      nome: "Camila Santos",
      email: "camila@example.com",
      ativo: true,
      administrador_plataforma: false,
    },
    {
      id: 8,
      nome: "Rafael Lima",
      email: "rafael@example.com",
      ativo: false,
      administrador_plataforma: false,
    },
  ];
  const screenshots = path.resolve(__dirname, "../test-results/accounts");
  fs.mkdirSync(screenshots, { recursive: true });
  async function capture(name) {
    await page.evaluate(() => document.activeElement?.blur());
    await page.screenshot({ path: path.join(screenshots, name + ".png"), fullPage: true });
  }
  async function fitsViewport() {
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth + 1,
    );
    assert.equal(overflow, false, "Account screen overflowed the viewport");
  }
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
      if (body.senha !== validPasswords.get(body.email === "user1@example.com" ? 1 : 2)) {
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
      if (refuseLogout) {
        refuseLogout = false;
        status = 503;
        data = { detail: "Saída temporariamente indisponível." };
      } else {
        session = null;
        status = 204;
        data = null;
      }
    } else if (url.pathname === "/api/v1/auth/password") {
      assert.deepEqual(Object.keys(body).sort(), ["atual", "nova"]);
      assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
      assert.equal(body.atual, validPasswords.get(session));
      validPasswords.set(session, body.nova);
      session = null;
      status = 204;
      data = null;
    } else if (url.pathname === "/api/v1/admin/users") {
      assert.equal(session, 1);
      data = users;
    } else if (/^\/api\/v1\/admin\/users\/\d+\/disable$/.test(url.pathname)) {
      assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
      users.find((user) => user.id === Number(url.pathname.split("/").at(-2))).ativo = false;
      status = 204;
    } else if (url.pathname === "/api/v1/admin/invites") {
      assert.equal(body.email, "new@example.com");
      assert.equal(request.headers()["x-socialmei-csrf"], "a".repeat(64));
      status = 201;
      data = { email: body.email, convite: "b".repeat(64), validade_dias: 3 };
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
  async function login(
    email,
    password = validPasswords.get(email === "user1@example.com" ? 1 : 2),
  ) {
    await page.locator("[data-auth-tab=login]").click();
    await page.locator("#loginEmail").fill(email);
    await page.locator("#loginPassword").fill(password);
    await page.locator("#xpLoginForm [type=submit]").click();
  }
  async function assertRealSession(expectedConversations = 0) {
    if (await page.evaluate(() => !!window.SocialMEIAuth?.current)) {
      await page.waitForFunction(() =>
        [
          "#refresh",
          "[data-clients-reload]",
          "[data-products-reload]",
          "[data-sales-reload]",
          "[data-finance-reload]",
        ].every((selector) => {
          const button = document.querySelector(selector);
          return button && !button.disabled;
        }),
      );
    }
    const data = await page.evaluate(() => ({
      conversations: sessionData.conversas.length,
      activity: sessionData.atividade.length,
      notifications: sessionData.notificacoes.length,
    }));
    assert.deepEqual(
      data,
      {
        conversations: expectedConversations,
        activity: 0,
        notifications: 0,
      },
      "Real accounts must not start with demo attendance data",
    );
  }
  async function assertEmptyAttendanceViews() {
    for (const width of [360, 390, 430, 1440]) {
      await page.setViewportSize({ width, height: width === 1440 ? 1000 : 844 });
      for (const theme of ["light", "dark"]) {
        await page.evaluate((theme) => {
          setTheme(theme);
          setView("Início");
        }, theme);
        assert(!(await page.locator("#homeNow").innerText()).includes("Maria Silva"));
        await page.evaluate(() => setView("Caixa Unificada"));
        assert.equal(await page.locator("#conversationList [data-conversation]").count(), 0);
        assert.match(await page.locator("#conversationList").innerText(), /Nenhuma conversa/);
        await page.evaluate(() => setView("Assistente"));
        assert.equal(await page.locator("#asConversationCount").innerText(), "0");
        await page.evaluate(() => {
          setView("Relatórios");
          selectedReportTab = "Atendimento";
          renderReports();
          renderNotifications();
        });
        assert.match(await page.locator("#notList").textContent(), /Sem notificações/);
        assert.equal(await page.locator("#notifyDot").evaluate((el) => el.style.display), "none");
        await fitsViewport();
      }
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.evaluate(() => {
      setTheme("light");
      setView("Início");
    });
  }
  try {
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () => SocialMEIAuth.remote && !!document.querySelector("[data-xp-screen=auth].is-active"),
    );
    await assertRealSession();
    await page.evaluate(() => {
      localStorage.setItem(
        "socialmei-inbox-local-v3",
        JSON.stringify({
          "notes:whatsapp:maria silva": [{ localNoteId: "legacy-note", texto: "Legacy note" }],
        }),
      );
      localStorage.setItem(
        "socialmei-ai-drafts-v1",
        JSON.stringify([
          { name: "Legacy draft", text: "Preserve this draft", at: "2026-10-10T12:00:00Z" },
        ]),
      );
    });
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
    await page.locator(".landing-login-disabled-link").click();
    assert(await page.locator("#accountRecoveryHelp").isVisible());
    assert((await page.locator("#accountRecoveryHelp").innerText()).includes("preparação"));
    await page.locator("[data-close-recovery]").click();
    assert(await page.locator("#accountRecoveryHelp").isHidden());
    await page.locator("#loginRemember").check();
    assert(await page.locator("#loginRemember").isEnabled());
    await login("user1@example.com");
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current?.usuario.id === 1 &&
        document.body.classList.contains("experience-app"),
    );
    await assertRealSession();
    const legacy = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("socialmei-account-state-legacy")),
    );
    assert(legacy["socialmei-inbox-local-v3"].includes("Legacy note"));
    assert(legacy["socialmei-ai-drafts-v1"].includes("Preserve this draft"));
    await assertEmptyAttendanceViews();
    await page.evaluate(() => {
      localStorage.setItem(
        "socialmei-inbox-local-v3",
        JSON.stringify({
          localConversations: [
            {
              id: 77,
              nome: "Local QA",
              iniciais: "LQ",
              canal: "whatsapp",
              status: "aberto",
              telefone: "11999990000",
              usuario: "@localqa",
              naoLidas: 0,
              atualizado: "agora",
              mensagens: [],
              localConversation: true,
            },
          ],
          "notes:whatsapp:local qa": [
            {
              localNoteId: "account-note",
              de: "nota",
              texto: "Account note",
              hora: "12:00",
            },
          ],
          "notes:whatsapp:maria silva": [{ localNoteId: "old-demo-note", texto: "Keep old note" }],
        }),
      );
      localStorage.setItem(
        "socialmei-ai-drafts-v1",
        JSON.stringify([{ name: "Saved QA", text: "Account draft", at: "2026-10-10T12:00:00Z" }]),
      );
    });
    await page.reload();
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current?.usuario.id === 1 &&
        document.body.classList.contains("experience-app"),
    );
    await assertRealSession(1);
    assert.equal(await page.evaluate(() => sessionData.conversas[0].nome), "Local QA");
    assert(
      await page.evaluate(() =>
        sessionData.conversas[0].mensagens.some((message) => message.texto === "Account note"),
      ),
    );
    assert(
      (await page.evaluate(() => localStorage.getItem("socialmei-inbox-local-v3"))).includes(
        "Keep old note",
      ),
    );
    assert(
      (await page.evaluate(() => localStorage.getItem("socialmei-ai-drafts-v1"))).includes(
        "Account draft",
      ),
    );
    assert(await page.locator("#profileBtn").isVisible());
    assert.equal(await page.locator("#utilityTools").evaluate((element) => element.open), false);
    await page.locator("#profileBtn").click();
    await page.locator('[data-profile-action="perfil"]').click();
    await page.waitForFunction(
      () => currentView === "Configurações" && selectedSettingsTab === "conta",
    );
    assert(await page.locator("#settingsPanel [data-account-logout]").isVisible());
    assert((await page.locator("#settingsPanel").innerText()).includes("Administração do projeto"));
    await capture("account-desktop-light");
    await page.evaluate(() => setTheme("dark"));
    await capture("account-desktop-dark");
    await page.evaluate(() => setTheme("light"));
    await page.locator(".account-password-disclosure summary").click();
    await page.locator("#accountCurrentPassword").fill("Valid-password-123!");
    await page.locator("#accountNewPassword").fill("New-valid-password-123!");
    await page.locator("#accountConfirmPassword").fill("Other-valid-password-123!");
    const passwordRequests = requests.filter(
      (request) => request.path === "/api/v1/auth/password",
    ).length;
    await page.locator("#accountPasswordForm [type=submit]").click();
    assert((await page.locator("#accountPasswordFeedback").innerText()).includes("iguais"));
    assert.equal(
      requests.filter((request) => request.path === "/api/v1/auth/password").length,
      passwordRequests,
    );
    await page.locator("#accountConfirmPassword").fill("New-valid-password-123!");
    await page.locator("#accountPasswordForm [type=submit]").click();
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.remote &&
        !window.SocialMEIAuth.current &&
        !!document.querySelector("[data-xp-screen=auth].is-active"),
    );
    await login("user1@example.com");
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current?.usuario.id === 1 &&
        document.body.classList.contains("experience-app"),
    );
    await page.locator("#profileBtn").click();
    await page.locator('[data-profile-action="perfil"]').click();
    await page.setViewportSize({ width: 390, height: 844 });
    await fitsViewport();
    await capture("account-mobile-light");
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.evaluate(() => localStorage.setItem("socialmei-private-test", "first-account"));
    await page.reload();
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current?.usuario.id === 1 &&
        document.body.classList.contains("experience-app"),
    );
    assert(await page.locator("#sb [data-account-logout]").isVisible());
    await page.locator("#sb [data-account-logout]").click();
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.remote &&
        !window.SocialMEIAuth.current &&
        !!document.querySelector("[data-xp-screen=auth].is-active"),
    );
    await login("user1@example.com");
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current?.usuario.id === 1 &&
        document.body.classList.contains("experience-app"),
    );
    await page.goto(origin + "/frontend/admin.html");
    await page.waitForFunction(() => !document.getElementById("adminContent").hidden);
    assert((await page.locator("#adminUsers").innerText()).includes("user1@example.com"));
    assert.equal(await page.locator("#adminTotal").innerText(), "3");
    await fitsViewport();
    await capture("admin-desktop-light");
    await page.locator("#adminThemeToggle").click();
    await capture("admin-desktop-dark");
    await page.locator("#adminThemeToggle").click();
    await page.locator("#adminSearch").fill("rafael");
    assert.equal(await page.locator("#adminUsers tr").count(), 1);
    await page.locator("#adminSearch").fill("");
    await page.locator("#adminFilter").selectOption("disabled");
    assert.equal(await page.locator("#adminUsers tr").count(), 1);
    await page.locator("#adminFilter").selectOption("all");
    await page.locator("#inviteEmail").fill("new@example.com");
    await page.locator("#adminInviteForm [type=submit]").click();
    await page.waitForFunction(() => !document.getElementById("inviteResult").hidden);
    assert.equal(await page.locator("#inviteCode").inputValue(), "b".repeat(64));
    await page.locator("#copyInvite").click();
    assert(
      (await page.locator("#adminStatus").innerText()).includes("código") ||
        (await page.locator("#adminStatus").innerText()).includes("Código"),
    );
    await page.getByRole("button", { name: "Desativar acesso de Camila Santos" }).click();
    assert(await page.locator("#disableAccountDialog").isVisible());
    await page.getByRole("button", { name: "Manter acesso" }).click();
    assert.equal(users.find((user) => user.id === 7).ativo, true);
    await page.getByRole("button", { name: "Desativar acesso de Camila Santos" }).click();
    await page.locator("#disableAccountConfirm").click();
    await page.waitForFunction(() => document.getElementById("adminDisabled").textContent === "2");
    await page.setViewportSize({ width: 390, height: 844 });
    await fitsViewport();
    await capture("admin-mobile-light");
    await page.locator("#adminThemeToggle").click();
    await fitsViewport();
    await capture("admin-mobile-dark");
    await page.locator("#adminThemeToggle").click();
    await page.locator("#adminLogout").click();
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.remote &&
        !window.SocialMEIAuth.current &&
        !!document.querySelector("[data-xp-screen=auth].is-active"),
    );
    assert(new URL(page.url()).pathname.endsWith("/frontend/socialmei-app.html"));
    await login("user1@example.com");
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current?.usuario.id === 1 &&
        document.body.classList.contains("experience-app"),
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(origin + "/frontend/transferencia.html");
    await page.waitForFunction(() => !document.getElementById("packetFile").disabled);
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(() => window.SocialMEIAuth?.current?.usuario.id === 1);
    await page.locator("#profileBtn").click();
    await page.locator('[data-profile-action="perfil"]').click();
    await page.setViewportSize({ width: 390, height: 844 });
    refuseLogout = true;
    await page.locator("#settingsPanel [data-account-logout]").click();
    await page.waitForFunction(() => document.body.innerText.includes("Saída não concluída"));
    assert.equal(session, 1);
    assert.equal(await page.evaluate(() => SocialMEIAuth.current.usuario.id), 1);
    assert(await page.locator("#settingsPanel [data-account-logout]").isEnabled());
    await page.locator("#settingsPanel [data-account-logout]").click();
    await page.waitForFunction(
      () =>
        SocialMEIAuth.remote &&
        window.SocialMEIAuth?.remote &&
        !window.SocialMEIAuth.current &&
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
        window.SocialMEIAuth?.current?.usuario.id === 2 &&
        document.body.classList.contains("experience-app"),
    );
    assert.equal(await page.evaluate(() => localStorage.getItem("socialmei-private-test")), null);
    assert.equal(await page.locator("#profileAdminLink").evaluate((link) => link.hidden), true);
    await assertRealSession();
    assert(
      !(await page.evaluate(() => localStorage.getItem("socialmei-inbox-local-v3") || "")).includes(
        "Account note",
      ),
    );
    await assertEmptyAttendanceViews();
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
    await page.goto(origin + "/frontend/transferencia.html");
    await page.waitForFunction(() =>
      document.getElementById("status").textContent.includes("administrador"),
    );
    assert(await page.locator("#packetFile").isDisabled());
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current?.usuario.id === 2 &&
        document.body.classList.contains("experience-app"),
    );
    await page.locator("#sb [data-account-logout]").click();
    await page.waitForFunction(() => !!document.querySelector("[data-xp-screen=auth].is-active"));
    await login("user1@example.com");
    await page.waitForFunction(
      () =>
        window.SocialMEIAuth?.current?.usuario.id === 1 &&
        document.body.classList.contains("experience-app"),
    );
    await assertRealSession(1);
    assert(
      await page.evaluate(() =>
        sessionData.conversas[0].mensagens.some((message) => message.texto === "Account note"),
      ),
    );
    assert(
      (await page.evaluate(() => localStorage.getItem("socialmei-ai-drafts-v1"))).includes(
        "Account draft",
      ),
    );
    session = null;
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.waitForFunction(
      () =>
        SocialMEIAuth.remote &&
        window.SocialMEIAuth?.remote &&
        !window.SocialMEIAuth.current &&
        !!document.querySelector("[data-xp-screen=auth].is-active"),
    );
    assert.deepEqual(errors, []);
    await assertRealSession();
    return "Contas: login/cadastro, sessão/logout, administrador, atendimento sem seeds demo e preservação/isolamento de notas e rascunhos";
  } finally {
    await page.close();
  }
};
