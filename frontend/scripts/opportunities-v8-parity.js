/* Local planning sidecar only. Commercial writes remain in opportunity-lifecycle-store. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIOpportunityV8Planning = api;
})(globalThis, function () {
  "use strict";
  const copy = (value) => JSON.parse(JSON.stringify(value));
  const empty = () => ({
    amount: 0,
    date: "",
    note: "",
    contacted: false,
    updatedAt: 0,
    events: [],
  });
  function parseMoney(input) {
    const text = String(input ?? "").trim();
    if (!text) return 0;
    if (!/^(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?$/.test(text)) return NaN;
    const value = Number(text.replace(/\./g, "").replace(",", "."));
    return Number.isFinite(value) && value >= 0 && value <= 1e9 ? value : NaN;
  }
  function validDate(value) {
    if (value === "") return true;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const d = new Date(value + "T12:00:00Z");
    return Number.isFinite(d.getTime()) && d.toISOString().slice(0, 10) === value;
  }
  function normalize(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return empty();
    return {
      amount:
        Number.isFinite(value.amount) && value.amount >= 0 && value.amount <= 1e9
          ? value.amount
          : 0,
      date: validDate(value.date) ? value.date : "",
      note: typeof value.note === "string" ? value.note.slice(0, 140) : "",
      contacted: !!value.contacted,
      updatedAt: Number.isSafeInteger(value.updatedAt) && value.updatedAt > 0 ? value.updatedAt : 0,
      events: Array.isArray(value.events)
        ? value.events
            .filter((e) => e && Number.isSafeInteger(e.t) && e.t > 0 && typeof e.s === "string")
            .slice(-20)
            .map((e) => ({ t: e.t, s: e.s.slice(0, 250) }))
        : [],
    };
  }
  function createRepository(options) {
    let current = null,
      items = {};
    const key = (scope) => "socialmei-op8-local-v1:" + encodeURIComponent(scope);
    const validId = (id) => typeof id === "string" && /^[a-z0-9-]{8,80}$/i.test(id);
    function sync() {
      const next = options.scope() || "";
      if (next === current) return;
      current = next;
      items = {};
      if (!next) return;
      try {
        const value = JSON.parse(options.storage.getItem(key(next)));
        if (
          value?.v !== 1 ||
          value.scope !== next ||
          !value.items ||
          typeof value.items !== "object" ||
          Array.isArray(value.items)
        )
          return;
        for (const [id, metadata] of Object.entries(value.items).slice(0, 100))
          if (validId(id)) items[id] = normalize(metadata);
      } catch {
        /* A malformed sidecar never replaces the authenticated CRM snapshot. */
      }
    }
    function persist(next) {
      try {
        options.storage.setItem(
          key(current),
          JSON.stringify({ v: 1, scope: current, items: next }),
        );
      } catch {
        throw new Error(
          "Não foi possível salvar o planejamento neste navegador. Seus campos foram preservados.",
        );
      }
      items = next;
    }
    function guard(id) {
      sync();
      if (!current || !options.writable())
        throw new Error("Este acesso é somente leitura ou ainda não carregou os dados.");
      if (!validId(id) || !options.exists(id))
        throw new Error("Oportunidade indisponível no negócio atual.");
    }
    return Object.freeze({
      rawCandidates() {
        const scope = options.scope() || "";
        if (!scope) return [];
        try {
          const value = JSON.parse(options.storage.getItem(key(scope)));
          if (
            value?.v !== 1 ||
            value.scope !== scope ||
            !value.items ||
            typeof value.items !== "object" ||
            Array.isArray(value.items)
          )
            return [];
          return Object.entries(value.items)
            .slice(0, 100)
            .filter(([id]) => validId(id) && options.exists(id))
            .map(([id, legacy]) => ({ id, scope, legacy: copy(legacy) }));
        } catch {
          return [];
        }
      },
      get(id) {
        sync();
        return copy(items[id] || empty());
      },
      all() {
        sync();
        return copy(items);
      },
      save(id, patch) {
        guard(id);
        if (
          patch.amount !== undefined &&
          (!Number.isFinite(patch.amount) || patch.amount < 0 || patch.amount > 1e9)
        )
          throw new Error("Confira o valor estimado.");
        if (patch.date !== undefined && !validDate(patch.date))
          throw new Error("Confira a data de retorno.");
        if (patch.note !== undefined && (typeof patch.note !== "string" || patch.note.length > 140))
          throw new Error("A anotação deve ter até 140 caracteres.");
        const before = items[id] ? copy(items[id]) : null;
        const after = normalize({ ...empty(), ...before, ...patch, updatedAt: Date.now() });
        const next = { ...items, [id]: after };
        persist(next);
        return { scope: current, id, before, after: copy(after) };
      },
      undo(receipt) {
        sync();
        if (!receipt || receipt.scope !== current)
          throw new Error("A sessão ou o negócio mudou. Não foi desfeito.");
        guard(receipt.id);
        if (JSON.stringify(items[receipt.id]) !== JSON.stringify(receipt.after))
          throw new Error("Existe uma edição mais recente. Não foi desfeito.");
        const next = { ...items };
        if (receipt.before) next[receipt.id] = copy(receipt.before);
        else delete next[receipt.id];
        persist(next);
        return true;
      },
    });
  }
  return Object.freeze({ createRepository, parseMoney, validDate });
});
