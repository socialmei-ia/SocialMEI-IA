const assert = require("node:assert/strict");
module.exports = async function transferFlows(browser, origin, errors) {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  let accepted = false,
    confirmations = 0,
    created = 0,
    requests = 0;
  const packet = {
    formato: "socialmei-workspace-transfer",
    versao_formato: 1,
    origem: "d82a45f6-6b1a-4544-a71c-2a8f2be8c085",
    workspace_origem: "development",
    exportado_em: "2026-10-12T00:00:00Z",
    clientes: [{ id: 11 }],
    produtos: [{ id: 21 }],
    vendas: [{ id: 31 }],
    financeiro: [],
  };
  const preview = {
    origem: packet.origem,
    workspace_destino: "team",
    ja_transferido: false,
    preview_token: "a".repeat(64),
    fonte: { clientes: 1, produtos: 1, vendas: 1, financeiro: 0 },
    destino_atual: { clientes: 1, produtos: 0, vendas: 0, financeiro: 0 },
    vendas_com_baixa_preservada: 1,
    vendas_excluidas: 0,
    financeiro_excluido: 0,
  };
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", async (route) => {
    const req = route.request(),
      url = new URL(req.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname.endsWith("/config.js"))
      return route.fulfill({
        contentType: "application/javascript",
        body: `const source={mode:"remote",apiBaseUrl:"/api/v1",workspaceKey:"team"};const SOCIALMEI_CONFIG={clientes:source,produtos:source,vendas:source,financeiro:source};`,
      });
    if (!url.pathname.includes("/api/v1/transferencias/")) return route.continue();
    requests++;
    const data = req.postDataJSON();
    if (url.pathname.endsWith("/preview")) {
      assert.deepEqual(data, packet);
      return route.fulfill({ json: { ...preview, ja_transferido: accepted } });
    }
    assert.equal(data.preview_token, preview.preview_token);
    assert.deepEqual(data.pacote, packet);
    confirmations++;
    if (!accepted) {
      accepted = true;
      created++;
      return route.abort();
    }
    return route.fulfill({
      json: {
        origem: packet.origem,
        workspace_destino: "team",
        ja_transferido: true,
        quantidades: preview.fonte,
        mapa_ids: { clientes: { 11: 2 }, produtos: { 21: 1 }, vendas: { 31: 1 }, financeiro: {} },
      },
    });
  });
  await page.goto(origin + "/frontend/transferencia.html");
  const upload = (data) =>
    page.locator("#packetFile").setInputFiles({
      name: "transfer.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(data)),
    });
  await upload({ wrong: "backup" });
  await page.waitForFunction(() =>
    document.getElementById("status").textContent.includes("data:export"),
  );
  assert.equal(requests, 0);
  await upload(packet);
  await page.locator("#previewButton").click();
  await page.waitForFunction(() => !document.getElementById("preview").hidden);
  assert.equal(await page.locator("#counts tr").count(), 4);
  assert(await page.locator("#confirmButton").isDisabled());
  await page.locator("#acknowledge").check();
  await page.locator("#confirmButton").click();
  await page.waitForFunction(() =>
    document.getElementById("status").textContent.includes("Preserve o mesmo arquivo"),
  );
  assert.equal(created, 1);
  assert(await page.locator("#confirmButton").isDisabled());
  await page.locator("#previewButton").click();
  await page.waitForFunction(() => !document.getElementById("receiptButton").hidden);
  assert.equal(created, 1);
  assert.equal(confirmations, 2);
  assert(await page.locator("#confirmButton").isDisabled());
  assert((await page.locator("#status").innerText()).includes("sem criar novos registros"));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await page.close();
  return "Transferência: arquivo inválido bloqueado, prévia explícita, confirmação, resposta perdida recuperada sem duplicar e layout móvel";
};
