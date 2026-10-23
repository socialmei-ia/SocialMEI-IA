// Synthetic transport fixture; never used by the application or an external host.
const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
module.exports = function fixture() {
  const identity = {
    usuario: { id: 101, nome: "Maiccon", email: "visual@example.test" },
    negocio: { id: 201, slug: "visual-v8", nome: "Negócio de Maiccon", configuracao: {} },
    papel: "owner",
    csrf_token: "a".repeat(64),
  };
  const names = [
    "Ana (Salão Bela Vista)",
    "Carlos (Loja Moda Viva)",
    "Dona Rita (Assistência TecFix)",
    "Paulo (Studio de Fotos)",
    "Juliana (Confeitaria Doce Hora)",
    "Marcos (Marketing Local)",
  ];
  const clients = names.map((nome, index) => ({ id: index + 1, nome, versao: 1, tags: [] }));
  const titles = [
    "Corte e escova",
    "Atacado de camisetas",
    "Troca de tela",
    "Ensaio de fim de ano",
    "Bolo para 40 pessoas",
    "Gestão de redes sociais",
  ];
  const rows = clients.map((client, index) => ({
    id: randomUUID(),
    workspace_id: 201,
    client_id: client.id,
    client_name: client.nome,
    title: titles[index],
    interest_level: ["hot", "warm", "unknown", "cold", "hot", "warm"][index],
    outcome: index === 4 ? "won" : index === 5 ? "lost" : "open",
    outcome_reason: index === 4 ? "sale_completed" : index === 5 ? "price" : null,
    outcome_note: "",
    sale_id: null,
    revision: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }));
  const profileAPI = require("./profile-sync-fixture.cjs")();
  const events = new Map(
    rows.map((row) => [
      row.id,
      [{ action: "create", created_at: row.created_at, actor_id: 101, current: { ...row } }],
    ]),
  );
  const writes = [],
    replay = new Map();
  let conflict = false,
    fail = false,
    historyGate = null;
  const api = {
    identity,
    clients,
    rows,
    writes,
    events,
    setConflict: (v) => (conflict = v),
    setFailure: (v) => (fail = v),
    holdHistory: () => new Promise((resolve) => (historyGate = resolve)),
    releaseHistory: () => {
      historyGate?.();
      historyGate = null;
    },
  };
  api.install = async (page, origin) => {
    await page.route("**/*", async (route) => {
      const req = route.request(),
        url = new URL(req.url());
      if (url.origin !== origin) return route.abort();
      const path = url.pathname;
      if (path === "/frontend/config.js")
        return route.fulfill({
          contentType: "application/javascript",
          body:
            "const SOCIALMEI_CONFIG=" +
            JSON.stringify({
              n8nMessagesUrl: null,
              auth: { mode: "remote", apiBaseUrl: "/api/v1" },
              clientes: { mode: "remote", apiBaseUrl: "/api/v1", workspaceKey: "v8-fixture" },
              instagramPublisher: { mode: "disabled" },
              instagramSimulation: { mode: "disabled" },
            }) +
            ";",
        });
      if (!path.startsWith("/api/v1/")) return route.continue();
      if (path === "/api/v1/auth/session") return route.fulfill({ json: identity });
      if (path === "/api/v1/auth/registration") return route.fulfill({ json: { mode: "open" } });
      if (["/api/v1/workspace-profile", "/api/v1/auth/preferences"].includes(path))
        return profileAPI(route, identity);
      if (path === "/api/v1/clientes")
        return route.fulfill({ json: identity.negocio.id === 201 ? clients : [] });
      const prefix = "/api/v1/opportunities";
      if (!path.startsWith(prefix)) {
        assert.equal(req.method(), "GET", "No unrelated write");
        return route.fulfill({ json: [] });
      }
      if (req.method() === "GET") {
        if (path.endsWith("/history")) {
          if (historyGate)
            await new Promise((resolve) => {
              const previous = historyGate;
              historyGate = () => {
                previous();
                resolve();
              };
            });
          const id = path.slice(prefix.length + 1, -8);
          return route.fulfill({
            json: { workspace_id: identity.negocio.id, items: events.get(id) || [] },
          });
        }
        return route.fulfill({
          json: {
            workspace_id: identity.negocio.id,
            items: identity.negocio.id === 201 ? rows : [],
          },
        });
      }
      assert.equal(req.headers()["x-socialmei-csrf"], identity.csrf_token);
      const body = req.postDataJSON();
      assert(body.operation_id);
      writes.push({ path, method: req.method(), body });
      if (fail)
        return route.fulfill({
          status: 503,
          json: { detail: "Falha sintética sem fallback local" },
        });
      if (conflict) {
        conflict = false;
        return route.fulfill({
          status: 409,
          json: { detail: "Conflito sintético. Atualize antes de salvar." },
        });
      }
      if (replay.has(body.operation_id))
        return route.fulfill({ json: replay.get(body.operation_id) });
      let row, action;
      if (path === prefix) {
        const client = clients.find((c) => c.id === body.client_id);
        assert(client);
        row = {
          id: randomUUID(),
          workspace_id: identity.negocio.id,
          client_id: client.id,
          client_name: client.nome,
          title: body.title,
          interest_level: body.interest_level,
          outcome: "open",
          revision: 1,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        rows.unshift(row);
        action = "create";
      } else {
        row = rows.find((r) => r.id === path.slice(prefix.length + 1).split("/")[0]);
        assert(row);
        assert.equal(body.expected_revision, row.revision);
        if (path.endsWith("/close")) {
          assert(["won", "lost"].includes(body.outcome));
          row.outcome = body.outcome;
          row.outcome_reason = body.reason;
          row.outcome_note = body.note;
          action = "close";
        } else if (path.endsWith("/reopen")) {
          assert(body.reason);
          row.outcome = "open";
          action = "reopen";
        } else if (path.endsWith("/sale")) {
          row.sale_id = body.sale_id;
          action = "sale";
        } else {
          assert(["unknown", "cold", "warm", "hot"].includes(body.interest_level));
          row.interest_level = body.interest_level;
          action = "edit";
        }
        row.revision++;
        row.updated_at = new Date().toISOString();
      }
      const history = events.get(row.id) || [];
      history.unshift({
        action,
        created_at: row.updated_at,
        actor_id: identity.usuario.id,
        reason: body.reason,
        note: body.note,
        current: { ...row },
      });
      events.set(row.id, history);
      replay.set(body.operation_id, { ...row });
      return route.fulfill({ status: action === "create" ? 201 : 200, json: row });
    });
  };
  api.seedPlanning = async (page) =>
    page.addInitScript(
      ({ items }) =>
        localStorage.setItem(
          "socialmei-op8-local-v1:" + encodeURIComponent("101|201|"),
          JSON.stringify({ v: 1, scope: "101|201|", items }),
        ),
      {
        items: Object.fromEntries(
          rows.map((row, index) => {
            const d = new Date();
            d.setDate(d.getDate() + [-1, 2, 1, 4, 0, 0][index]);
            return [
              row.id,
              {
                amount: [450, 1200, 380, 900, 280, 1500][index],
                date: index < 4 ? d.toLocaleDateString("sv-SE") : "",
                note: "",
                contacted: false,
              },
            ];
          }),
        ),
      },
    );
  return api;
};
