/* SocialMEI-IA v7.6 · Seletor de negócios (somente modo conectado).
   Reutiliza GET /auth/workspaces e auth.switchWorkspace(): o contrato, o isolamento de dados e as permissões não mudam. */
(() => {
  "use strict";
  const auth = window.SocialMEIAuth;
  if (!auth?.remote || window.SocialMEIv76Switcher) return;
  const ROLE = { owner: "Proprietário", admin: "Administrador", member: "Equipe", viewer: "Somente consulta", report_viewer: "Acompanhamento (somente leitura)" };
  const scope = () => auth.current && `${auth.current.usuario.id}:${auth.current.negocio.id}`;
  const el = (t, c, txt) => { const n = document.createElement(t); if (c) n.className = c; if (txt !== undefined) n.textContent = txt; return n; };
  const initials = (s) => String(s || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  const say = (m) => { if (typeof toast === "function") toast(m); };
  let menu = null, opener = null, busy = false;

  function close(restore = true) {
    if (!menu) return;
    menu.remove(); document.querySelector(".sw76-scrim")?.remove(); menu = null;
    document.querySelectorAll("[data-business-menu]").forEach((b) => b.setAttribute("aria-expanded", "false"));
    if (restore && opener?.isConnected) opener.focus();
  }
  function overlay(name) {
    const o = el("div", "sw76-busy"); o.setAttribute("role", "status"); o.setAttribute("aria-live", "polite");
    const sp = el("span", "sw76-spin"); sp.setAttribute("aria-hidden", "true");
    o.append(sp, el("p", "", "Alternando para " + name + "…"), el("small", "", "Carregando clientes, agenda e vendas deste negócio."));
    document.body.append(o); return o;
  }
  async function choose(item, list) {
    if (busy) return; busy = true;
    list.querySelectorAll("button").forEach((b) => (b.disabled = true));
    close(false);
    const o = overlay(item.nome);
    try { await auth.switchWorkspace(item.id); } // recarrega a página com dados e sessão do novo negócio
    catch (e) { o.remove(); busy = false; say(e?.message || "Não foi possível trocar de negócio. Você continua em " + auth.current.negocio.nome + "."); }
  }
  async function open(anchor) {
    if (menu) return close();
    opener = anchor; anchor.setAttribute("aria-expanded", "true");
    const expected = scope();
    const scrim = el("div", "sw76-scrim"); scrim.onclick = () => close();
    menu = el("div", "sw76-menu"); menu.setAttribute("role", "dialog"); menu.setAttribute("aria-label", "Trocar de negócio");
    const head = el("div", "sw76-head"); head.append(el("b", "", "Meus negócios"), el("small", "", "Cada negócio tem seus próprios clientes, agenda, vendas e conversas."));
    const list = el("ul", "sw76-list"); list.setAttribute("role", "listbox"); list.setAttribute("aria-label", "Negócios disponíveis");
    const status = el("p", "sw76-status", "Carregando seus negócios…"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
    const foot = el("a", "sw76-foot", "Gerenciar negócios"); foot.href = "#/config/conta"; foot.onclick = () => close(false);
    menu.append(head, status, list, foot);
    document.body.append(scrim, menu);
    menu.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      const opts = [...menu.querySelectorAll("button.sw76-opt:not(:disabled), a.sw76-foot")], k = opts.indexOf(document.activeElement);
      if (e.key === "ArrowDown") { e.preventDefault(); opts[(k + 1) % opts.length]?.focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); opts[(k - 1 + opts.length) % opts.length]?.focus(); }
      else if (e.key === "Tab" && opts.length) { const f = opts[0], l = opts[opts.length - 1]; if (e.shiftKey && document.activeElement === f) { e.preventDefault(); l.focus(); } else if (!e.shiftKey && document.activeElement === l) { e.preventDefault(); f.focus(); } }
    });
    try {
      const r = await auth.request("/auth/workspaces");
      if (!menu || scope() !== expected) return; // resposta antiga: o contexto mudou ou o menu foi fechado
      status.textContent = r.items.length > 1 ? "" : "Você tem apenas este negócio por enquanto.";
      status.hidden = r.items.length > 1;
      for (const it of r.items) {
        const active = it.id === r.active_workspace_id, li = el("li"), b = el("button", "sw76-opt");
        b.type = "button"; b.setAttribute("role", "option"); b.setAttribute("aria-selected", String(active)); if (active) b.setAttribute("aria-current", "true");
        const av = el("span", "sw76-av", initials(it.nome)); av.setAttribute("aria-hidden", "true");

        /* SM_WORKSPACE_MENU_LOGO_V1 */
        const logo = it.logo;
        if (typeof logo === 'string' &&
            logo.length <= 2000000 &&
            /^data:image\/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(logo)) {
          const img = document.createElement('img');
          img.alt = '';
          img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:inherit;display:block;';
          img.addEventListener('error', () => {
            av.replaceChildren(initials(it.nome));
          }, {once:true});
          img.src = logo;
          av.replaceChildren(img);
        }

        const tx = el("span", "sw76-tx"); tx.append(el("b", "", it.nome), el("small", "", active ? "Negócio ativo" + (it.papel && ROLE[it.papel] ? " · " + ROLE[it.papel] : "") : ROLE[it.papel] || "Alternar para este negócio"));
        b.append(av, tx); if (active) b.append(el("span", "sw76-ck", "✓"));
        if (!active) b.onclick = () => choose(it, list); else b.onclick = () => close();
        li.append(b); list.append(li);
      }
      (list.querySelector('[aria-current]') || list.querySelector("button"))?.focus();
    } catch (e) {
      if (!menu || scope() !== expected) return;
      status.textContent = (e?.message || "Não foi possível carregar seus negócios.") + " Tente novamente."; status.dataset.err = "1";
      const retry = el("button", "sw76-retry", "Tentar de novo"); retry.type = "button"; retry.onclick = () => { close(false); open(anchor); }; status.after(retry); retry.focus();
    }
  }

  function enhance() {
    if (!auth.current) return;
    const nome = auth.current.negocio.nome;
    document.querySelectorAll("[data-business-menu]").forEach((a) => {
      if (a.dataset.sw76 !== nome) {
        a.dataset.sw76 = nome; a.replaceChildren();
        const av = el("span", "sw76-av sm", initials(nome)); av.setAttribute("aria-hidden", "true");
        a.append(av, el("span", "sw76-name", nome));
        a.title = "Negócio ativo: " + nome + ". Clique para trocar.";
        a.setAttribute("aria-label", "Negócio ativo: " + nome + ". Trocar de negócio");
        a.setAttribute("aria-haspopup", "dialog"); a.setAttribute("aria-expanded", "false"); a.setAttribute("role", "button");
      }
    });
    const pop = document.querySelector('.pop[data-for="ws"]');
    if (pop && !pop.querySelector("[data-sw76-side]")) {
      const b = el("button", "sw76-side", "Trocar de negócio…"); b.type = "button"; b.dataset.sw76Side = "1";
      b.onclick = (e) => { e.stopPropagation(); const t = document.querySelector("[data-business-menu]") || e.currentTarget; open(t); };
      pop.prepend(b);
    }
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest?.("[data-business-menu]");
    if (a) { e.preventDefault(); e.stopImmediatePropagation(); open(a); }
  }, true);
  window.SocialMEIv76Switcher = { open, close, enhance };
  const prevRender = window.render;
  if (typeof prevRender === "function") window.render = function (...a) { const r = prevRender.apply(this, a); queueMicrotask(enhance); setTimeout(enhance, 60); return r; };
  window.addEventListener("hashchange", () => { close(false); setTimeout(enhance, 60); });
  setTimeout(enhance, 120); setTimeout(enhance, 600);
})();
