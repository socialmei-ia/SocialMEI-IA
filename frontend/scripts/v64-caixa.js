/* SocialMEI-IA · v6.4 · Comportamento da Caixa Unificada (complementa a Caixa; não cria outro sistema).
   - colunas redimensionáveis por arraste/teclado, com mínimos e preferência salva neste navegador
   - rolagem: abre na última mensagem, preserva a posição de leitura e mostra "N novas mensagens"
   - compositor: cresce ao digitar, Ctrl/⌘+Enter salva, rascunho por USUÁRIO + NEGÓCIO + CONVERSA
   - o rascunho só é apagado depois que a resposta salva aparece na conversa (nunca antes de confirmar)
   - mensagens muito longas recolhem com "Ver mais"; aviso real de falta de internet
   Nunca envia nada: a Caixa local só salva respostas neste navegador. No modo remoto, o compositor é
   controlado pelos scripts de integração (rascunho no servidor) e este arquivo não guarda o texto. */
(function () {
  "use strict";
  var app = document.getElementById("app");
  if (!app) return;

  var CK = "smei-v63-cols",
    DEF = { cl: 296, cx: 320 };
  var MIN_CL = 240,
    MAX_CL = 480,
    MIN_CX = 280,
    MAX_CX = 460,
    MIN_CT = 440;
  var DK = "smei-v64-draft:",
    LEGACY = "smei-v63-drafts:",
    TTL = 30 * 864e5,
    LONG = 640;
  var reduce = matchMedia("(prefers-reduced-motion: reduce)");

  function ls(k, v) {
    try {
      if (v === undefined) return localStorage.getItem(k);
      if (v === null) localStorage.removeItem(k);
      else localStorage.setItem(k, v);
      return true;
    } catch (e) {
      return v === undefined ? null : false;
    }
  }
  function rd(k, d) {
    try {
      var o = JSON.parse(ls(k) || "");
      return o && typeof o === "object" ? o : d;
    } catch (e) {
      return d;
    }
  }
  function clamp(v, a, b) {
    return Math.max(a, Math.min(b, v));
  }
  function curId() {
    var m = location.hash.match(/^#\/caixa\/([^/?#]+)/);
    return m ? decodeURIComponent(m[1]) : null;
  }
  function desk() {
    return innerWidth > 900;
  }

  /* ---------- identidade (usuário + negócio) ---------- */
  function who() {
    try {
      var a = window.SocialMEIAuth,
        cur = a && a.current;
      if (a && a.remote) {
        if (
          !cur ||
          !cur.usuario ||
          !cur.negocio ||
          cur.usuario.id == null ||
          cur.negocio.id == null
        )
          return null;
        return { u: String(cur.usuario.id), b: String(cur.negocio.id) };
      }
      var n = cur && cur.negocio;
      return {
        u: cur && cur.usuario && cur.usuario.id != null ? String(cur.usuario.id) : "local",
        b: n && (n.id != null || n.nome) ? String(n.id != null ? n.id : n.nome) : "local",
      };
    } catch (e) {
      return null;
    }
  }
  function dkey(id) {
    var w = who();
    return w && id
      ? DK + encodeURIComponent(w.u) + ":" + encodeURIComponent(w.b) + ":" + encodeURIComponent(id)
      : null;
  }
  var scope = who();
  if (scope) CK += ":" + encodeURIComponent(scope.u) + ":" + encodeURIComponent(scope.b);
  function readDraft(id) {
    if (window.SocialMEIAuth && window.SocialMEIAuth.remote) return "";
    var k = dkey(id),
      w = who();
    if (!k) return "";
    try {
      var o = JSON.parse(ls(k) || "null");
      if (
        o &&
        typeof o.t === "string" &&
        o.u === w.u &&
        o.b === w.b &&
        o.c === id &&
        Date.now() - (o.ts || 0) < TTL
      )
        return o.t;
    } catch (e) {
      /* ignora */
    }
    return "";
  }
  /* devolve true só se o navegador realmente gravou (ou removeu) */
  function writeDraft(id, v) {
    var k = dkey(id),
      w = who();
    if (!k) return false;
    if (!v) return ls(k, null) !== false;
    return ls(k, JSON.stringify({ t: v, u: w.u, b: w.b, c: id, ts: Date.now() })) === true;
  }
  /* limpeza: rascunhos vencidos e o formato antigo (v6.3, sem usuário). No modo local o antigo é migrado; no remoto é descartado. */
  (function purge() {
    try {
      var w = who(),
        remote = !!(window.SocialMEIAuth && window.SocialMEIAuth.remote),
        del = [];
      for (var n = 0; n < localStorage.length; n++) {
        var k = localStorage.key(n);
        if (!k) continue;
        if (k.indexOf(LEGACY) === 0) {
          if (!remote && w) {
            var old = rd(k, {});
            Object.keys(old).forEach(function (cid) {
              if (typeof old[cid] === "string" && old[cid] && !readDraft(cid))
                writeDraft(cid, old[cid]);
            });
          }
          del.push(k);
        } else if (k.indexOf(DK) === 0) {
          var o = rd(k, null);
          if (!o || Date.now() - (o.ts || 0) >= TTL) del.push(k);
        }
      }
      del.forEach(function (k) {
        ls(k, null);
      });
    } catch (e) {
      /* ignora */
    }
  })();
  var sig = (function () {
    var w = who();
    return w ? w.u + ":" + w.b : "";
  })();

  /* ---------- colunas ---------- */
  var cols = rd(CK, DEF);
  cols.cl = +cols.cl || DEF.cl;
  cols.cx = +cols.cx || DEF.cx;
  function fit(cv) {
    var W = cv.clientWidth,
      hasCx = !cv.classList.contains("noctx");
    var cl = clamp(cols.cl, MIN_CL, MAX_CL),
      cx = clamp(cols.cx, MIN_CX, MAX_CX);
    var room = W - MIN_CT - (hasCx ? cx : 0);
    cl = clamp(cl, Math.min(MIN_CL, Math.max(160, room)), Math.max(MIN_CL, Math.min(MAX_CL, room)));
    if (hasCx) cx = clamp(cx, MIN_CX, Math.max(MIN_CX, Math.min(MAX_CX, W - MIN_CT - cl)));
    cv.style.setProperty("--v63-cl", cl + "px");
    cv.style.setProperty("--v63-cx", cx + "px");
    return { cl: cl, cx: cx };
  }
  function mkSep(kind, label) {
    var d = document.createElement("div");
    d.className = "v63-rs v63-rs-" + kind;
    d.setAttribute("role", "separator");
    d.setAttribute("aria-orientation", "vertical");
    d.tabIndex = 0;
    d.dataset.rs = kind;
    d.setAttribute("aria-label", label);
    d.title = "Arraste para ajustar. Clique duas vezes para restaurar.";
    return d;
  }
  function seps(cv) {
    // The integrated remote inbox already owns sizing and scoped preferences.
    if (window.SocialMEIInboxLayout) {
      cv.querySelectorAll(".v63-rs").forEach(function (node) {
        node.remove();
      });
      return;
    }
    var want = desk(),
      hasCx = !cv.classList.contains("noctx");
    [
      ["cl", "Ajustar largura da lista de conversas", true],
      ["cx", "Ajustar largura do contexto do cliente", hasCx],
    ].forEach(function (s) {
      var ex = cv.querySelector(":scope > .v63-rs-" + s[0]);
      if (want && s[2]) {
        if (!ex) cv.appendChild(mkSep(s[0], s[1]));
      } else if (ex) ex.remove();
    });
    if (!want) return;
    var v = fit(cv);
    [
      ["cl", MIN_CL, MAX_CL, v.cl],
      ["cx", MIN_CX, MAX_CX, v.cx],
    ].forEach(function (s) {
      var e = cv.querySelector(":scope > .v63-rs-" + s[0]);
      if (!e) return;
      e.setAttribute("aria-valuemin", s[1]);
      e.setAttribute("aria-valuemax", s[2]);
      e.setAttribute("aria-valuenow", Math.round(s[3]));
    });
  }
  function save() {
    ls(CK, JSON.stringify(cols));
  }
  var drag = null;
  app.addEventListener("pointerdown", function (e) {
    var h = e.target.closest && e.target.closest(".v63-rs");
    if (!h) return;
    drag = { k: h.dataset.rs, cv: h.closest(".cv"), h: h };
    h.setPointerCapture(e.pointerId);
    h.classList.add("on");
    document.body.classList.add("v63-dragging");
    e.preventDefault();
  });
  app.addEventListener("pointermove", function (e) {
    if (!drag) return;
    var r = drag.cv.getBoundingClientRect(),
      z = parseFloat(document.body.style.zoom) || 1;
    if (drag.k === "cl") cols.cl = (e.clientX - r.left) / z;
    else cols.cx = (r.right - e.clientX) / z;
    var v = fit(drag.cv);
    cols.cl = v.cl;
    cols.cx = v.cx;
    drag.h.setAttribute("aria-valuenow", Math.round(drag.k === "cl" ? v.cl : v.cx));
  });
  function end() {
    if (!drag) return;
    drag.h.classList.remove("on");
    document.body.classList.remove("v63-dragging");
    save();
    drag = null;
  }
  app.addEventListener("pointerup", end);
  app.addEventListener("pointercancel", end);
  app.addEventListener("dblclick", function (e) {
    var h = e.target.closest && e.target.closest(".v63-rs");
    if (!h) return;
    cols[h.dataset.rs] = DEF[h.dataset.rs];
    save();
    seps(h.closest(".cv"));
  });
  app.addEventListener("keydown", function (e) {
    var h = e.target.closest && e.target.closest(".v63-rs");
    if (!h) return;
    var step = e.shiftKey ? 48 : 16,
      d = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0;
    if (!d) {
      if (e.key === "Home") {
        cols[h.dataset.rs] = DEF[h.dataset.rs];
        save();
        seps(h.closest(".cv"));
        e.preventDefault();
      }
      return;
    }
    cols[h.dataset.rs] += (h.dataset.rs === "cl" ? d : -d) * step;
    var cv = h.closest(".cv"),
      v = fit(cv);
    cols.cl = v.cl;
    cols.cx = v.cx;
    save();
    seps(cv);
    e.preventDefault();
  });

  /* ---------- rolagem, "Última mensagem" e "novas mensagens" ---------- */
  var track = { id: null, el: null, top: 0, gap: 0, n: 0, pend: 0 };
  function msgCount(ms) {
    return ms.querySelectorAll(".cx4-m").length;
  }
  function gap(ms) {
    return ms.scrollHeight - ms.scrollTop - ms.clientHeight;
  }
  function toBottom(ms) {
    ms.scrollTop = ms.scrollHeight;
  }
  function jumpBtn(ct, ms) {
    var b = ct.querySelector(".v63-last");
    if (!b) {
      b = document.createElement("button");
      b.type = "button";
      b.className = "v63-last";
      b.hidden = true;
      ct.appendChild(b);
    }
    if (!b._v64) {
      b._v64 = 1;
      b.addEventListener("click", function () {
        track.pend = 0;
        ms.scrollTo({ top: ms.scrollHeight, behavior: reduce.matches ? "auto" : "smooth" });
      });
    }
    b._ms = ms;
    return b;
  }
  function paintJump(b) {
    var ms = b._ms;
    if (!ms) return;
    var far = gap(ms) >= 140;
    if (!far) track.pend = 0;
    b.hidden = !far;
    var lbl =
      track.pend > 0
        ? track.pend + (track.pend > 1 ? " novas mensagens" : " nova mensagem")
        : "Última mensagem";
    b.innerHTML = '<span aria-hidden="true">↓</span> ' + lbl;
    b.setAttribute(
      "aria-label",
      track.pend > 0 ? "Ir para as " + lbl : "Ir para a última mensagem",
    );
    b.classList.toggle("new", track.pend > 0);
    var ct = ms.parentNode;
    b.style.setProperty(
      "bottom",
      Math.max(12, ct.clientHeight - (ms.offsetTop + ms.offsetHeight) + 12) + "px",
    );
  }
  function scrollState(ct, ms) {
    var id = curId(),
      b = jumpBtn(ct, ms),
      n = msgCount(ms);
    if (track.el !== ms) {
      var again = track.id === id && track.el; /* a tela foi redesenhada para a mesma conversa */
      var wasNear = again && track.gap < 140;
      if (!again) {
        toBottom(ms);
        track.pend = 0;
      } /* conversa nova: abre na última mensagem */
      else {
        if (n > track.n && !wasNear) track.pend += n - track.n;
        if (wasNear) toBottom(ms);
        else ms.scrollTop = track.top;
      }
      track.id = id;
      track.el = ms;
      track.n = n;
      ms.addEventListener(
        "scroll",
        function () {
          track.top = ms.scrollTop;
          track.gap = gap(ms);
          paintJump(b);
        },
        { passive: true },
      );
      track.top = ms.scrollTop;
      track.gap = gap(ms);
    } else if (n !== track.n) {
      /* mensagem nova na mesma tela */
      if (n > track.n && gap(ms) >= 140) track.pend += n - track.n;
      else if (n > track.n) toBottom(ms);
      track.n = n;
    }
    paintJump(b);
  }

  /* ---------- mensagens longas ---------- */
  function longMsgs(ms) {
    var searching = !!ms.querySelector("mark.k10-mk");
    ms.querySelectorAll(".cx4-m .bb:not(.k10-rich)").forEach(function (bb) {
      var m = bb.closest(".cx4-m"),
        btn = m.querySelector(":scope > .cx4-more");
      var big = (bb.textContent || "").length > LONG;
      if (!big) {
        if (btn) btn.remove();
        bb.classList.remove("cx4-clamp");
        return;
      }
      if (!btn) {
        btn = document.createElement("button");
        btn.type = "button";
        btn.className = "cx4-more lk";
        btn.textContent = "Ver mais";
        btn.setAttribute("aria-expanded", "false");
        btn.addEventListener("click", function () {
          var open = bb.classList.toggle("cx4-clamp") === false;
          btn.textContent = open ? "Ver menos" : "Ver mais";
          btn.setAttribute("aria-expanded", String(open));
          bb._open = open;
        });
        var mt = m.querySelector(":scope > .cx4-mt");
        m.insertBefore(btn, mt);
        m.classList.toggle("cx4-or", !!m.querySelector(".mg.o"));
        bb.classList.add("cx4-clamp");
      }
      if (searching) {
        bb.classList.remove("cx4-clamp");
        btn.hidden = true;
      } else {
        btn.hidden = false;
        if (bb._open) bb.classList.remove("cx4-clamp");
      }
    });
  }

  /* ---------- compositor e rascunhos ---------- */
  var restored = {},
    pend = null,
    flash = 0,
    wrote = {};
  function managed(cp) {
    return !!cp.querySelector(
      "[data-wa-replies],[data-ig-reply],[data-ig-reply-unavailable],[data-wa-prepare],[data-ig-prepare]",
    );
  }
  function grow(t) {
    t.style.setProperty("height", "auto", "important");
    t.style.setProperty("height", Math.min(t.scrollHeight + 2, 168) + "px", "important");
  }
  function note(cp, msg, kind) {
    var s = cp.querySelector(".cx4-dr");
    if (!s) return;
    s.textContent = msg || "";
    s.dataset.k = kind || "";
    s.setAttribute("role", kind === "err" ? "alert" : "status");
  }
  function sendBtn(cp) {
    var b = cp.querySelector(".cx4-send");
    return b && /^salvar/.test(b.dataset.a || "") ? b : null;
  }
  function paintDraft(cp, t, id, ok) {
    var b = sendBtn(cp);
    if (b) b.disabled = !t.value.trim();
    if (flash && Date.now() < flash) return;
    if (ok === undefined) ok = wrote[dkey(id)] !== false;
    if (managed(cp) || !dkey(id)) {
      note(cp, "");
      return;
    }
    if (!t.value.trim()) note(cp, "");
    else if (ok === false) note(cp, "Não foi possível guardar o rascunho neste navegador", "err");
    else note(cp, "Rascunho salvo neste navegador", "ok");
  }
  function composer() {
    var t = document.getElementById("ta"),
      id = curId();
    if (!t || !id) return;
    var cp = t.closest(".cp");
    if (!cp) return;
    if (window.SocialMEIAuth && window.SocialMEIAuth.remote) {
      grow(t);
      if (!t._v64Remote) {
        t._v64Remote = true;
        t.addEventListener("input", function () {
          grow(t);
        });
      }
      return;
    }
    var k = dkey(id),
      mg = managed(cp);
    if (k && !mg && !restored[k]) {
      restored[k] = 1;
      var st = readDraft(id);
      if (st && t.value !== st) {
        t.value = st;
        t.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
    if (!t._v64) {
      t._v64 = 1;
      t.addEventListener("input", function () {
        grow(t);
        var i2 = curId(),
          ok = true,
          cp2 = t.closest(".cp");
        if (!i2 || !cp2) return;
        if (!managed(cp2) && dkey(i2)) {
          ok = writeDraft(i2, t.value);
          wrote[dkey(i2)] = ok;
        }
        paintDraft(cp2, t, i2, ok);
      });
      t.addEventListener("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          var b = sendBtn(t.closest(".cp"));
          if (b && !b.disabled) {
            e.preventDefault();
            b.click();
          }
        }
      });
    }
    grow(t);
    paintDraft(cp, t, id);
  }
  /* Só apaga o rascunho guardado depois de confirmar que a resposta salva apareceu na conversa. */
  document.addEventListener(
    "click",
    function (e) {
      var b = e.target.closest && e.target.closest('[data-a^="salvar"]');
      if (!b) return;
      var t = document.getElementById("ta"),
        id = curId(),
        txt = t && t.value.trim();
      if (!t || !id || !txt || !dkey(id)) return;
      pend = { id: id, key: dkey(id), txt: txt };
      setTimeout(confirmSaved, 80);
      setTimeout(confirmSaved, 400);
    },
    true,
  ); /* captura: lê o texto ANTES de a Caixa redesenhar a tela */
  function confirmSaved() {
    var p = pend;
    if (!p) return;
    var t = document.getElementById("ta");
    if (curId() !== p.id || dkey(p.id) !== p.key) {
      pend = null;
      return;
    }
    var bb = document.querySelectorAll("#v .ms .cx4-m .mg.o .bb"),
      last = bb[bb.length - 1];
    if (t && t.value === "" && last && last.textContent.trim() === p.txt) {
      pend = null;
      writeDraft(p.id, "");
      wrote[p.key] = true;
      var cp = t.closest(".cp");
      if (cp) {
        flash = Date.now() + 3200;
        note(cp, "Resposta salva neste navegador", "ok");
        setTimeout(function () {
          flash = 0;
          var c2 = document.querySelector("#v .cp"),
            t2 = document.getElementById("ta");
          if (c2 && t2) paintDraft(c2, t2, curId());
        }, 3300);
      }
    }
  }

  /* ---------- conexão e atalhos ---------- */
  function banner(ct) {
    var b = ct.querySelector(".v63-bn"),
      off = navigator.onLine === false;
    if (off && !b) {
      b = document.createElement("div");
      b.className = "v63-bn";
      b.setAttribute("role", "status");
      b.textContent =
        window.SocialMEIAuth && window.SocialMEIAuth.remote
          ? "Sem conexão com a internet. Aguarde a conexão para confirmar o salvamento no servidor."
          : "Sem conexão com a internet. Seus rascunhos continuam salvos neste navegador.";
      var hd = ct.querySelector(".hd");
      hd ? hd.after(b) : ct.prepend(b);
    } else if (!off && b) b.remove();
  }
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target;
    if (t && (/^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable)) return;
    var s = document.querySelector("#v .cx4-sr input");
    if (s) {
      e.preventDefault();
      s.focus();
    }
  });

  /* ---------- menu "Mais": setas, Home/End e Esc devolvendo o foco ---------- */
  document.addEventListener("keydown", function (e) {
    var btn = e.target.closest && e.target.closest(".cx4-mb"),
      item = e.target.closest && e.target.closest(".cx4-mi");
    if (btn && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      if (btn.getAttribute("aria-expanded") !== "true") btn.click();
      requestAnimationFrame(function () {
        var it = document.querySelectorAll(".cx4-pop .cx4-mi");
        if (it.length) (e.key === "ArrowUp" ? it[it.length - 1] : it[0]).focus();
      });
      return;
    }
    if (!item) return;
    var all = Array.prototype.slice.call(item.parentNode.querySelectorAll(".cx4-mi")),
      i = all.indexOf(item),
      n = all.length;
    if (e.key === "ArrowDown") {
      all[(i + 1) % n].focus();
      e.preventDefault();
    } else if (e.key === "ArrowUp") {
      all[(i - 1 + n) % n].focus();
      e.preventDefault();
    } else if (e.key === "Home") {
      all[0].focus();
      e.preventDefault();
    } else if (e.key === "End") {
      all[n - 1].focus();
      e.preventDefault();
    } else if (e.key === "Escape") {
      var b = document.querySelector(".cx4-mb");
      setTimeout(function () {
        if (b) b.focus();
      }, 0);
    }
  });

  /* ---------- menu de anexos (+): fecha ao clicar fora, com Esc ou ao escolher ---------- */
  document.addEventListener("click", function (e) {
    var open = document.querySelectorAll(".cx4-att[open]");
    for (var n = 0; n < open.length; n++)
      if (
        !open[n].contains(e.target) ||
        (e.target.closest && e.target.closest(".cx4-attm .btn") && !e.target.closest("label"))
      )
        open[n].removeAttribute("open");
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    var d = document.querySelector(".cx4-att[open]");
    if (d) {
      d.removeAttribute("open");
      var sm = d.querySelector("summary");
      if (sm) sm.focus();
    }
  });

  /* ---------- Alt+↑/↓: conversa anterior/seguinte (funciona até com o cursor no campo de resposta) ---------- */
  document.addEventListener("keydown", function (e) {
    if (!e.altKey || e.ctrlKey || e.metaKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown"))
      return;
    var rows = Array.prototype.slice
      .call(document.querySelectorAll("#v .cx4-rows .ci"))
      .filter(function (r) {
        return r.style.display !== "none";
      });
    if (!rows.length) return;
    var i = rows.findIndex(function (r) {
      return r.getAttribute("aria-current") === "true";
    });
    var j =
      e.key === "ArrowDown" ? Math.min(rows.length - 1, i + 1) : Math.max(0, i < 0 ? 0 : i - 1);
    if (j === i) return;
    e.preventDefault();
    location.hash = rows[j].getAttribute("href");
  });
  /* sombra no cabeçalho da lista quando há rolagem */
  document.addEventListener(
    "scroll",
    function (e) {
      var t = e.target;
      if (!t || !t.classList || !t.classList.contains("cl")) return;
      var h = t.querySelector(".cx4-ph");
      if (h) h.classList.toggle("sh", t.scrollTop > 4);
    },
    true,
  );

  /* ---------- "Rascunho:" na lista de conversas (como nos apps de mensagem) ---------- */
  function paintDrafts() {
    var rows = document.querySelectorAll("#v .cx4-rows .ci");
    for (var n = 0; n < rows.length; n++) {
      var r = rows[n],
        pv = r.querySelector(".pv");
      if (!pv) continue;
      var m = (r.getAttribute("href") || "").match(/#\/caixa\/([^/?#]+)/);
      if (!m) continue;
      var id = decodeURIComponent(m[1]),
        live =
          r.getAttribute("aria-current") === "true"
            ? (document.getElementById("ta") || {}).value
            : null;
      var d = (live != null ? live : readDraft(id)) || "";
      d = d.trim().replace(/\s+/g, " ");
      if (d) {
        if (pv.dataset.orig === undefined) pv.dataset.orig = pv.innerHTML;
        var want = d.slice(0, 80);
        if (pv.dataset.d !== want) {
          pv.dataset.d = want;
          pv.textContent = "";
          var t = document.createElement("b");
          t.className = "cx4-dtag";
          t.textContent = "Rascunho:";
          pv.append(t, document.createTextNode(" " + want));
        }
        r.classList.add("has-draft");
      } else if (pv.dataset.orig !== undefined) {
        pv.innerHTML = pv.dataset.orig;
        delete pv.dataset.orig;
        delete pv.dataset.d;
        r.classList.remove("has-draft");
      }
    }
  }
  document.addEventListener("input", function (e) {
    if (e.target && e.target.id === "ta") setTimeout(paintDrafts, 0);
  });

  /* ---------- teclado virtual no celular: compacta o cabeçalho para sobrar espaço às mensagens ---------- */
  (function () {
    var vv = window.visualViewport;
    if (!vv) return;
    var base = vv.height;
    function chk() {
      var open =
        innerWidth <= 900 &&
        base - vv.height > 140 &&
        document.activeElement &&
        document.activeElement.id === "ta";
      document.documentElement.classList.toggle("cx4-kb", open);
      if (open) {
        var ms = document.querySelector("#v .ct .ms");
        if (ms) ms.scrollTop = ms.scrollHeight;
      }
    }
    vv.addEventListener("resize", function () {
      if (vv.height > base) base = vv.height;
      chk();
    });
    document.addEventListener("focusout", function () {
      setTimeout(chk, 120);
    });
  })();

  /* ---------- ciclo ---------- */
  var busy = false,
    raf = 0,
    lastMode = null;
  function modeNow() {
    return desk() ? "d" : "m";
  }
  function enhance() {
    raf = 0;
    if (busy) return;
    busy = true;
    try {
      var s2 = (function () {
        var w = who();
        return w ? w.u + ":" + w.b : "";
      })();
      if (s2 !== sig) {
        pend = null;
        return;
      } // Auth owns account/workspace navigation.
      var cv = document.querySelector("#v .cv");
      if (cv) {
        seps(cv);
        paintDrafts();
        var ct = cv.querySelector(".ct"),
          ms = cv.querySelector(".ct .ms");
        if (ct && ms) {
          banner(ct);
          scrollState(ct, ms);
          longMsgs(ms);
          composer();
        } else {
          track.el = null;
          track.id = null;
        }
      } else {
        track.el = null;
        track.id = null;
      }
      /* cruzou o limite de 900 px na lista da Caixa: troca entre página e painel */
      var idle = document.querySelector("#v .cx4-idle"),
        pgl = document.querySelector("#v .cx4-pgl");
      if ((idle && !desk()) || (pgl && desk())) {
        if (typeof window.render === "function" && lastMode !== modeNow()) {
          lastMode = modeNow();
          window.render();
        }
      } else lastMode = modeNow();
    } finally {
      busy = false;
      obs.takeRecords();
    }
  }
  var obs = new MutationObserver(function () {
    if (!busy && !raf) raf = requestAnimationFrame(enhance);
  });
  obs.observe(app, { childList: true, subtree: true });
  var sched = function () {
    if (!raf) raf = requestAnimationFrame(enhance);
  };
  addEventListener("resize", sched);
  addEventListener("online", sched);
  addEventListener("offline", sched);
  enhance();
})();
