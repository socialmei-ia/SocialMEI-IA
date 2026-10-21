/* Commercial decisions are server records, separate from heuristic demonstrations. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIOpportunityLifecycle = api;
})(globalThis, function () {
  "use strict";
  const INTEREST = Object.freeze({
    unknown: "Em análise",
    cold: "Frio",
    warm: "Morno",
    hot: "Quente",
  });
  const OUTCOME = Object.freeze({
    open: "Em andamento",
    won: "Venda realizada",
    lost: "Não avançou",
  });
  const REASONS = Object.freeze({
    gave_up: "Desistiu",
    other_supplier: "Comprou em outro lugar",
    price: "Preço",
    timing: "Prazo ou momento",
    other: "Outro motivo",
    sale_completed: "Venda realizada",
  });
  const copy = (value) => JSON.parse(JSON.stringify(value));
  function counts(items) {
    const totals = { open: 0, unknown: 0, cold: 0, warm: 0, hot: 0, won: 0, lost: 0 };
    for (const row of items) {
      if (row.outcome === "open") {
        totals.open++;
        if (row.interest_level in INTEREST) totals[row.interest_level]++;
      } else if (row.outcome === "won" || row.outcome === "lost") totals[row.outcome]++;
    }
    return totals;
  }
  function valid(row) {
    if (
      !row ||
      typeof row.id !== "string" ||
      !Number.isSafeInteger(row.client_id) ||
      row.client_id < 1 ||
      !Number.isSafeInteger(row.revision) ||
      row.revision < 1 ||
      typeof row.title !== "string" ||
      typeof row.client_name !== "string" ||
      !Object.hasOwn(INTEREST, row.interest_level) ||
      !Object.hasOwn(OUTCOME, row.outcome)
    )
      throw new Error("Resposta inválida de Oportunidades. Atualize antes de salvar.");
    return row;
  }
  function createStore(options) {
    let scope = "",
      items = [],
      ready = false,
      busy = false,
      problem = "",
      generation = 0;
    const pending = new Map();
    const notify = () => options.change?.();
    function sync() {
      const value = options.identity();
      const next =
        value && Number.isSafeInteger(value.usuario?.id) && Number.isSafeInteger(value.negocio?.id)
          ? `${value.usuario.id}|${value.negocio.id}|${value.scope || ""}`
          : "";
      if (next !== scope) {
        scope = next;
        items = [];
        ready = false;
        busy = false;
        problem = "";
        generation++;
        pending.clear();
      }
      return value && next ? value : null;
    }
    function capture() {
      const identity = sync();
      if (!identity) throw new Error("Entre na sua conta para consultar oportunidades.");
      return { scope, generation, workspace: identity.negocio.id, role: identity.papel };
    }
    function check(context) {
      sync();
      if (context.scope !== scope || context.generation !== generation)
        throw new Error("A sessão mudou. Confira a conta atual.");
    }
    async function request(path, method, body, context) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 12000);
      try {
        const response = await options.fetch(
          new URL("/api/v1/opportunities" + path, options.origin).href,
          {
            method,
            credentials: "same-origin",
            cache: "no-store",
            signal: controller.signal,
            headers: {
              Accept: "application/json",
              ...(options.headers?.() || {}),
              ...(body ? { "Content-Type": "application/json" } : {}),
            },
            ...(body ? { body: JSON.stringify(body) } : {}),
          },
        );
        check(context);
        let result;
        try {
          result = await response.json();
        } catch {
          throw new Error("Resposta indisponível. Confira a conexão e atualize.");
        }
        check(context);
        if (!response.ok) {
          const error = new Error(
            typeof result?.detail === "string"
              ? result.detail
              : "Não foi possível concluir a operação.",
          );
          error.status = response.status;
          throw error;
        }
        if (result?.workspace_id !== context.workspace)
          throw new Error("A resposta pertence a outro negócio e foi recusada.");
        return result;
      } finally {
        clearTimeout(timer);
      }
    }
    async function reload() {
      const context = capture();
      if (busy) throw new Error("Aguarde a operação em andamento.");
      busy = true;
      ready = false;
      problem = "";
      notify();
      try {
        const result = await request("", "GET", null, context);
        if (!Array.isArray(result.items) || result.items.length > 100)
          throw new Error("Lista de oportunidades inválida.");
        const next = result.items.map(valid);
        check(context);
        items = next;
        ready = true;
        return copy(next);
      } catch (error) {
        if (scope === context.scope) problem = error.message;
        throw error;
      } finally {
        if (scope === context.scope && generation === context.generation) {
          busy = false;
          notify();
        }
      }
    }
    async function write(path, method, payload) {
      const context = capture();
      if (!["owner", "admin", "member"].includes(context.role))
        throw new Error("Este acesso é somente leitura.");
      if (busy) throw new Error("Aguarde a operação em andamento.");
      const key = JSON.stringify([context.scope, path, method, payload]);
      if (!pending.has(key)) pending.set(key, globalThis.crypto.randomUUID());
      const body = { ...payload, operation_id: pending.get(key) };
      busy = true;
      problem = "";
      notify();
      try {
        const result = valid(await request(path, method, body, context));
        check(context);
        const previous = items.find((row) => row.id === result.id);
        if (!previous || previous.revision <= result.revision)
          items = [result, ...items.filter((row) => row.id !== result.id)].slice(0, 100);
        pending.delete(key);
        ready = true;
        return copy(result);
      } catch (error) {
        if (scope === context.scope) {
          problem = error.message;
          if (!error.status || error.status === 401 || error.status >= 500) ready = false;
        }
        throw error;
      } finally {
        if (scope === context.scope && generation === context.generation) {
          busy = false;
          notify();
        }
      }
    }
    async function history(id) {
      const context = capture();
      const result = await request("/" + encodeURIComponent(id) + "/history", "GET", null, context);
      if (!Array.isArray(result.items)) throw new Error("Histórico indisponível.");
      return copy(result.items);
    }
    return Object.freeze({
      reload,
      history,
      create: (data) => write("", "POST", data),
      update: (row, data) =>
        write("/" + encodeURIComponent(row.id), "PATCH", {
          ...data,
          expected_revision: row.revision,
        }),
      close: (row, outcome, reason, note = "") =>
        write("/" + encodeURIComponent(row.id) + "/close", "POST", {
          expected_revision: row.revision,
          outcome,
          reason,
          note,
        }),
      reopen: (row, reason) =>
        write("/" + encodeURIComponent(row.id) + "/reopen", "POST", {
          expected_revision: row.revision,
          reason,
        }),
      linkSale: (row, sale_id) =>
        write("/" + encodeURIComponent(row.id) + "/sale", "POST", {
          expected_revision: row.revision,
          sale_id,
        }),
      snapshot() {
        const identity = sync();
        return {
          scope,
          items: copy(items),
          ready,
          busy,
          problem,
          role: identity?.papel || "",
          totals: counts(items),
        };
      },
      clear() {
        scope = "";
        items = [];
        ready = false;
        busy = false;
        problem = "";
        generation++;
        pending.clear();
        notify();
      },
    });
  }
  return Object.freeze({ createStore, counts, INTEREST, OUTCOME, REASONS });
});
