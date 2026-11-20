/* SocialMEI-IA · Seções v3: história por etapas (celular que muda de tela), demonstração por ramo,
   lista "Para hoje" que se marca, brilho nos cartões do bento e trilho de "Como funciona".
   Tudo ilustrativo e local: sem rede, sem armazenamento, nada é enviado. Depende de window.SMEI_LANDING (landing-content.js).
   Substitui landing-v2.js e sections-anim.js (versões anteriores em ../secoes-originais/scripts/). Só transform/opacity. */
(function () {
  "use strict";
  var root = document.documentElement;
  var D = window.SMEI_LANDING || { historia: [], ramos: [] };
  var $ = function (s, r) {
    return (r || document).querySelector(s);
  };
  var $$ = function (s, r) {
    return Array.prototype.slice.call((r || document).querySelectorAll(s));
  };
  function el(t, c, x) {
    var e = document.createElement(t);
    if (c) e.className = c;
    if (x != null) e.textContent = x;
    return e;
  }
  var reduceMQ = matchMedia("(prefers-reduced-motion: reduce)");
  var calm = function () {
    return root.classList.contains("calm") || reduceMQ.matches;
  };
  root.classList.add("sx-js");
  /* v6.2: dispara uma vez quando o elemento entra na tela OU já foi ultrapassado (rolagem rápida, End, arrastar a barra) */
  function reach(el, frac, cb) {
    var done = false;
    function chk() {
      if (done) return;
      var r = el.getBoundingClientRect();
      if (r.top < innerHeight * (1 - frac) || r.bottom < 0) {
        done = true;
        removeEventListener("scroll", chk);
        cb();
      }
    }
    addEventListener("scroll", chk, { passive: true });
    chk();
  }

  /* ======================================================================
     1. HISTÓRIA: 5 etapas, um celular que muda de tela, mesma cliente atravessando as áreas
     ====================================================================== */
  var hist = document.getElementById("hist");
  if (hist && D.historia.length) {
    var tabsBox = $(".sx-tabs", hist),
      phone = document.getElementById("h-panel"),
      stage = document.getElementById("hStage");
    var screens = $$(".sx-sc", phone),
      dots = $$(".sx-dots li", phone),
      areaEl = document.getElementById("hArea"),
      threadEl = document.getElementById("hThread");
    var live = document.getElementById("h-live"),
      nextBtn = document.getElementById("hNext");
    var tabs = [],
      chaps = [],
      slots = [],
      cur = -1,
      lockUntil = 0;
    var desk = matchMedia("(min-width:1001px)");
    var n2 = function (i) {
      return String(i + 1);
    };

    D.historia.forEach(function (s, i) {
      var chap = el("div", "sx-chap");
      chap.setAttribute("role", "none");
      var b = el("button", "sx-tab");
      b.type = "button";
      b.id = "ht-" + s.id;
      b.setAttribute("role", "tab");
      b.setAttribute("aria-controls", "h-panel");
      b.appendChild(el("span", "sx-n", n2(i)));
      var tb = el("span", "sx-tb");
      tb.appendChild(el("span", "sx-lb", s.rotulo));
      tb.appendChild(el("span", "sx-tt", s.titulo));
      tb.appendChild(el("span", "sx-nt", s.nota));
      b.appendChild(tb);
      b.addEventListener("click", function () {
        go(i, { from: "click" });
      });
      b.addEventListener("keydown", function (e) {
        var k = e.key,
          n =
            k === "ArrowDown" || k === "ArrowRight"
              ? i + 1
              : k === "ArrowUp" || k === "ArrowLeft"
                ? i - 1
                : k === "Home"
                  ? 0
                  : k === "End"
                    ? tabs.length - 1
                    : null;
        if (n === null) return;
        e.preventDefault();
        go((n + tabs.length) % tabs.length, { from: "key", focus: true });
      });
      var slot = el("div", "sx-slot");
      slot.hidden = true;
      chap.appendChild(b);
      chap.appendChild(slot);
      tabs.push(b);
      chaps.push(chap);
      slots.push(slot);
      tabsBox.appendChild(chap);
    });

    function railPos() {
      /* trilho: do centro do 1º nó ao centro do último; preenchimento até o nó ativo */
      var ns = tabs.map(function (b) {
        return b.firstChild;
      });
      var box = tabsBox.getBoundingClientRect(),
        y0 = ns[0].getBoundingClientRect(),
        y1 = ns[ns.length - 1].getBoundingClientRect(),
        ya = ns[Math.max(cur, 0)].getBoundingClientRect();
      var c0 = y0.top - box.top + y0.height / 2,
        c1 = y1.top - box.top + y1.height / 2,
        ca = ya.top - box.top + ya.height / 2;
      tabsBox.style.setProperty("--r0", c0.toFixed(1) + "px");
      tabsBox.style.setProperty("--rh", Math.max(c1 - c0, 0).toFixed(1) + "px");
      tabsBox.style.setProperty(
        "--pr",
        c1 > c0 ? Math.min(Math.max((ca - c0) / (c1 - c0), 0), 1).toFixed(3) : 0,
      );
    }
    function place() {
      /* desktop: celular no palco fixo; mobile: celular dentro do passo ativo */
      var d = desk.matches,
        i = Math.max(cur, 0);
      slots.forEach(function (s, n) {
        s.hidden = d || n !== i;
      });
      if (d) {
        if (phone.parentNode !== stage) stage.appendChild(phone);
      } else if (phone.parentNode !== slots[i]) slots[i].appendChild(phone);
      nextBtn.hidden = d;
    }
    function go(i, o) {
      o = o || {};
      if (i === cur) {
        if (o.focus) tabs[i].focus();
        return;
      }
      var s = D.historia[i],
        anchor = !desk.matches && cur >= 0 ? tabs[i] : null,
        top0 = anchor ? anchor.getBoundingClientRect().top : 0;
      cur = i;
      if (o.from !== "scroll") lockUntil = performance.now() + 900;
      tabs.forEach(function (b, n) {
        b.setAttribute("aria-selected", n === i);
        b.tabIndex = n === i ? 0 : -1;
        b.classList.toggle("done", n < i);
      });
      screens.forEach(function (sc) {
        sc.classList.toggle("on", sc.getAttribute("data-sc") === s.id);
      });
      dots.forEach(function (d, n) {
        d.classList.toggle("on", n <= i);
      });
      phone.setAttribute("aria-labelledby", "ht-" + s.id);
      areaEl.textContent = s.area;
      threadEl.textContent = i === 0 ? "WhatsApp · Kit de presente" : "Kit de presente · R$ 180,00";
      live.textContent =
        "Etapa " +
        (i + 1) +
        " de " +
        D.historia.length +
        ", " +
        s.rotulo +
        ": " +
        s.titulo +
        ". " +
        s.linhas
          .map(function (l) {
            return l[0] + ": " + l[1];
          })
          .join(". ") +
        ". " +
        s.nota;
      nextBtn.firstChild.nodeValue =
        i < D.historia.length - 1
          ? "Próxima etapa: " + D.historia[i + 1].rotulo + " "
          : "Voltar ao início da história ";
      place();
      railPos();
      if (anchor) {
        var dy = anchor.getBoundingClientRect().top - top0;
        if (Math.abs(dy) > 1) window.scrollBy({ top: dy, behavior: "auto" });
      }
      if (o.focus) tabs[i].focus();
      if (o.from === "click" && desk.matches && !calm()) {
        var r = chaps[i].getBoundingClientRect(),
          vh = innerHeight;
        if (r.top < vh * 0.3 || r.bottom > vh * 0.85)
          window.scrollBy({ top: r.top + r.height / 2 - vh * 0.5, behavior: "smooth" });
      }
    }
    nextBtn.addEventListener("click", function () {
      var n = (cur + 1) % tabs.length;
      go(n, { from: "next" });
      tabs[n].scrollIntoView({ block: "nearest", behavior: "auto" });
    });

    /* v6.2: a rolagem narra a história no desktop. O capítulo mais perto do centro da tela vira a etapa ativa; se a pessoa
       passa depressa e pula etapas, a história percorre as intermediárias em sequência (uma a cada ~260 ms), sem cortar. */
    var walkT = 0,
      wantI = -1,
      syncRaf = 0;
    function walk() {
      clearTimeout(walkT);
      if (wantI < 0 || cur === wantI) return;
      if (calm()) {
        go(wantI, { from: "scroll" });
        return;
      }
      go(cur + (wantI > cur ? 1 : -1), { from: "scroll" });
      walkT = setTimeout(walk, 260);
    }
    function sync() {
      syncRaf = 0;
      if (!desk.matches || performance.now() < lockUntil) return;
      var mid = innerHeight / 2,
        hr = hist.getBoundingClientRect(),
        t = cur;
      if (hr.bottom < mid) t = chaps.length - 1;
      else if (hr.top > mid) t = 0;
      else {
        var best = 1e9;
        chaps.forEach(function (c, n) {
          var r = c.getBoundingClientRect(),
            d = Math.abs(r.top + r.height / 2 - mid);
          if (d < best) {
            best = d;
            t = n;
          }
        });
      }
      if (t !== wantI) {
        wantI = t;
        walk();
      }
    }
    addEventListener(
      "scroll",
      function () {
        if (!syncRaf) syncRaf = requestAnimationFrame(sync);
      },
      { passive: true },
    );
    var rz = 0;
    addEventListener(
      "resize",
      function () {
        cancelAnimationFrame(rz);
        rz = requestAnimationFrame(function () {
          place();
          railPos();
        });
      },
      { passive: true },
    );
    desk.addEventListener
      ? desk.addEventListener("change", function () {
          place();
          railPos();
        })
      : desk.addListener(function () {
          place();
          railPos();
        });
    go(0);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(railPos);
  }

  /* ======================================================================
     2. PRODUTO: brilho azul que segue o ponteiro nos cartões do bento (só --cx/--cy, rAF)
     ====================================================================== */
  var bento = document.getElementById("bento");
  if (bento && matchMedia("(pointer:fine)").matches) {
    var raf = 0,
      last = null;
    bento.addEventListener(
      "pointermove",
      function (e) {
        var c = e.target.closest && e.target.closest(".sx-bc");
        if (!c || calm()) return;
        last = [c, e.clientX, e.clientY];
        if (raf) return;
        raf = requestAnimationFrame(function () {
          raf = 0;
          var r = last[0].getBoundingClientRect();
          last[0].style.setProperty("--cx", last[1] - r.left + "px");
          last[0].style.setProperty("--cy", last[2] - r.top + "px");
        });
      },
      { passive: true },
    );
  }

  /* ======================================================================
     3. PARA MEI: "Para hoje" se marca sozinho uma vez ao entrar na tela; depois a pessoa marca e desmarca
     ====================================================================== */
  var hoje = document.getElementById("hoje");
  if (hoje) {
    var cks = $$("input[type=checkbox]", hoje),
      played = false;
    var seq = function () {
      if (played) return;
      played = true;
      if (calm()) {
        cks[0].checked = true;
        cks[1].checked = true;
        return;
      }
      [0, 1].forEach(function (n) {
        setTimeout(
          function () {
            if (!cks[n].dataset.touched) cks[n].checked = true;
          },
          1100 + n * 1100,
        );
      });
    };
    cks.forEach(function (c) {
      c.addEventListener("change", function () {
        c.dataset.touched = "1";
      });
    });
    reach(hoje, 0.3, seq);
    var rep = document.getElementById("hojeRep");
    if (rep)
      rep.addEventListener("click", function () {
        cks.forEach(function (c) {
          c.checked = false;
          delete c.dataset.touched;
        });
        if (calm()) {
          cks[0].checked = true;
          cks[1].checked = true;
          return;
        }
        [0, 1].forEach(function (n) {
          setTimeout(
            function () {
              if (!cks[n].dataset.touched) cks[n].checked = true;
            },
            500 + n * 900,
          );
        });
      });
  }

  /* ======================================================================
     4. COMO FUNCIONA: o trilho se preenche e os passos aparecem em sequência
     ====================================================================== */
  var track = document.getElementById("comoTrack");
  if (track) {
    if (!("IntersectionObserver" in window) || calm()) track.classList.add("on");
    else
      reach(track, 0.2, function () {
        track.classList.add("on");
      });
  }

  /* ======================================================================
     5. DEMONSTRAÇÃO por ramo (mesma lógica de antes): trocar o ramo reescreve a conversa;
        "Ver sugestão de resposta" → "Registrar como oportunidade"; nada é enviado nem salvo
     ====================================================================== */
  var demo = document.getElementById("ramoDemo");
  if (demo && D.ramos.length) {
    var chips = $(".sx-chips", demo),
      chat = $(".sx-dbody", demo),
      nameEl = $(".sx-dname", demo),
      avEl = $(".sx-dav", demo),
      curR = D.ramos[0];
    var draw = function () {
      chat.innerHTML = "";
      chat.appendChild(el("div", "sx-day", "Hoje"));
      var m = el("div", "sx-msg");
      m.appendChild(document.createTextNode(curR.msg));
      m.appendChild(el("small", "", "09:41"));
      chat.appendChild(m);
      var sug = el("button", "sx-act o", "Ver sugestão de resposta");
      sug.type = "button";
      chat.appendChild(sug);
      var cli = el("div", "sx-cli");
      var cav = el("span", "sx-dav", curR.cliente.charAt(0));
      var ct = el("div");
      ct.appendChild(el("small", "", "Cliente ao lado"));
      ct.appendChild(el("b", "", curR.cliente));
      ct.appendChild(el("em", "", "Quer: " + curR.item + " · " + curR.valor));
      var stt = el("i", "", "Novo contato");
      cli.appendChild(cav);
      cli.appendChild(ct);
      cli.appendChild(stt);
      chat.appendChild(cli);
      sug.addEventListener("click", function () {
        sug.remove();
        var b = el("div", "sx-sugg");
        b.appendChild(el("small", "", "Sugestão · você revisa antes de usar"));
        b.appendChild(el("span", "", curR.sug));
        chat.appendChild(b);
        var r = el("button", "sx-act", "Registrar como oportunidade");
        r.type = "button";
        chat.appendChild(r);
        r.addEventListener("click", function () {
          r.remove();
          stt.textContent = "Quente";
          stt.className = "hot";
          var c = el("div", "sx-opc");
          c.appendChild(el("b", "", curR.cliente + " · " + curR.item));
          c.appendChild(el("span", "", "Interesse: quente · " + curR.valor));
          chat.insertBefore(c, cli);
          chat.insertBefore(el("p", "tag-ex", "Exemplo ilustrativo: nada é enviado."), cli);
        });
      });
      nameEl.textContent = curR.cliente;
      avEl.textContent = curR.cliente.charAt(0);
    };
    /* Os botões de ramo são criados por premium-v5.js (um só estado para hero, demonstração e passo 2). */
    window.SMEI_DEMO = {
      draw: function (id) {
        curR =
          D.ramos.filter(function (r) {
            return r.id === id;
          })[0] || D.ramos[0];
        draw();
      },
    };
    window.SMEI_DEMO.draw("presentes");
  }

  /* ======================================================================
     6. economia: as animações em laço das seções pausam fora da tela
     ====================================================================== */
  if ("IntersectionObserver" in window) {
    var io4 = new IntersectionObserver(
      function (es) {
        es.forEach(function (x) {
          x.target.classList.toggle("sx-off", !x.isIntersecting);
        });
      },
      { rootMargin: "120px" },
    );
    $$("[data-sx]").forEach(function (s) {
      io4.observe(s);
    });
  }
})();
