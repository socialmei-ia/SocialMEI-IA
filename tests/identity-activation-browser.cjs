/* Browser contracts use controlled SMTP/API outcomes, never real mail. */
const assert = require("node:assert/strict");
module.exports = async (browser, origin) => {
  for (const width of [390, 1440]) {
    for (const mode of ["pending", "verification", "invite", "existing"]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const signed = mode !== "invite";
      if (signed)
        await context.addInitScript(() =>
          localStorage.setItem("socialmei-auth-browser-scope", "10:20"),
        );
      const page = await context.newPage();
      const token = "T".repeat(43),
        packets = [];
      const user = {
        usuario: { id: 10, email: "employee@example.test" },
        negocio: { id: 20, slug: "controlled", nome: "Negócio controlado" },
        papel: "owner",
        csrf_token: "a".repeat(64),
        email_verification: { required: true, verified: mode === "existing" },
      };
      await page.route("**/frontend/config.js", (route) =>
        route.fulfill({
          contentType: "text/javascript",
          body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};',
        }),
      );
      await page.route("**/api/v1/**", async (route) => {
        const request = route.request(),
          path = new URL(request.url()).pathname;
        assert(!request.url().includes(token));
        const body = request.postDataJSON();
        packets.push({ path, body, headers: request.headers() });
        let status = 200,
          value;
        if (path.endsWith("/auth/session")) value = signed ? user : null;
        else if (path.endsWith("/verification/status"))
          value = { required: true, verified: false, email: user.usuario.email };
        else if (path.endsWith("/verification/resend")) {
          status = 429;
          value = { detail: "Aguarde um minuto antes de reenviar." };
        } else if (path.endsWith("/verification/email")) {
          status = 202;
          value = { message: "E-mail atualizado. Confira o novo endereço." };
        } else if (path.endsWith("/verification/confirm")) value = { verified: true };
        else if (path.endsWith("/invitations/inspect"))
          value = {
            business_name: "Empresa correta",
            role: "member",
            email_hint: "e***@example.test",
          };
        else if (path.endsWith("/invitations/accept"))
          value = { accepted: true, message: "Acesso confirmado. Entre na sua conta." };
        else throw new Error("Unexpected identity request: " + path);
        await route.fulfill({
          status,
          contentType: "application/json",
          body: JSON.stringify(value),
        });
      });
      const fragment =
        mode === "verification"
          ? "#verificar/" + token
          : ["invite", "existing"].includes(mode)
            ? "#convite/" + token
            : "";
      await page.goto(origin + "/frontend/ativar.html" + fragment);
      if (mode === "pending") {
        await page.getByRole("button", { name: "Reenviar e-mail" }).click();
        await page.getByText("Aguarde um minuto antes de reenviar.").waitFor();
        await page.getByLabel("E-mail correto", { exact: true }).fill("correct@example.test");
        await page.getByLabel("Sua senha atual").fill("Private-controlled-password");
        await page.getByRole("button", { name: "Corrigir e enviar nova verificação" }).click();
        await page.getByText("E-mail atualizado. Confira o novo endereço.").waitFor();
        assert.equal(await page.getByLabel("Sua senha atual").inputValue(), "");
      } else if (mode === "verification") {
        await page.getByRole("button", { name: "Confirmar meu e-mail" }).click();
        await page.getByText("E-mail confirmado. Sua conta foi ativada.").waitFor();
      } else {
        await page.getByRole("heading", { name: "Convite para Empresa correta" }).waitFor();
        await page.getByLabel("E-mail que recebeu o convite").fill("employee@example.test");
        if (!signed) {
          await page.getByLabel("Seu nome", { exact: true }).fill("Funcionário controlado");
          await page.getByLabel("Senha para sua nova conta").fill("Private-controlled-password");
        } else assert.equal(await page.locator("input[type=password]").count(), 0);
        await page.getByRole("button", { name: "Aceitar acesso a este negócio" }).click();
        await page.getByText("Acesso confirmado. Entre na sua conta.").waitFor();
        const accepted = packets.find((p) => p.path.endsWith("/invitations/accept"));
        assert.equal(accepted.body.token, token);
        assert.equal("senha" in accepted.body, !signed);
        if (signed) assert.equal(accepted.headers["x-socialmei-csrf"], "a".repeat(64));
      }
      assert.equal(new URL(page.url()).hash, "");
      assert.equal(
        await page.evaluate(
          (token) => JSON.stringify([localStorage, sessionStorage]).includes(token),
          token,
        ),
        false,
      );
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
        true,
      );
      await context.close();
    }
  }
  console.log(
    "Identity activation: 8 mobile/desktop verification, resend, correction and employee invitation journeys passed (controlled transport).",
  );
};
