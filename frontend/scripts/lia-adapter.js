/* SocialMEI-IA · v7.7 · Lia — adaptador modular de IA generativa (opcional).
   ESTADO NESTA VERSÃO: nenhum adaptador registrado e nenhum endpoint de IA conhecido → a Lia usa somente assistência local
   (navegação, orientação, comandos e leitura de dados já carregados na tela). Nada aqui chama a rede por conta própria.

   Para ligar uma IA no futuro (sem mexer no restante):
     1) o servidor expõe um endpoint próprio, com a chave de API SOMENTE no servidor (nunca no navegador);
     2) um script de integração chama SocialMEILiaAdapter.register({ id, label, scope, ask });
     3) config.js habilita: lia: { genAI: { mode: "adapter", adapterId: "<id>" } }.
   Contrato de ask({ text, context, history, signal }) → Promise<{ text: string, actions?: [{type:"nav",path}|{type:"form",id}] }>
     • context contém apenas: mode, route, title, role, locale e a lista de ids de recursos disponíveis. Nunca registros do negócio.
     • text é exibido como texto puro (sem HTML). actions são revalidadas pela Lia contra a lista de telas/formulários conhecidos;
       qualquer coisa fora dela é descartada. Gravações, envios, cobranças e publicações continuam passando pelos formulários e
       confirmações existentes — a resposta de uma IA nunca executa nada sozinha. */
(() => {
  "use strict";
  if (window.SocialMEILiaAdapter) return;
  const adapters = new Map();
  const cfg = () => {
    try {
      return (typeof SOCIALMEI_CONFIG !== "undefined" && SOCIALMEI_CONFIG.lia && SOCIALMEI_CONFIG.lia.genAI) || {};
    } catch (_) { return {}; }
  };
  const scopes = (a) => (Array.isArray(a.scope) ? a.scope : [a.scope || "public", ...(a.scope ? [] : ["app"])]);

  function register(adapter) {
    if (!adapter || typeof adapter.id !== "string" || !/^[a-z0-9-]{2,40}$/.test(adapter.id)) throw new Error("Adaptador inválido: id.");
    if (typeof adapter.ask !== "function") throw new Error("Adaptador inválido: ask().");
    adapters.set(adapter.id, Object.freeze({ label: String(adapter.label || adapter.id).slice(0, 40), ...adapter }));
    window.dispatchEvent(new CustomEvent("socialmei-lia-adapter-change"));
  }
  function unregister(id) {
    if (adapters.delete(id)) window.dispatchEvent(new CustomEvent("socialmei-lia-adapter-change"));
  }
  function active(scope) {
    const c = cfg();
    if (c.mode !== "adapter") return null;
    const a = adapters.get(c.adapterId);
    if (!a || !scopes(a).includes(scope)) return null;
    return a;
  }
  function status(scope) {
    const c = cfg();
    if (c.mode !== "adapter") return { available: false, reason: "disabled", label: "" };
    const a = active(scope);
    if (!a) return { available: false, reason: "missing", label: "" };
    let ok = true;
    try { if (typeof a.isAvailable === "function") ok = !!a.isAvailable(); } catch (_) { ok = false; }
    if (typeof navigator !== "undefined" && navigator.onLine === false) return { available: false, reason: "offline", label: a.label };
    return ok ? { available: true, reason: "", label: a.label } : { available: false, reason: "unavailable", label: a.label };
  }
  /* v7.8 · timeout efetivo: o prazo é imposto por Promise.race, então vale mesmo que o provedor ignore o AbortSignal.
     Um sinal externo (troca de empresa/usuário/sessão) cancela do mesmo modo, e uma resposta tardia é sempre descartada. */
  async function ask(scope, payload, timeoutMs = 20000) {
    const st = status(scope);
    if (!st.available) throw Object.assign(new Error("IA indisponível."), { code: st.reason });
    const a = active(scope);
    const outer = payload && payload.signal;
    if (outer && outer.aborted) throw Object.assign(new Error("A IA não respondeu."), { code: "aborted" });
    const ctl = new AbortController();
    let timer = 0, onOuter = null, settle = null, why = "";
    const stop = new Promise((_, reject) => {
      settle = (code) => { if (why) return; why = code; try { ctl.abort(); } catch (_) {} reject(Object.assign(new Error("A IA não respondeu."), { code })); };
      timer = setTimeout(() => settle("timeout"), Math.max(1, timeoutMs));
      if (outer) { onOuter = () => settle("aborted"); outer.addEventListener("abort", onOuter, { once: true }); }
    });
    stop.catch(() => {});
    try {
      const { signal: _ignored, ...rest } = payload || {};
      let call;
      try { call = Promise.resolve(a.ask({ ...rest, signal: ctl.signal })); } catch (e) { call = Promise.reject(e); }
      call.catch(() => {});
      const out = await Promise.race([call, stop]);
      if (why) throw Object.assign(new Error("A IA não respondeu."), { code: why });
      const text = typeof out?.text === "string" ? out.text.trim().slice(0, 2000) : "";
      if (!text) throw Object.assign(new Error("Resposta vazia."), { code: "empty" });
      return { text, actions: Array.isArray(out.actions) ? out.actions.slice(0, 4) : [], label: a.label };
    } catch (e) {
      throw Object.assign(new Error("A IA não respondeu."), { code: why || e.code || "error" });
    } finally { clearTimeout(timer); if (outer && onOuter) outer.removeEventListener("abort", onOuter); }
  }
  window.SocialMEILiaAdapter = Object.freeze({ register, unregister, status, ask });
})();
