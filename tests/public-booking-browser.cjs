/* Controlled public transport; no real SMTP, provider or reservation. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");

async function validate(browser, origin) {
  let journeys = 0;
  for (const width of [390, 768, 1440]) {
    for (const dark of [false, true]) {
      const context = await browser.newContext({
        viewport: { width, height: 1100 },
        reducedMotion: "reduce",
        colorScheme: dark ? "dark" : "light",
      });
      await context.addCookies([
        { name: "socialmei_session", value: "synthetic-admin-session", url: origin },
      ]);
      const page = await context.newPage();
      const errors = [],
        outside = [],
        requests = [],
        confirmations = [];
      let scenario = "normal",
        bookCalls = 0;
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("**/*", async (route) => {
        const request = route.request(),
          url = new URL(request.url());
        if (url.origin !== origin) {
          outside.push(url.origin);
          return route.abort();
        }
        if (!url.pathname.startsWith("/api/v1/")) return route.continue();
        assert.equal(
          request.headers()["cookie"],
          undefined,
          "Visitor requests must not carry admin cookies",
        );
        assert.equal(request.headers()["authorization"], undefined);
        assert.ok(url.pathname.startsWith("/api/v1/public/booking/"));
        requests.push({
          path: url.pathname,
          method: request.method(),
          body: request.postDataJSON(),
        });
        if (scenario === "off")
          return route.fulfill({ status: 503, json: { detail: "private technical error" } });
        const slug = url.pathname.split("/")[5],
          base = "/api/v1/public/booking/" + slug;
        if (url.pathname === base)
          return route.fulfill({
            json: {
              name: slug === "brilho" ? "Brilho Limpeza" : "Bella Store",
              timezone: "America/Fortaleza",
              horizon_days: 30,
              server_date: "2031-11-12",
              services: [
                {
                  reference: "private-service-" + slug,
                  name: "Atendimento de exemplo",
                  duration_minutes: 30,
                  price: "80.00",
                },
              ],
            },
          });
        if (url.pathname.endsWith("/resources"))
          return route.fulfill({
            json: { items: [{ reference: "private-resource-" + slug, name: "Equipe de exemplo" }] },
          });
        if (url.pathname.endsWith("/slots")) {
          if (scenario === "empty")
            return route.fulfill({
              json: { items: [], has_more: false, timezone: "America/Fortaleza" },
            });
          return route.fulfill({
            json: {
              items: [
                {
                  offer: "private-offer-" + slug,
                  scheduled_for: "2031-11-13T09:00:00-03:00",
                  ends_at: "2031-11-13T09:30:00-03:00",
                  service_name: "Atendimento de exemplo",
                  resource_name: "Equipe de exemplo",
                  duration_minutes: 30,
                  price: "80.00",
                },
              ],
              has_more: false,
              timezone: "America/Fortaleza",
            },
          });
        }
        if (url.pathname.endsWith("/verification/request"))
          return route.fulfill({
            status: 202,
            json: { challenge: "private-challenge-" + slug, message: "Código enviado." },
          });
        if (url.pathname.endsWith("/verification/confirm")) {
          if (request.postDataJSON().code !== "654321")
            return route.fulfill({ status: 400, json: { detail: "bad OTP" } });
          return route.fulfill({ json: { proof: "private-proof-" + slug } });
        }
        if (url.pathname.endsWith("/confirm")) {
          bookCalls++;
          confirmations.push(request.postDataJSON());
          if (["uncertain", "cancelled", "completed"].includes(scenario) && bookCalls === 1)
            return route.abort("failed");
          if (scenario === "conflict")
            return route.fulfill({ status: 409, json: { detail: "changed" } });
          await new Promise((resolve) => setTimeout(resolve, 150));
          return route.fulfill({
            json: {
              status: ["cancelled", "completed"].includes(scenario) ? scenario : "scheduled",
              reference: "private-receipt-" + slug,
              scheduled_for: "2031-11-13T09:00:00-03:00",
              service_name: "Atendimento de exemplo",
              duration_minutes: 30,
              price: "80.00",
            },
          });
        }
        throw Error("Unexpected visitor endpoint " + url.pathname);
      });
      async function open(mode) {
        scenario = mode;
        bookCalls = 0;
        confirmations.length = 0;
        await page.goto(
          origin + "/frontend/agendar.html?negocio=" + (width === 768 ? "brilho" : "bella"),
        );
        await page.getByRole("heading", { name: "Escolha o serviço", exact: true }).waitFor();
      }
      async function choose() {
        await page.locator('input[name="selection"]').first().check();
        await page.getByRole("button", { name: "Continuar", exact: true }).click();
      }
      async function untilSlots() {
        await choose();
        await page.getByRole("heading", { name: "Escolha quem vai atender" }).waitFor();
        await choose();
        await page.locator("#booking-date").fill("2031-11-13");
        await page.getByRole("button", { name: "Consultar horários" }).click();
        await page.getByRole("heading", { name: "Escolha um horário" }).waitFor();
      }
      async function untilReview() {
        await untilSlots();
        await choose();
        await page.locator("#booking-name").fill("Pessoa Teste");
        await page.locator("#booking-email").fill("visitante@example.test");
        await page.getByRole("button", { name: "Enviar código" }).click();
        await page.locator("#booking-code").fill("000000");
        await page.getByRole("button", { name: "Verificar e-mail" }).click();
        await page
          .getByText("Confira os dados informados e tente novamente.", { exact: true })
          .waitFor();
        await page.locator("#booking-code").fill("654321");
        await page.getByRole("button", { name: "Verificar e-mail" }).click();
        await page.getByRole("heading", { name: "Confira seu agendamento" }).waitFor();
        assert.equal(await page.locator("#booking-code").count(), 0);
      }
      async function privacy() {
        const html = await page.content();
        for (const value of [
          "private-service-",
          "private-resource-",
          "private-offer-",
          "private-challenge-",
          "private-proof-",
          "private-receipt-",
        ]) {
          assert.ok(!html.includes(value), "Opaque references must not become DOM fields");
          assert.ok(!page.url().includes(value));
        }
        assert.deepEqual(
          await page.evaluate(() => [localStorage.length, sessionStorage.length]),
          [0, 0],
        );
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      }
      await open("normal");
      await untilReview();
      await privacy();
      await page.getByRole("button", { name: "Confirmar agendamento", exact: true }).dblclick();
      await page.getByRole("heading", { name: "Agendamento confirmado", exact: true }).waitFor();
      assert.equal(bookCalls, 1, "Double click must not submit two confirmations");
      await privacy();
      fs.mkdirSync(path.resolve(__dirname, "../test-results/public-booking"), { recursive: true });
      await page.screenshot({
        path: path.resolve(
          __dirname,
          `../test-results/public-booking/${width}-${dark ? "dark" : "light"}.png`,
        ),
        fullPage: true,
      });
      journeys++;

      await open("uncertain");
      await untilReview();
      await page.getByRole("button", { name: "Confirmar agendamento", exact: true }).click();
      await page.getByRole("button", { name: "Verificar confirmação", exact: true }).waitFor();
      assert.equal(
        await page.getByRole("heading", { name: "Agendamento confirmado", exact: true }).count(),
        0,
      );
      assert.equal(await page.locator("#back").isVisible(), false);
      await page.getByRole("button", { name: "Verificar confirmação", exact: true }).click();
      await page.getByRole("heading", { name: "Agendamento confirmado", exact: true }).waitFor();
      assert.equal(bookCalls, 2);
      assert.deepEqual(confirmations[0], confirmations[1]);
      await privacy();
      journeys++;

      for (const [mode, title] of [
        ["cancelled", "Agendamento cancelado"],
        ["completed", "Atendimento concluído"],
      ]) {
        await open(mode);
        await untilReview();
        await page.getByRole("button", { name: "Confirmar agendamento", exact: true }).click();
        await page.getByRole("button", { name: "Verificar confirmação", exact: true }).click();
        await page.getByRole("heading", { name: title, exact: true }).waitFor();
        assert.equal(
          await page.getByRole("heading", { name: "Agendamento confirmado", exact: true }).count(),
          0,
        );
        assert.deepEqual(confirmations[0], confirmations[1]);
        await privacy();
        journeys++;
      }

      await open("conflict");
      await untilReview();
      await page.getByRole("button", { name: "Confirmar agendamento", exact: true }).click();
      await page.getByRole("heading", { name: "Escolha o serviço", exact: true }).waitFor();
      await page
        .getByText("O horário ou as condições mudaram. Consulte as opções novamente.", {
          exact: true,
        })
        .waitFor();
      assert.equal(
        await page.getByRole("heading", { name: "Agendamento confirmado", exact: true }).count(),
        0,
      );
      await privacy();
      journeys++;

      await open("empty");
      await untilSlots();
      await page
        .getByText("Não há horários livres nessa data. Volte para escolher outro dia.", {
          exact: true,
        })
        .waitFor();
      assert.equal(await page.locator("#next").isDisabled(), true);
      await privacy();
      journeys++;
      scenario = "off";
      await page.goto(origin + "/frontend/agendar.html?negocio=bella");
      await page.getByRole("heading", { name: "Agendamento indisponível", exact: true }).waitFor();
      const beforeRetry = requests.length;
      await Promise.all([
        page.waitForResponse(
          (response) =>
            new URL(response.url()).pathname === "/api/v1/public/booking/bella" &&
            response.status() === 503,
        ),
        page.getByRole("button", { name: "Tentar novamente", exact: true }).click(),
      ]);
      await page.getByRole("heading", { name: "Agendamento indisponível", exact: true }).waitFor();
      assert.ok(requests.length > beforeRetry, "Retry must perform a fresh visitor request");
      assert.ok(!(await page.content()).includes("private technical error"));
      await privacy();
      journeys++;
      assert.ok(requests.length > 0);
      assert.deepEqual(errors, []);
      assert.deepEqual(outside, []);
      await context.close();
    }
  }
  await staleResponse(browser, origin);
  return { publicBookingJourneys: journeys, staleScopeProtection: true, realProviderCalls: 0 };
}

