/* SocialMEI v7.5 — same presentation with real authenticated data. */
(() => {
  "use strict";
  if (!window.SocialMEIV22?.remote || window.SocialMEIConnectedParity) return;
  const app = document.getElementById("app");
  if (!app) return;
  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "styles/v75-connected-parity.css?release=75-parity2";
  document.head.appendChild(style);
  const state = { scope: "", tools: false, replies: false, lastJob: "" };
  let raf = 0;
  function identity() {
    const a = window.SocialMEIV22.identity;
    return a ? `${a.usuario.id}:${a.negocio.id}:${location.hash}` : "";
  }
  function drawer(parent, kind, label, before) {
    let d = parent.querySelector(`:scope > details[data-v75-drawer="${kind}"]`);
    if (!d) {
      d = document.createElement("details");
      d.dataset.v75Drawer = kind;
      d.className = "v75-drawer";
      const summary = document.createElement("summary");
      const title = document.createElement("span");
      title.textContent = label;
      const status = document.createElement("small");
      status.dataset.v75Status = "true";
      summary.append(title, status);
      const body = document.createElement("div");
      body.className = "v75-drawer-body";
      d.append(summary, body);
      d.open = state[kind];
      d.addEventListener("toggle", () => {
        if (d.isConnected && state.scope === identity()) state[kind] = d.open;
      });
      if (before && before.parentNode === parent) before.before(d);
      else parent.append(d);
    }
    return d;
  }
  function move(d, nodes) {
    const body = d.querySelector(".v75-drawer-body");
    for (const node of nodes) if (node.parentNode !== body) body.append(node);
  }
  function text(node, value) { if (node.textContent !== value) node.textContent = value; }
  function paint() {
    raf = 0;
    const scope = identity();
    if (state.scope !== scope) Object.assign(state, {scope, tools:false, replies:false, lastJob:""});
    if (!/^#\/caixa\/me-\d+$/.test(location.hash)) return;
    const thread = app.querySelector("#v .ct"), ms = thread?.querySelector(".ms"), cp = thread?.querySelector(".cp");
    if (!thread || !ms || !cp) return;
    const tools = [...thread.querySelectorAll("[data-inbox-customer],[data-assist-suggestions],[data-assist-draft],[data-wa-bot]")];
    if (tools.length) {
      const d = drawer(thread,"tools","Ferramentas da conversa",ms);
      move(d,tools);
      text(d.querySelector("[data-v75-status]"),"Cliente, assistente e atendimento");
    }
    const replies = [...cp.querySelectorAll("[data-wa-replies],[data-ig-reply],[data-ig-reply-unavailable]")];
    if (replies.length) {
      const d = drawer(cp,"replies","Revisão e histórico",null);
      move(d,replies);
      const reply = replies[0];
      const job = reply.querySelector("select")?.value || "";
      const status = reply.querySelector("[data-wa-reply-status],[data-ig-reply-status]")?.textContent?.trim() || "";
      text(d.querySelector("[data-v75-status]"), status || "Ver respostas registradas");
      const critical = /incert|diverg|não confirmad|não foi possível|sem confirmação|não pode ser validada|não repita/i.test(status);
      if ((job && job !== state.lastJob) || critical) {
        state.replies = true; d.open = true;
      }
      state.lastJob = job;
    }
  }
  function schedule() { if (!raf) raf = requestAnimationFrame(paint); }
  app.addEventListener("click", e => {
    const target = e.target.closest?.("[data-wa-prepare],[data-ig-prepare]");
    if (target) {
      state.replies = true;
      const d = target.closest(".cp")?.querySelector('[data-v75-drawer="replies"]');
      if (d) d.open = true;
    }
  }, true);
  new MutationObserver(schedule).observe(app,{childList:true,subtree:true,characterData:true});
  window.addEventListener("hashchange",schedule);
  window.SocialMEIConnectedParity = {version:"75-parity2"};
  schedule();
})();
