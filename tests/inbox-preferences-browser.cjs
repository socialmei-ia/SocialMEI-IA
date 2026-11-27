const assert = require("node:assert/strict");

module.exports = async (browser, origin) => {
  for (const width of [390, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    const errors = [];
    const calls = [];
    const rows = [2, 3].map(id => ({
      id, channel: "whatsapp", origin: "waha", revision: 2, account_ref: "waha:111@c.us",
      contact_ref: "waha:" + id + "@lid", contact_name: "Contato " + id,
      unread: true, unread_count: 2, last_inbound_id: 70 + id,
      messages: [{id: 70 + id, text: "Mensagem de teste", occurred_at: "2026-11-27T10:00:00Z"}],
    }));
    const archived = new Set();
    page.on("pageerror", error => errors.push(error.message));
    page.on("dialog", dialog => dialog.accept());
    await page.addInitScript(() => localStorage.setItem("socialmei-auth-browser-scope", "91:17"));
    await page.route("**/*", route => {
      const req = route.request();
      const url = new URL(req.url());
      if (url.origin !== origin) return route.abort();
      if (url.pathname === "/frontend/config.js")
        return route.fulfill({contentType: "text/javascript",
          body: 'const SOCIALMEI_CONFIG={auth:{mode:"remote",apiBaseUrl:"/api/v1"}};'});
      if (!url.pathname.startsWith("/api/v1/")) return route.continue();
      switch (url.pathname.slice("/api/v1".length)) {
      case "/auth/session":
        return route.fulfill({json: {usuario: {id: 91, nome: "Teste", email: "teste@example.test"},
          negocio: {id: 17, nome: "Fixture", slug: "fixture", configuracao: {}},
          papel: "owner", csrf_token: "a".repeat(64)}});
      case "/auth/preferences":
        return route.fulfill({json: {preferences: {}}});
      case "/workspace-profile":
        return route.fulfill({json: {profile: {}}});
      case "/message-enrichment/capabilities":
        return route.fulfill({json: {mode: "disabled", waha_inbox: true}});
      case "/message-enrichment/conversations":
        return route.fulfill({json: {workspace_id: 17, items: rows.filter(row => !archived.has(row.id))}});
      case "/message-enrichment/archived-conversations":
        return route.fulfill({json: {workspace_id: 17, items: rows.filter(row => archived.has(row.id))}});
      case "/message-enrichment/inbox-preferences": {
        assert.equal(req.method(), "POST");
        assert.equal(req.headers()["x-socialmei-identity"], "91:17");
        assert.equal(req.headers()["x-socialmei-csrf"], "a".repeat(64));
        const payload = req.postDataJSON();
        calls.push(payload);
        const {action, conversation_ids: ids} = payload;
        if (action === "read" || action === "unread") {
          const row = rows.find(item => item.id === ids[0]);
          row.unread = action === "unread";
          row.unread_count = 0;
        } else if (action === "archive" || action === "unarchive") {
          for (const id of ids) if (action === "archive") archived.add(id); else archived.delete(id);
        } else {
          const row = rows.find(item => item.id === ids[0]);
          if (action === "pin") row.pinned = true;
          if (action === "snooze") row.snoozed_until = payload.snoozed_until;
          if (action === "unsnooze") row.snoozed_until = null;
        }
        return route.fulfill({json: {workspace_id: 17, action, conversation_ids: ids}});
      }
      default:
        return route.fulfill({json: []});
      }
    });
    try {
      await page.goto(origin + "/frontend/socialmei-app.html#/caixa");
      const row = page.getByRole("link", {name: /Contato 2.*2 mensagens não lidas/});
      await row.waitFor();
      await row.click();
      const more = page.getByRole("button", {name: "Mais ações da conversa"});
      await more.click();
      await page.getByRole("menuitem", {name: "Marcar como lida", exact: true}).click();
      await page.waitForResponse(r => r.url().endsWith("/message-enrichment/conversations"));
      assert.deepEqual(calls[0], {action: "read", conversation_ids: [2], read_through_id: 72});
      if (!(await page.getByRole("menuitem", {name: "Fixar no topo"}).isVisible())) await more.click();
      await page.getByRole("menuitem", {name: "Fixar no topo"}).click();
      await page.getByRole("img", {name: "Conversa fixada", exact: true}).waitFor();
      if (!(await page.getByRole("menuitem", {name: "Adiar conversa"}).isVisible())) await more.click();
      await page.getByRole("menuitem", {name: "Adiar conversa"}).click();
      await page.getByRole("button", {name: "Daqui a 1 hora", exact: true}).click();
      await page.getByText(/Adiada at?/).waitFor();
      await page.reload();
      await page.getByText(/Adiada at?/).waitFor();
      await page.getByRole("button", {name: "Reativar", exact: true}).click();
      await page.getByText(/Adiada at?/).waitFor({state: "hidden"});
      assert.deepEqual(calls.slice(1,4).map(call => call.action), ["pin", "snooze", "unsnooze"]);
      await page.goto(origin + "/frontend/socialmei-app.html#/caixa");
      await page.getByRole("button", {name: "Selecionar conversas"}).click();
      const dialog = page.locator("dialog[open]");
      for (const id of [2, 3]) await dialog.getByRole("checkbox", {name: new RegExp("Contato " + id)}).check();
      await dialog.getByRole("button", {name: "Arquivar selecionadas"}).click();
      await dialog.getByText("Alteração confirmada.").waitFor();
      assert.deepEqual([...archived].sort(), [2, 3]);
      await dialog.getByRole("button", {name: "Fechar"}).click();
      await page.getByRole("button", {name: "Conversas arquivadas"}).click();
      await dialog.getByRole("checkbox", {name: /Contato 2/}).check();
      await dialog.getByRole("button", {name: "Desarquivar selecionadas"}).click();
      await dialog.getByText("Alteração confirmada.").waitFor();
      assert.deepEqual([...archived], [3]);
      await dialog.getByRole("button", {name: "Fechar"}).click();
      await page.getByRole("link", {name: /Contato 2/}).waitFor();
      assert.deepEqual(errors, []);
    } finally {
      await context.close();
    }
  }
};
