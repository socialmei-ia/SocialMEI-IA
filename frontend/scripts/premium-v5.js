/* SocialMEI-IA · Experiência Premium v5 (landing)
   1. Ramo escolhido na hero → mural, passo 2/3 e cadastro (chave localStorage "smei-ramo", a mesma que o onboarding já lê).
   2. "Cada parte do negócio": índice + palco com abas acessíveis.
   3. Três passos: escolhas reais (ramo e cor) e roteiro que muda com o ramo.
   4. FAQ com abertura e fechamento suaves (Web Animations API), teclado e movimento reduzido.
   Tudo local: nenhuma rede, nada é enviado. Grava smei-ramo e smei-brand (preferências, localStorage) e, só se a pessoa digitar no passo 1, smei-nome e smei-email em sessionStorage (somem ao fechar a aba, saem ao criar a conta e podem ser apagados pelo botão "Limpar"; valores antigos em localStorage são removidos).
   Depende de hero-wall.js (window.SMEI_RAMO) e do markup de entrada.html. Se faltar algo, cada bloco simplesmente não roda. */
(function () {
  "use strict";
  var root = document.documentElement;
  var $ = function (s, r) {
    return (r || document).querySelector(s);
  };
  var $$ = function (s, r) {
    return Array.prototype.slice.call((r || document).querySelectorAll(s));
  };
  var reduceMQ = matchMedia("(prefers-reduced-motion: reduce)");
  var calm = function () {
    return root.classList.contains("calm") || reduceMQ.matches;
  };
  function lg(k) {
    try {
      return localStorage.getItem(k);
    } catch (e) {
      return null;
    }
  }
  function ls(k, v) {
    try {
      v == null || v === "" ? localStorage.removeItem(k) : localStorage.setItem(k, v);
    } catch (e) {
      /* armazenamento bloqueado: a escolha vale só nesta visita */
    }
  }

  /* ================= 1. RAMO ================= */
  var LAND = window.SMEI_LANDING || {},
    ROT = LAND.rotulos || {},
    ORDEM = LAND.ordem || ["comida", "moda", "beleza", "casa", "presentes", "outra"];
  var NOMES = {
    comida: "Alimentação e confeitaria",
    moda: "Moda e acessórios",
    beleza: "Beleza e estética",
    casa: "Casa, reparos e limpeza",
    presentes: "Presentes e artesanato",
    outra: "Outra atividade",
  };
  var ramo = (function () {
    var v = lg("smei-ramo");
    return NOMES[v] ? v : "";
  })();
  var views = [];
  function perfilTemRamo() {
    try {
      var p = JSON.parse(lg("smei-perfil") || "null");
      return !!(p && p.areaId);
    } catch (e) {
      return false;
    }
  }

  function setRamo(id) {
    ramo = id === ramo ? "" : id; /* tocar de novo na mesma escolha desfaz */
    ls("smei-ramo", ramo);
    if (window.SMEI_RAMO) window.SMEI_RAMO.set(ramo || "presentes");
    views.forEach(function (f) {
      f();
    });
  }

  /* hero */
  var heroChips = $$(".hx-chip");
  var st = document.getElementById("hxRamoSt");
  heroChips.forEach(function (b) {
    b.addEventListener("click", function () {
      setRamo(b.getAttribute("data-ramo"));
    });
  });
  views.push(function () {
    heroChips.forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-ramo") === ramo ? "true" : "false");
    });
    if (!st) return;
    st.textContent = !ramo
      ? ""
      : perfilTemRamo()
        ? "Isso muda só os exemplos desta página. O ramo da sua conta continua como está."
        : "No cadastro, “" + NOMES[ramo] + "” já vem marcado. Você pode trocar.";
    st.classList.toggle("on", !!ramo);
  });

  /* demonstração: mesmos botões e mesma escolha da hero */
  var demoChips = document.querySelector("#ramoDemo .sx-chips");
  if (demoChips && window.SMEI_DEMO) {
    ORDEM.forEach(function (id) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "sx-chip";
      b.textContent = ROT[id] || NOMES[id];
      b.setAttribute("data-ramo", id);
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", function () {
        setRamo(id);
      });
      demoChips.appendChild(b);
    });
    views.push(function () {
      $$("button", demoChips).forEach(function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-ramo") === ramo ? "true" : "false");
      });
      window.SMEI_DEMO.draw(ramo || "presentes");
    });
  }

  /* passo 2: ramo e cor de verdade */
  var stRamo = document.getElementById("stRamo"),
    stCor = document.getElementById("stCor"),
    stTar = document.getElementById("stTarefas");
  var PASSO2 = ORDEM.map(function (id) {
    return [id, ROT[id] || NOMES[id]];
  });
  var CORES = [
    ["", "Azul", "#2f6bff"],
    ["v", "Verde", "#16a34a"],
    ["l", "Laranja", "#f59e0b"],
    ["r", "Roxo", "#a855f7"],
  ];
  var cor = (function () {
    var v = lg("smei-brand") || "";
    return CORES.some(function (c) {
      return c[0] === v;
    })
      ? v
      : "";
  })();
  if (stRamo) {
    PASSO2.forEach(function (p) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = p[1];
      b.setAttribute("data-ramo", p[0]);
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", function () {
        setRamo(p[0]);
      });
      stRamo.appendChild(b);
    });
    views.push(function () {
      $$("button", stRamo).forEach(function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-ramo") === ramo ? "true" : "false");
      });
    });
  }
  if (stCor) {
    CORES.forEach(function (c) {
      var b = document.createElement("button");
      b.type = "button";
      b.style.setProperty("--sw", c[2]);
      b.setAttribute("aria-label", c[1]);
      b.title = c[1];
      b.setAttribute("data-cor", c[0]);
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", function () {
        cor = c[0];
        ls("smei-brand", cor);
        views.forEach(function (f) {
          f();
        });
      });
      stCor.appendChild(b);
    });
    views.push(function () {
      var cur =
        CORES.filter(function (c) {
          return c[0] === cor;
        })[0] || CORES[0];
      $$("button", stCor).forEach(function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-cor") === cor ? "true" : "false");
      });
      var como = document.getElementById("como");
      if (como) como.style.setProperty("--pick", cur[2]);
    });
  }

  /* passo 3: roteiro com as palavras do ramo; marcar/desmarcar é só da demonstração */
  var marcados = [true, true, false];
  function tarefas() {
    var A = window.SMEI_RAMO,
      rid = ramo && ramo !== "outra" ? ramo : "presentes";
    var rep = rid === "presentes" ? "Repor vela" : A ? A.R("Repor vela artesanal") : "Repor vela";
    return ["Responder a Emilly", "Cobrar a Tawanny", rep];
  }
  if (stTar) {
    views.push(function () {
      var t = tarefas();
      stTar.innerHTML = "";
      t.forEach(function (txt, n) {
        var l = document.createElement("label");
        l.className = "pv-ck";
        var i = document.createElement("input");
        i.type = "checkbox";
        i.checked = marcados[n];
        i.addEventListener("change", function () {
          marcados[n] = i.checked;
        });
        var s = document.createElement("span");
        s.textContent = txt;
        l.appendChild(i);
        l.appendChild(s);
        stTar.appendChild(l);
      });
    });
  }

  /* cadastro: a prévia ao lado acompanha o ramo escolhido (e continua mostrando o nome digitado) */
  var pvBz = document.getElementById("pvBz"),
    wsx = $$(".wsx-r");
  var PADRAO = "Seu espaço";
  function previaCadastro() {
    var rid = ramo && ramo !== "outra" ? ramo : "presentes",
      A = window.SMEI_RAMO;
    if (pvBz && pvBz.textContent === PADRAO && ramo)
      pvBz.textContent = "Seu espaço · " + NOMES[ramo];
    else if (pvBz && /^Seu espaço · /.test(pvBz.textContent) && !ramo) pvBz.textContent = PADRAO;
    if (wsx.length === 3 && A) {
      var txt =
        rid === "presentes"
          ? ["Quero comprar o kit. Como pago?", "Repor vela artesanal"]
          : [A.R("Quero comprar o kit. Como pago?"), A.R("Repor vela artesanal")];
      wsx[0].querySelector("small").textContent = txt[0];
      wsx[2].querySelector("b").textContent = txt[1];
    }
  }
  if (pvBz) {
    views.push(previaCadastro);
    new MutationObserver(function () {
      previaCadastro();
    }).observe(pvBz, { childList: true, characterData: true, subtree: true });
  }
  views.forEach(function (f) {
    f();
  });
  if (
    ramo &&
    window.SMEI_RAMO &&
    window.SMEI_RAMO.get() !== (ramo === "outra" ? "presentes" : ramo)
  )
    window.SMEI_RAMO.set(ramo);

  /* ================= 2. PRODUTO: índice + palco ================= */
  var pv = document.getElementById("pvx");
  if (pv) {
    var tabs = $$(".pv-t", pv),
      panels = $$(".pv-panel", pv),
      cur = 0;
    var horiz = matchMedia("(max-width:900px)");
    var show = function (i, focus) {
      cur = i;
      tabs.forEach(function (t, n) {
        t.setAttribute("aria-selected", n === i ? "true" : "false");
        t.tabIndex = n === i ? 0 : -1;
        t.classList.toggle("done", n < i);
      });
      panels.forEach(function (p, n) {
        p.classList.toggle("on", n === i);
      });
      pv.style.setProperty("--pv-i", i);
      if (focus) tabs[i].focus();
      if (horiz.matches && tabs[i].scrollIntoView) {
        var bx = tabs[i].parentNode;
        bx.scrollTo({ left: tabs[i].offsetLeft - 16, behavior: calm() ? "auto" : "smooth" });
      }
    };
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () {
        show(i);
      });
      t.addEventListener("keydown", function (e) {
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
        show((n + tabs.length) % tabs.length, true);
      });
    });
    $$("[data-pv-next]", pv).forEach(function (b) {
      b.addEventListener("click", function () {
        show((cur + 1) % tabs.length);
      });
    });
    show(0);
  }

  /* ================= 4. FAQ suave ================= */
  var DUR = 300,
    EASE = "cubic-bezier(.2,.7,.2,1)";
  $$("details.faq").forEach(function (d) {
    var sum = d.querySelector("summary"),
      body = d.querySelector(".fa"),
      anim = null;
    if (!sum || !body) return;
    d.setAttribute("data-state", d.open ? "open" : "closed");
    function run(to) {
      var from = anim ? body.getBoundingClientRect().height : d.open ? body.scrollHeight : 0;
      if (anim) {
        anim.cancel();
        anim = null;
      }
      if (to > 0) d.open = true;
      d.setAttribute("data-state", to > 0 ? "open" : "closed");
      var end = to > 0 ? body.scrollHeight : 0;
      if (calm() || !body.animate) {
        if (!end) d.open = false;
        return;
      }
      body.style.overflow = "hidden";
      anim = body.animate(
        [
          { height: from + "px", opacity: to > 0 ? Math.min(from / (end || 1), 1) * 0.4 : 1 },
          { height: end + "px", opacity: to > 0 ? 1 : 0 },
        ],
        { duration: DUR, easing: EASE },
      );
      var mine = anim;
      mine.onfinish = function () {
        if (anim !== mine) return;
        anim = null;
        body.style.overflow = "";
        if (!end) d.open = false;
      };
      mine.oncancel = function () {
        body.style.overflow = "";
      };
    }
    sum.addEventListener("click", function (e) {
      e.preventDefault();
      run(d.getAttribute("data-state") === "open" ? 0 : 1);
    });
    sum.addEventListener("keydown", function (e) {
      var all = $$("details.faq > summary"),
        i = all.indexOf(sum),
        n =
          e.key === "ArrowDown"
            ? i + 1
            : e.key === "ArrowUp"
              ? i - 1
              : e.key === "Home"
                ? 0
                : e.key === "End"
                  ? all.length - 1
                  : null;
      if (n === null) return;
      e.preventDefault();
      all[(n + all.length) % all.length].focus();
    });
  });

  /* ================= 5. PASSO 1: nome e e-mail seguem para o cadastro ================= */
  (function () {
    var f = document.getElementById("sxStart");
    if (!f) return;
    var nome = document.getElementById("sxNome"),
      mail = document.getElementById("sxMail"),
      err = document.getElementById("sxErr");
    var hint = document.getElementById("sxHint"),
      clr = document.getElementById("sxClear"),
      hintTxt = hint ? hint.textContent : "";
    /* Dados pessoais só na sessão da aba (computador compartilhado): nada fica no disco do navegador. */
    function sg(k) {
      try {
        return sessionStorage.getItem(k);
      } catch (e) {
        return null;
      }
    }
    function ss(k, v) {
      try {
        v == null || v === "" ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v);
      } catch (e) {
        /* bloqueado: vale só nesta visita */
      }
    }
    function apagarAntigos() {
      ["smei-nome", "smei-email"].forEach(function (k) {
        try {
          localStorage.removeItem(k);
        } catch (e) {
          /* ignora */
        }
      });
    }
    apagarAntigos(); /* versões anteriores gravavam em localStorage */
    var guardado = { n: sg("smei-nome") || "", m: sg("smei-email") || "" };
    nome.value = guardado.n;
    mail.value = guardado.m;
    function mostrarLimpar() {
      if (clr) clr.hidden = !(sg("smei-nome") || sg("smei-email") || nome.value || mail.value);
    }
    function fill() {
      var cn = document.getElementById("cNome"),
        cm = document.getElementById("cMail");
      if (cn && !cn.value) cn.value = sg("smei-nome") || "";
      if (cm && !cm.value) cm.value = sg("smei-email") || "";
      [cn, cm].forEach(function (el) {
        if (el && el.value) el.dispatchEvent(new Event("input", { bubbles: true }));
      });
    }
    function limpar(aviso) {
      var cn = document.getElementById("cNome"),
        cm = document.getElementById("cMail");
      /* só apaga no cadastro o que veio daqui; o que a pessoa digitou lá fica */
      if (cn && cn.value && cn.value === (sg("smei-nome") || "")) cn.value = "";
      if (cm && cm.value && cm.value === (sg("smei-email") || "")) cm.value = "";
      ss("smei-nome", "");
      ss("smei-email", "");
      apagarAntigos();
      nome.value = "";
      mail.value = "";
      err.textContent = "";
      nome.parentNode.classList.remove("bad");
      mostrarLimpar();
      if (aviso && hint) {
        hint.textContent = "Nome e e-mail apagados deste navegador.";
        setTimeout(function () {
          hint.textContent = hintTxt;
        }, 4000);
      }
    }
    if (clr)
      clr.addEventListener("click", function () {
        limpar(true);
        nome.focus();
      });
    window.addEventListener("smei:conta-criada", function () {
      limpar(false);
    });
    [nome, mail].forEach(function (el) {
      el.addEventListener("input", mostrarLimpar);
    });
    mostrarLimpar();
    window.addEventListener("hashchange", function () {
      if (/^#\/?cadastro/.test(location.hash)) fill();
    });
    fill();
    nome.addEventListener("input", function () {
      err.textContent = "";
      nome.parentNode.classList.remove("bad");
    });
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var n = nome.value.trim(),
        m = mail.value.trim();
      if (n.length < 2) {
        err.textContent = "Como podemos te chamar? Digite seu nome.";
        nome.parentNode.classList.add("bad");
        nome.focus();
        return;
      }
      ss("smei-nome", n);
      ss("smei-email", m);
      mostrarLimpar();
      fill();
      location.hash = "#/cadastro";
      setTimeout(fill, 60);
    });
  })();
})();
