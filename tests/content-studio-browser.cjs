const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path"),
  http = require("node:http");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
module.exports = async function contentStudio(browser, origin) {
  const context = await browser.newContext({ reducedMotion: "reduce", acceptDownloads: true });
  const errors = [],
    external = [],
    writes = [];
  const output = path.join(root, "test-results/content-studio");
  fs.mkdirSync(output, { recursive: true });
  try {
    const page = await context.newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", (r) => {
      const request = r.request(),
        url = new URL(request.url());
      if (url.origin !== origin) {
        external.push(url.href);
        return r.abort();
      }
      if (request.method() !== "GET") writes.push(url.pathname);
      return r.continue();
    });
    await page.addInitScript(() => {
      window.mediaUrls = { created: [], revoked: [] };
      const create = URL.createObjectURL.bind(URL),
        revoke = URL.revokeObjectURL.bind(URL);
      URL.createObjectURL = (value) => {
        const url = create(value);
        window.mediaUrls.created.push(url);
        return url;
      };
      URL.revokeObjectURL = (url) => {
        window.mediaUrls.revoked.push(url);
        return revoke(url);
      };
    });
    await page.goto(origin + "/frontend/socialmei-app.html");
    await page.locator('[data-xp-go="app"]').first().click();
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => setView("Vendas"));
      const tabs = await page.locator("#nvTabs").evaluate((el) => {
        const bounds = el.getBoundingClientRect();
        return [...el.querySelectorAll("button")].map((b) => {
          const r = b.getBoundingClientRect();
          return {
            text: b.textContent.trim(),
            visible: r.left >= bounds.left && r.right <= bounds.right + 1,
            height: r.height,
          };
        });
      });
      assert.equal(tabs.length, 5);
      assert(tabs.every((t) => t.visible && t.height >= 44));
      await page.locator('[data-nv-tab="Financeiro"]').click();
      assert.equal(await page.evaluate(() => currentView), "Financeiro");
      await page.screenshot({
        path: path.join(output, `business-nav-${width}-light.png`),
        fullPage: true,
      });
    }
    await page.evaluate(
      () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
    );
    await page.locator("#utilityTools > summary").click();
    await page.evaluate(async () => {
      window.dispatchEvent(new Event("resize"));
      await new Promise((resolve) => setTimeout(resolve, 180));
    });
    assert.equal(
      await page.locator("#utilityTools").evaluate((e) => e.open),
      true,
      "Header resize must preserve the tools menu opened by the user",
    );
    await page.locator("#contentStudioOpen").click();
    assert.equal(await page.evaluate(() => currentView), "Divulgação");
    assert(await page.locator("#contentPublish").isDisabled());
    await page.evaluate(() => {
      SocialMEIBusinessProfile.browserRepository().save({
        completed: true,
        businessName: "Ateliê fictício",
        segment: "sewing",
        offers: ["services"],
        modules: ["clients"],
      });
      SocialMEIContentStudio.render();
    });
    assert.equal(await page.locator("#contentPreviewBusiness").textContent(), "Ateliê fictício");
    await page.locator("#contentSave").click();
    assert.equal(
      await page.locator("#contentTitle").evaluate((e) => e.validity.valueMissing),
      true,
    );
    await page.locator("#contentTitle").fill("Novidades do ateliê");
    await page
      .locator("#contentCaption")
      .fill("Conheça o trabalho do nosso ateliê. Conteúdo fictício para teste.");
    await page.locator("#contentCta").fill("Converse com a gente para saber mais.");
    await page.locator("#contentHashtags").fill("#ExemploFictício");
    await page.locator("#contentMedia").setInputFiles({
      name: "invalido.svg",
      mimeType: "image/svg+xml",
      buffer: Buffer.from("<svg/>"),
    });
    await page.waitForFunction(() =>
      document.querySelector("#contentActionStatus").textContent.includes("recusado"),
    );
    const png = await page.evaluate(() => {
      const canvas = document.createElement("canvas");
      canvas.width = 640;
      canvas.height = 800;
      const c = canvas.getContext("2d");
      c.fillStyle = "#1e73d8";
      c.fillRect(0, 0, 640, 800);
      c.fillStyle = "#f2b11b";
      c.fillRect(48, 70, 70, 6);
      c.fillStyle = "white";
      c.font = "bold 44px sans-serif";
      c.fillText("Seu negócio,", 48, 190);
      c.fillText("sua história.", 48, 245);
      c.font = "24px sans-serif";
      c.fillText("Conteúdo fictício para teste", 48, 700);
      return canvas.toDataURL("image/png").split(",")[1];
    });
    await page.locator("#contentMedia").setInputFiles({
      name: "conteudo-ficticio.png",
      mimeType: "image/png",
      buffer: Buffer.from(png, "base64"),
    });
    await page.locator("#contentPreviewStage img").waitFor();
    await page.locator("#contentSave").click();
    assert.match(await page.locator("#contentActionStatus").textContent(), /salvo neste navegador/);
    assert.equal(await page.locator(".content-draft-row").count(), 1);
    const saved = await page.evaluate(() =>
      Object.entries(localStorage).filter(([key]) =>
        key.startsWith("socialmei-content-drafts-v1:"),
      ),
    );
    assert.equal(saved.length, 1);
    assert(!saved[0][1].includes("blob:"));
    assert(!saved[0][1].includes("data:image"));
    await page.evaluate(() => {
      navigator.clipboard.writeText = async (text) => (window.copiedContent = text);
    });
    await page.locator("#contentCopy").click();
    assert.match(await page.evaluate(() => window.copiedContent), /#ExemploFictício/);
    await page.evaluate(() => {
      navigator.clipboard.writeText = async () => {
        throw Error("denied");
      };
    });
    await page.locator("#contentCopy").click();
    assert.match(
      await page.locator("#contentActionStatus").textContent(),
      /Não foi possível copiar/,
    );
    const download = page.waitForEvent("download");
    await page.locator("#contentExport").click();
    const exported = await download;
    const filename = path.join(output, "preparacao.txt");
    await exported.saveAs(filename);
    assert.match(fs.readFileSync(filename, "utf8"), /nenhuma publicação foi realizada/);
    assert.match(fs.readFileSync(filename, "utf8"), /Novidades do ateliê/);
    await page.locator("#contentTitle").fill("Alteração não salva");
    await page.locator("#contentNew").click();
    assert(
      await page.locator("#contentConfirmModal").evaluate((e) => e.classList.contains("open")),
    );
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      () => !document.querySelector("#contentConfirmModal").classList.contains("open"),
    );
    assert.equal(await page.locator("#contentTitle").inputValue(), "Alteração não salva");
    await page.locator("#contentNew").click();
    await page.locator("#contentConfirmAction").click();
    await page.waitForFunction(
      () => !document.querySelector("#contentConfirmModal").classList.contains("open"),
    );
    assert.equal(await page.locator("#contentTitle").inputValue(), "");
    await page.locator('[data-content-action="edit"]').first().click();
    assert.match(await page.locator("#contentMediaStatus").textContent(), /Selecione novamente/);
    assert.equal(await page.locator("#contentPreviewStage img").count(), 0);
    await page.locator('[data-content-action="duplicate"]').first().click();
    assert.equal(await page.locator(".content-draft-row").count(), 2);
    await page.locator('[data-content-action="delete"]').first().click();
    await page.locator("#contentConfirmAction").click();
    await page.waitForFunction(
      () => !document.querySelector("#contentConfirmModal").classList.contains("open"),
    );
    assert.equal(await page.locator(".content-draft-row").count(), 1);
    await page.locator('[data-content-action="edit"]').click();
    await page.locator("#contentCaption").fill('<img src=x onerror="window.contentXss=true">');
    await page.locator("#contentSave").click();
    assert.equal(await page.locator("#contentPreviewCaption img").count(), 0);
    assert(!(await page.evaluate(() => window.contentXss)));
    await page
      .locator("#contentCaption")
      .fill("Conheça o trabalho do nosso ateliê. Conteúdo fictício para teste.");
    await page.locator("#contentSave").click();
    let layouts = 0;
    for (const width of [320, 390, 768, 1024, 1280, 1440])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((t) => SocialMEIThemes.select(t), theme);
        for (const format of ["feed", "story", "reel"]) {
          await page.locator(`[data-content-format="${format}"]`).click();
          if (format !== "reel") {
            await page.locator("#contentMedia").setInputFiles({
              name: "conteudo-ficticio.png",
              mimeType: "image/png",
              buffer: Buffer.from(png, "base64"),
            });
            await page.locator("#contentPreviewStage img").waitFor();
          }
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          assert.equal(
            await page.locator(`[data-content-format="${format}"]`).getAttribute("aria-selected"),
            "true",
          );
          if ([390, 1440].includes(width))
            await page.screenshot({
              path: path.join(output, `${format}-${width}-${theme}.png`),
              fullPage: true,
            });
          layouts++;
        }
      }
    const webm = await page.evaluate(async () => {
      const canvas = document.createElement("canvas");
      canvas.width = 320;
      canvas.height = 480;
      const c = canvas.getContext("2d");
      c.fillStyle = "#1e73d8";
      c.fillRect(0, 0, 320, 480);
      const stream = canvas.captureStream(5),
        chunks = [];
      const recorder = new MediaRecorder(stream, { mimeType: "video/webm" });
      const blob = await new Promise((resolve) => {
        recorder.ondataavailable = (e) => chunks.push(e.data);
        recorder.onstop = () => resolve(new Blob(chunks, { type: "video/webm" }));
        recorder.start();
        setTimeout(() => recorder.stop(), 250);
      });
      stream.getTracks().forEach((t) => t.stop());
      return [...new Uint8Array(await blob.arrayBuffer())];
    });
    await page.locator("#contentMedia").setInputFiles({
      name: "video-ficticio.webm",
      mimeType: "video/webm",
      buffer: Buffer.from(webm),
    });
    await page.locator("#contentPreviewStage video").waitFor();
    assert(await page.locator("#contentPreviewStage video").evaluate((v) => v.paused));
    await page.screenshot({ path: path.join(output, "reel-video-1440-dark.png"), fullPage: true });
    await page.locator('[data-content-format="feed"]').click();
    assert.equal(await page.locator("#contentPreviewStage video").count(), 0);
    assert.match(await page.locator("#contentActionStatus").textContent(), /compatível/);
    await page.locator('[data-content-format="feed"]').focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(
      await page
        .locator('[data-content-format="reel"]')
        .evaluate((e) => e === document.activeElement),
      true,
    );
    await page.keyboard.press("Home");
    assert.equal(
      await page.locator('[data-content-format="story"]').getAttribute("aria-selected"),
      "true",
    );
    await page.emulateMedia({ reducedMotion: "no-preference" });
    assert.match(
      await page
        .locator(".content-format-indicator")
        .evaluate((e) => getComputedStyle(e).transitionDuration),
      /0\.24s/,
    );
    await page.emulateMedia({ reducedMotion: "reduce" });
    assert.equal(
      await page
        .locator(".content-format-indicator")
        .evaluate((e) => getComputedStyle(e).transitionDuration),
      "0s",
    );
    await page.evaluate(() => {
      window.oldStorageSet = Storage.prototype.setItem;
      Storage.prototype.setItem = function (k, v) {
        if (k.startsWith("socialmei-content-drafts")) throw Error("quota");
        return window.oldStorageSet.call(this, k, v);
      };
    });
    await page.locator("#contentTitle").fill("Falha de armazenamento");
    await page.locator("#contentSave").click();
    assert.match(
      await page.locator("#contentActionStatus").textContent(),
      /Não foi possível salvar/,
    );
    await page.evaluate(() => {
      Storage.prototype.setItem = window.oldStorageSet;
    });
    await page.evaluate(() =>
      sessionStorage.setItem("socialmei-business-demo-identity", "different-business"),
    );
    await page.evaluate(() => setView("Início"));
    await page.evaluate(() => setView("Divulgação"));
    assert.equal(await page.locator("#contentTitle").inputValue(), "");
    assert.equal(await page.locator(".content-draft-row").count(), 0);
    const urls = await page.evaluate(() => window.mediaUrls);
    assert(urls.revoked.length > 0);
    await page.evaluate(() => sessionStorage.removeItem("socialmei-business-demo-identity"));
    await page.reload();
    await page.evaluate(() => SocialMEIExperience.enterApp("Divulgação"));
    assert.equal(await page.locator(".content-draft-row").count(), 1);
    assert.equal(await page.locator("#contentPreviewStage img").count(), 0);
    const connected = await browser.newContext({ reducedMotion: "reduce" });
    try {
      let workspace = 21;
      const account = await connected.newPage();
      account.on("pageerror", (e) => errors.push(e.message));
      await account.route("**/*", (route) => {
        const request = route.request(),
          url = new URL(request.url());
        if (url.origin !== origin) {
          external.push(url.href);
          return route.abort();
        }
        if (url.pathname === "/frontend/config.js")
          return route.fulfill({
            contentType: "text/javascript",
            body: 'const SOCIALMEI_CONFIG={n8nMessagesUrl:null,auth:{mode:"remote",apiBaseUrl:"/api/v1"},clientes:{mode:"remote",apiBaseUrl:"/api/v1",workspaceKey:"content-test"}};',
          });
        if (url.pathname.startsWith("/api/v1/")) {
          if (request.method() !== "GET") writes.push(url.pathname);
          return route.fulfill({
            json:
              url.pathname === "/api/v1/auth/session"
                ? {
                    usuario: {
                      id: 12,
                      nome: "Conta sintética",
                      email: "teste@example.com",
                      administrador_plataforma: false,
                    },
                    negocio: {
                      id: workspace,
                      slug: "workspace-" + workspace,
                      nome: "Negócio fictício " + workspace,
                      configuracao: {},
                    },
                    papel: "owner",
                    csrf_token: "a".repeat(64),
                  }
                : url.pathname === "/api/v1/auth/registration"
                  ? { mode: "open" }
                  : [],
          });
        }
        return route.continue();
      });
      const enter = async () => {
        await account.goto(origin + "/frontend/socialmei-app.html");
        await account.waitForFunction(
          () => typeof SocialMEIAuth !== "undefined" && SocialMEIAuth.current,
        );
        await account.evaluate(() => SocialMEIExperience.enterApp("Divulgação"));
      };
      await enter();
      await account.locator("#contentTitle").fill("Rascunho privado A");
      await account.locator("#contentCaption").fill("Texto privado de teste");
      await account.locator("#contentSave").click();
      assert.equal(await account.locator(".content-draft-row").count(), 1);
      workspace = 22;
      await enter();
      assert.equal(await account.locator(".content-draft-row").count(), 0);
      assert.equal(await account.locator("#contentTitle").inputValue(), "");
      assert(
        !(await account.locator("#contentStudioView").textContent()).includes(
          "Texto privado de teste",
        ),
      );
      workspace = 21;
      await enter();
      assert.equal(await account.locator(".content-draft-row").count(), 1);
      assert(await account.locator("#contentPublish").isDisabled());
      const raw = await account.evaluate(() => {
        const key = Object.keys(localStorage).find(
          (k) =>
            k.startsWith("socialmei-content-drafts-v1:") &&
            k.includes(encodeURIComponent("account:12:workspace:21")),
        );
        const raw = localStorage.getItem(key);
        localStorage.setItem(key, "invalid json");
        return { key, raw };
      });
      await account.evaluate(() => SocialMEIContentStudio.render());
      assert.match(
        await account.locator("#contentStorageStatus").textContent(),
        /Não foi possível ler/,
      );
      assert(await account.locator("#contentSave").isDisabled());
      assert.equal(await account.locator(".content-draft-row").count(), 0);
      await account.evaluate(({ key, raw }) => {
        localStorage.setItem(key, raw);
        SocialMEIContentStudio.render();
      }, raw);
      assert.equal(await account.locator(".content-draft-row").count(), 1);
    } finally {
      await connected.close();
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert.deepEqual(writes, []);
    fs.writeFileSync(
      path.join(output, "results.json"),
      JSON.stringify(
        {
          layouts,
          widths: [320, 390, 768, 1024, 1280, 1440],
          themes: ["light", "dark"],
          errors,
          external,
          writes,
        },
        null,
        2,
      ),
    );
    return `Divulgação: ${layouts} layouts, CRUD local, confirmação, mídia real imagem/vídeo, formatos, copiar/falha, exportação, quota, XSS, isolamento, teclado e movimento reduzido passaram.`;
  } finally {
    await context.close();
  }
};

if (require.main === module) {
  const server = http.createServer((request, response) => {
    const file = path.resolve(root, "." + new URL(request.url, "http://local").pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404).end();
      return;
    }
    response.setHeader(
      "Content-Type",
      {
        ".html": "text/html",
        ".js": "text/javascript",
        ".css": "text/css",
        ".woff2": "font/woff2",
      }[path.extname(file)] || "application/octet-stream",
    );
    fs.createReadStream(file).pipe(response);
  });
  (async () => {
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    let browser;
    try {
      browser = await chromium.launch(
        process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {},
      );
      console.log(await module.exports(browser, `http://127.0.0.1:${server.address().port}`));
    } finally {
      await browser?.close();
      server.close();
    }
  })().catch((error) => {
    console.error(error);
    server.close();
    process.exitCode = 1;
  });
}
