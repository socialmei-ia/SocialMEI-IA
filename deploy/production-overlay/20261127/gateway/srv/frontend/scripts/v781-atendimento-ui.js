/* SocialMEI-IA · v7.8.1 · Atendimento conectado: componentes Premium compartilhados (WhatsApp e Instagram).
   Só interface. Não cria endpoints, não envia, não repete envios e não grava dados:
   quem decide e executa cada operação continua sendo o script do canal (v22-whatsapp-replies / v22-instagram-direct).
   Oferece: diálogo de confirmação, revisão e envio com resultado, histórico de operações e o painel do compositor. */
(() => {
  "use strict";
  if (window.SocialMEIAtendimentoUI) return;
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const IC = {
    send: '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    warn: '<path d="M12 3 2 21h20L12 3zM12 10v5M12 18v.01"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.01"/>',
    eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    save: '<path d="M5 3h11l3 3v15H5zM8 3v6h7V3M8 21v-7h8v7"/>',
    quote: '<path d="M9 7 4 12l5 5M4 12h11a5 5 0 0 1 5 5"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  };
  const svg = (name, size = 18) =>
    `<svg class="sm-ic" viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IC[name] || ""}</svg>`;
  const icon = (name, size) => {
    const w = el("span", "sm-ico");
    w.innerHTML = svg(name, size);
    return w;
  };
  const spinner = () => {
    const s = el("span", "sm-spin");
    s.setAttribute("aria-hidden", "true");
    return s;
  };
  const initials = (name) =>
    String(name || "?")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase() || "")
      .join("") || "?";

  /* ---------- diálogo base ---------- */
  const live = new Set();
  let seq = 0;
  function restore(prev) {
    const target =
      prev?.isConnected && !prev.disabled
        ? prev
        : document.querySelector("[data-sm-primary]:not(:disabled)") || document.getElementById("ta");
    try {
      target?.focus({ preventScroll: true });
    } catch {}
  }
  function base({ label, cls = "", dismissible = () => true }) {
    const dlg = el("dialog", "sm-dlg " + cls);
    const inner = el("div", "sm-dlg-in");
    dlg.append(inner);
    const id = "sm-dlg-t" + ++seq;
    dlg.setAttribute("aria-labelledby", id);
    const prev = document.activeElement;
    dlg.addEventListener("cancel", (e) => {
      if (!dismissible()) e.preventDefault();
    });
    dlg.addEventListener("click", (e) => {
      if (e.target === dlg && dismissible()) dlg.close();
    });
    dlg.addEventListener("close", () => {
      live.delete(dlg);
      dlg.remove();
      restore(prev);
    });
    return {
      dlg,
      inner,
      titleId: id,
      show() {
        live.add(dlg);
        document.body.append(dlg);
        dlg.showModal();
        (dlg.querySelector("[data-autofocus]") || dlg.querySelector("button"))?.focus();
      },
    };
  }
  const head = (b, ic, title, sub, tone) => {
    const h = el("header", "sm-dlg-head");
    const chip = el("span", "sm-dlg-chip");
    chip.dataset.tone = tone || "info";
    chip.innerHTML = svg(ic, 20);
    const t = el("div", "sm-dlg-ttl");
    const h2 = el("h2", "", title);
    h2.id = b.titleId;
    t.append(h2);
    if (sub) t.append(el("p", "sm-dlg-sub", sub));
    h.append(chip, t);
    return h;
  };
  function closeAll() {
    for (const d of [...live]) if (!d.dataset.busy) d.close();
  }

  /* ---------- confirmação simples ---------- */
  function confirm({ title, body = [], detail = "", confirmLabel = "Continuar", cancelLabel = "Cancelar", tone = "info", icon: ic = "info" }) {
    return new Promise((resolve) => {
      let answer = false;
      const b = base({ label: title, cls: "sm-dlg-confirm" });
      b.inner.append(head(b, ic, title, "", tone));
      const content = el("div", "sm-dlg-body");
      for (const t of [].concat(body)) content.append(el("p", "", t));
      if (detail) content.append(el("blockquote", "sm-dlg-quote", detail));
      const foot = el("footer", "sm-dlg-foot");
      const cancel = el("button", "btn o", cancelLabel);
      cancel.type = "button";
      cancel.dataset.autofocus = "true";
      const ok = el("button", "btn", confirmLabel);
      ok.type = "button";
      cancel.onclick = () => b.dlg.close();
      ok.onclick = () => {
        answer = true;
        b.dlg.close();
      };
      foot.append(cancel, ok);
      b.inner.append(content, foot);
      b.dlg.addEventListener("close", () => resolve(answer));
      b.show();
    });
  }

  /* ---------- revisar e enviar (a confirmação e o resultado acontecem na mesma janela) ---------- */
  function review(o) {
    return new Promise((resolve) => {
      let busy = false,
        outcome = null;
      const b = base({ label: o.title, cls: "sm-dlg-review", dismissible: () => !busy });
      b.inner.append(head(b, "send", o.title || "Revisar antes de enviar", o.channelLabel, "info"));
      const content = el("div", "sm-dlg-body");
      const to = el("div", "sm-rv-to");
      const av = el("span", "sm-rv-av", initials(o.recipient));
      av.setAttribute("aria-hidden", "true");
      const who = el("div", "sm-rv-who");
      who.append(el("small", "", "Para"), el("b", "", o.recipient || "Contato da conversa"));
      to.append(av, who);
      const bubble = el("div", "sm-rv-bubble", o.text);
      bubble.tabIndex = 0;
      bubble.setAttribute("aria-label", "Mensagem que será enviada");
      const note = el("p", "sm-rv-note");
      note.setAttribute("role", "status");
      note.setAttribute("aria-live", "polite");
      note.dataset.tone = o.canConfirm ? "info" : "warn";
      note.textContent = o.canConfirm ? o.note || "Ao confirmar, a mensagem será enviada de verdade." : o.blockedReason || "Envio indisponível.";
      content.append(to, bubble, note);
      const foot = el("footer", "sm-dlg-foot");
      const cancel = el("button", "btn o", "Voltar e editar");
      cancel.type = "button";
      cancel.dataset.autofocus = "true";
      const ok = el("button", "btn", o.confirmLabel || "Confirmar envio");
      ok.type = "button";
      ok.disabled = !o.canConfirm;
      cancel.onclick = () => {
        if (!busy) b.dlg.close();
      };
      ok.onclick = async () => {
        if (busy || !o.canConfirm) return;
        busy = true;
        b.dlg.dataset.busy = "1";
        ok.disabled = cancel.disabled = true;
        b.dlg.dataset.phase = "sending";
        note.replaceChildren(spinner(), document.createTextNode(" " + (o.sendingText || "Enviando. Não feche esta janela.")));
        note.dataset.tone = "busy";
        let out;
        try {
          out = await o.run();
        } catch (error) {
          out = { tone: "err", title: "Não foi possível confirmar", text: (error && error.message) || "Consulte as respostas antes de qualquer nova tentativa. Nada será repetido automaticamente." };
        }
        outcome = out || { tone: "warn", title: "Consulte a situação", text: "O resultado não foi reconhecido. Nada será repetido automaticamente." };
        busy = false;
        delete b.dlg.dataset.busy;
        b.dlg.dataset.phase = "result";
        const res = el("div", "sm-rv-result");
        res.dataset.tone = outcome.tone || "info";
        res.setAttribute("role", outcome.tone === "err" ? "alert" : "status");
        const ring = el("span", "sm-rv-ring");
        ring.innerHTML = svg(outcome.tone === "ok" ? "check" : outcome.tone === "err" ? "x" : "warn", 26);
        const tx = el("div", "sm-rv-rtx");
        tx.append(el("b", "", outcome.title || ""), el("span", "", outcome.text || ""));
        res.append(ring, tx);
        content.replaceChildren(res);
        const close = el("button", "btn", "Fechar");
        close.type = "button";
        close.dataset.autofocus = "true";
        close.onclick = () => b.dlg.close();
        foot.replaceChildren(close);
        close.focus();
      };
      foot.append(cancel, ok);
      b.inner.append(content, foot);
      b.dlg.addEventListener("close", () => resolve(outcome));
      b.show();
    });
  }

  /* ---------- histórico de operações ---------- */
  function history({ title = "Histórico de respostas", items, selectedId, onPick, onNew, canNew, newLabel = "Nova resposta" }) {
    const b = base({ label: title, cls: "sm-dlg-sheet" });
    const h = head(b, "clock", title, items.length ? items.length + (items.length === 1 ? " operação" : " operações") : "", "info");
    const x = el("button", "sm-x");
    x.type = "button";
    x.setAttribute("aria-label", "Fechar histórico");
    x.innerHTML = svg("x", 18);
    x.onclick = () => b.dlg.close();
    h.append(x);
    const content = el("div", "sm-dlg-body");
    if (!items.length) content.append(el("p", "sm-hist-empty", "Nenhuma resposta registrada nesta conversa ainda."));
    const list = el("ul", "sm-hist");
    for (const it of items) {
      const li = el("li");
      const btn = el("button", "sm-hist-it");
      btn.type = "button";
      btn.dataset.tone = it.tone || "info";
      if (it.id === selectedId) btn.setAttribute("aria-current", "true");
      const top = el("span", "sm-hist-top");
      top.append(el("b", "", it.label), el("span", "sm-hist-time", it.time || ""));
      btn.append(top, el("span", "sm-hist-tx", it.text));
      btn.onclick = () => {
        b.dlg.close();
        onPick?.(it.id);
      };
      li.append(btn);
      list.append(li);
    }
    content.append(list);
    const foot = el("footer", "sm-dlg-foot");
    if (canNew) {
      const nw = el("button", "btn o", newLabel);
      nw.type = "button";
      nw.onclick = () => {
        b.dlg.close();
        onNew?.();
      };
      foot.append(nw);
    }
    const close = el("button", "btn", "Fechar");
    close.type = "button";
    close.onclick = () => b.dlg.close();
    foot.append(close);
    b.inner.append(h, content, foot);
    b.show();
    (list.querySelector("[aria-current]") || list.querySelector("button") || close).focus();
    list.querySelector("[aria-current]")?.scrollIntoView({ block: "center" });
  }

  /* ---------- painel do compositor ---------- */
  const panels = new WeakMap();
  const STEPS = ["Preparar", "Revisar", "Enviar"];
  const stepStates = {
    loading: ["todo", "todo", "todo"],
    compose: ["current", "todo", "todo"],
    pending: ["warn", "todo", "todo"],
    review: ["done", "current", "todo"],
    sending: ["done", "done", "busy"],
    accepted: ["done", "done", "done"],
    uncertain: ["done", "done", "warn"],
    blocked: ["done", "done", "err"],
  };
  const stamp = (iso) => {
    const d = new Date(iso);
    if (!iso || Number.isNaN(+d)) return "";
    const t = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    return d.toDateString() === new Date().toDateString() ? "hoje, " + t : d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + ", " + t;
  };
  function mountPanel(cp, { attr }) {
    let p = panels.get(cp);
    if (p && p.top.isConnected) return p;
    const bar = cp.querySelector(".cx4-bar");
    const top = el("div", "sm-conn-top");
    const quote = el("div", "sm-conn-quote");
    quote.hidden = true;
    const steps = el("ol", "sm-steps");
    steps.setAttribute("aria-label", "Etapas da resposta");
    for (const s of STEPS) {
      const li = el("li");
      li.append(el("span", "sm-step-dot"), el("span", "sm-step-lb", s));
      steps.append(li);
    }
    top.append(quote, steps);
    bar ? bar.before(top) : cp.prepend(top);
    const foot = el("section", "sm-conn-foot");
    foot.dataset[attr] = "true";
    const status = el("div", "sm-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const tools = el("div", "sm-tools");
    const hist = el("button", "sm-tool");
    hist.type = "button";
    const refresh = el("button", "sm-tool");
    refresh.type = "button";
    const counter = el("span", "sm-counter");
    counter.setAttribute("aria-live", "polite");
    tools.append(hist, refresh, counter);
    foot.append(status, tools);
    cp.append(foot);
    p = { top, quote, steps, foot, status, hist, refresh, counter, tools };
    panels.set(cp, p);
    return p;
  }
  /* model: { channel, attr, stage, tone, message, quote, primary:{label,icon,disabled,title,onClick}, history:{count,disabled,onClick},
              refresh:{busy,disabled,onClick}, counter:{used,max}|null, textarea:{disabled}, banner:{state,title,detail}, footer } */
  function update(cp, m) {
    const p = mountPanel(cp, { attr: m.attr });
    cp.dataset.smConn = m.channel;
    p.top.dataset.stage = m.stage;
    p.top.dataset.smConn = m.channel;
    p.foot.dataset.stage = m.stage;
    p.foot.setAttribute("aria-busy", String(m.stage === "loading" || m.stage === "sending" || !!m.busy));
    const st = stepStates[m.stage] || stepStates.compose;
    [...p.steps.children].forEach((li, i) => {
      li.dataset.state = st[i];
      const dot = li.firstChild;
      dot.textContent = st[i] === "done" ? "✓" : st[i] === "err" ? "!" : st[i] === "warn" ? "!" : String(i + 1);
      if (st[i] === "current" || st[i] === "busy" || st[i] === "warn" || st[i] === "err") li.setAttribute("aria-current", "step");
      else li.removeAttribute("aria-current");
    });
    /* resposta a… */
    if (m.quote) {
      if (p.quote.dataset.t !== m.quote) {
        p.quote.dataset.t = m.quote;
        p.quote.replaceChildren(icon("quote", 14), el("span", "sm-conn-qt", "Respondendo a"), el("span", "sm-conn-qb", m.quote));
      }
      p.quote.hidden = false;
    } else p.quote.hidden = true;
    /* status */
    p.status.dataset.tone = m.tone || "info";
    const key = (m.tone || "") + "|" + (m.message || "") + "|" + m.stage;
    if (p.status.dataset.k !== key) {
      p.status.dataset.k = key;
      const lead = m.tone === "busy" || m.stage === "loading" ? spinner() : el("span", "sm-dot");
      lead.setAttribute("aria-hidden", "true");
      p.status.replaceChildren(lead, el("span", "sm-status-tx", m.message || ""));
    }
    /* ferramentas */
    p.hist.innerHTML = svg("clock", 16) + "<span>Histórico</span>" + (m.history.count ? `<i class="sm-badge">${m.history.count}</i>` : "");
    p.hist.disabled = !!m.history.disabled;
    p.hist.onclick = m.history.onClick;
    p.hist.setAttribute("aria-label", "Abrir histórico de respostas" + (m.history.count ? " (" + m.history.count + ")" : ""));
    p.refresh.innerHTML = svg("refresh", 16) + "<span>" + (m.refresh.busy ? "Atualizando…" : "Atualizar") + "</span>";
    p.refresh.classList.toggle("is-busy", !!m.refresh.busy);
    p.refresh.disabled = !!m.refresh.disabled;
    p.refresh.onclick = m.refresh.onClick;
    p.refresh.setAttribute("aria-label", "Atualizar respostas e situação do envio");
    /* contador de limite (só perto do limite) */
    const c = m.counter;
    if (c && c.max && c.used / c.max >= 0.8) {
      const left = c.max - c.used;
      p.counter.textContent = left >= 0 ? "Restam " + left : "Excedeu em " + -left;
      p.counter.dataset.tone = left < 0 ? "err" : left < c.max * 0.05 ? "warn" : "info";
      p.counter.title = "Limite de " + c.max + " bytes (acentos e emojis ocupam mais espaço).";
      p.counter.hidden = false;
    } else p.counter.hidden = true;
    /* botão principal, dentro da barra do campo */
    const btn = cp.querySelector(".cx4-send");
    if (btn && m.primary) {
      btn.removeAttribute("data-a");
      btn.type = "button";
      btn.dataset.smPrimary = "true";
      btn.dataset.stage = m.stage;
      const sig = m.primary.label + "|" + m.primary.icon;
      if (btn.dataset.sig !== sig) {
        btn.dataset.sig = sig;
        btn.innerHTML = svg(m.primary.icon, 18) + `<span class="cx4-sl"></span><kbd class="cx4-k" aria-hidden="true">Ctrl ↵</kbd>`;
        btn.querySelector(".cx4-sl").textContent = m.primary.label;
      }
      btn.setAttribute("aria-label", m.primary.label);
      btn.title = m.primary.title || m.primary.label + " (Ctrl+Enter)";
      btn.disabled = !!m.primary.disabled;
      btn.onclick = (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        if (!btn.disabled) m.primary.onClick();
      };
    }
    /* faixa do cabeçalho e rodapé (só texto; sem alterar o resto da tela) */
    if (m.banner) {
      const wn = document.querySelector(".ct .hd .wn");
      if (wn) {
        const k = m.banner.state + m.banner.title + m.banner.detail;
        if (wn.dataset.k !== k) {
          wn.dataset.k = k;
          wn.dataset.state = m.banner.state;
          const dot = el("span", "wn-d");
          dot.setAttribute("aria-hidden", "true");
          wn.replaceChildren(dot, el("b", "", m.banner.title), document.createTextNode(" · "), el("span", "m", m.banner.detail));
        }
      }
    }
    if (m.footer) {
      const f = cp.parentNode?.querySelector("#cx4-ft");
      if (f) {
        const last = [...f.childNodes].reverse().find((n) => n.nodeType === 3);
        if (last) {
          if (last.textContent.trim() !== m.footer) last.textContent = " " + m.footer;
        } else f.append(document.createTextNode(" " + m.footer));
      }
    }
    return p;
  }

  window.SocialMEIAtendimentoUI = Object.freeze({ confirm, review, history, update, closeAll, svg, stamp, shell: base, header: head, spinner });
})();