async function staleResponse(browser, origin) {
  const page = await browser.newPage();
  let release, started;
  const pending = new Promise((resolve) => {
    release = resolve;
  });
  const began = new Promise((resolve) => {
    started = resolve;
  });
  await page.route("**/api/v1/public/booking/*", async (route) => {
    const bella = route.request().url().endsWith("/bella");
    if (bella) {
      started();
      await pending;
    }
    try {
      await route.fulfill({
        json: {
          name: bella ? "Bella Store" : "Brilho Limpeza",
          timezone: "America/Fortaleza",
          horizon_days: 30,
          server_date: "2031-11-12",
          services: [],
        },
      });
    } catch {}
  });
  await page.goto(origin + "/frontend/agendar.html?negocio=bella");
  await began;
  await page.evaluate(() => {
    history.pushState(null, "", "?negocio=brilho");
    dispatchEvent(new PopStateEvent("popstate"));
  });
  await page.getByRole("heading", { name: "Brilho Limpeza", exact: true }).waitFor();
  release();
  await page.waitForTimeout(100);
  assert.equal(await page.locator("#business-name").innerText(), "Brilho Limpeza");
  await page.close();
}

module.exports = validate;
if (require.main === module) {
  const { chromium } = require("playwright"),
    root = path.resolve(__dirname, "..");
  const server = http.createServer((req, res) => {
    const file = path.resolve(root, "." + new URL(req.url, "http://localhost").pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())
      return res.writeHead(404).end();
    res.setHeader(
      "Content-Type",
      {
        ".html": "text/html",
        ".css": "text/css",
        ".js": "text/javascript",
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
      console.log(await validate(browser, `http://127.0.0.1:${server.address().port}`));
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
