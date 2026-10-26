/* Same-origin V22 frame integration. No credentials cross postMessage. */
window.V22Frame = (() => {
  let remote = false,
    parentAuth;
  try {
    parentAuth = window.parent !== window ? window.parent.SocialMEIAuth : null;
    remote = !!parentAuth?.remote;
  } catch {}
  if (remote) {
    const user = parentAuth.current;
    if (!user) {
      document.documentElement.hidden = true;
      throw Error("Sessão ausente.");
    }
    const prefix = `smei-v22-account:${user.usuario.id}:${user.negocio.id}:`;
    for (const method of ["getItem", "setItem", "removeItem"]) {
      const original = Storage.prototype[method];
      Storage.prototype[method] = function (key, ...args) {
        return original.call(
          this,
          this === localStorage &&
            /^smei(?:-|4_)/.test(String(key)) &&
            !String(key).startsWith("smei-v22-account:")
            ? prefix + key
            : key,
          ...args,
        );
      };
    }
  }
  async function parentReady() {
    for (let count = 0; count < 250; count++) {
      if (window.parent.SocialMEIV22) {
        await window.parent.SocialMEIV22.ready;
        return window.parent.SocialMEIV22;
      }
      await new Promise((resolve) => setTimeout(resolve, 40));
    }
    throw Error("Não foi possível carregar os dados do negócio.");
  }
  let mediaManifest = null;
  document.addEventListener(
    "change",
    (event) => {
      if (event.target.id === "file") {
        const file = event.target.files[0];
        mediaManifest = file ? { name: file.name, mime: file.type, size: file.size } : null;
      }
    },
    true,
  );
  document.addEventListener(
    "click",
    (event) => {
      if (event.target.closest("#clr")) mediaManifest = null;
    },
    true,
  );
  let rows = new Map();
  let lastId = null;
  let host;
  const localDate = (value) =>
    value
      ? `${new Date(value).getFullYear()}-${String(new Date(value).getMonth() + 1).padStart(2, "0")}-${String(new Date(value).getDate()).padStart(2, "0")}`
      : null;
  async function load() {
    host = await parentReady();
    const result = await host.request("/opportunities");
    rows = new Map(result.items.map((row) => [row.id, row]));
    return result.items.map(project);
  }
  const project = (row) => ({
    id: row.id,
    c: row.client_name,
    w: row.title,
    i: row.interest_level === "unknown" ? "analysis" : row.interest_level,
    r: row.outcome,
    n: row.planning_note,
    u: Date.parse(row.updated_at),
    f: row.follow_up_date ? new Date(row.follow_up_date + "T12:00:00").getTime() : null,
    v: Number(row.estimated_amount),
    h: [{ t: Date.parse(row.updated_at), s: "Registro compartilhado do negócio." }],
    reason: row.outcome_note,
  });
  async function history(id) {
    const result = await host.request("/opportunities/" + id + "/history");
    return result.items
      .slice()
      .reverse()
      .map((event) => ({
        t: Date.parse(event.created_at),
        s:
          ({
            create: "Oportunidade criada",
            edit: "Registro atualizado",
            close: "Negociação encerrada",
            reopen: "Negociação reaberta",
            sale: "Venda vinculada",
          }[event.action] || event.action) + (event.reason ? " · " + event.reason : ""),
      }));
  }

  async function persist(before, after) {
    const changed = after.filter(
      (row) => JSON.stringify(row) !== JSON.stringify(before.find((old) => old.id === row.id)),
    );
    if (changed.length !== 1 || after.length < before.length)
      throw Error("Esta alteração exige uma operação individual do servidor.");
    const row = changed[0],
      previous = rows.get(row.id);
    let path = "/opportunities" + (previous ? "/" + previous.id : ""),
      method = previous ? "PATCH" : "POST";
    let payload = {
      title: row.w,
      interest_level: row.i === "analysis" ? "unknown" : row.i,
      estimated_amount: row.v,
      follow_up_date: localDate(row.f),
      planning_note: row.n || "",
      ...(row.h?.at(-1)?.s === "Contato registrado" ? { contacted: true } : {}),
    };
    if (!previous) {
      const clients = host.clients.filter((c) => c.nome === row.c);
      if (clients.length !== 1) throw Error("Selecione um cliente com nome único.");
      payload.client_id = clients[0].id;
    } else {
      payload.expected_revision = previous.revision;
      if (row.r !== previous.outcome) {
        method = "POST";
        if (row.r === "open") {
          path += "/reopen";
          payload = {
            expected_revision: previous.revision,
            reason: (row.h?.at(-1)?.s || "").replace(/^Oportunidade reaberta — /, ""),
          };
        } else {
          path += "/close";
          payload = {
            expected_revision: previous.revision,
            outcome: row.r,
            reason: row.r === "won" ? "sale_completed" : "other",
            note: row.reason || "",
          };
        }
      }
    }
    const result = await host.write(path, method, payload, true);
    rows.set(result.id, result);
    return [...rows.values()].map(project);
  }
  return {
    remote,
    parentReady,
    load,
    persist,
    get lastId() {
      return lastId;
    },
    history,
    get mediaManifest() {
      return mediaManifest;
    },
    get clients() {
      return host?.clients || [];
    },
  };
})();
