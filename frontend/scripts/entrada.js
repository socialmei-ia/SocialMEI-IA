/* SocialMEI.IA · porta de entrada (demonstração local)
   Landing, cadastro/login e onboarding. Nada é enviado a servidor:
   o perfil fica no localStorage deste navegador (chave smei-perfil) e a senha nunca é guardada. */
(function () {
  "use strict";

  var account = window.SocialMEIV22Account,
    remote = !!account && account.remote;
  var authSettled = !remote,
    remoteRevision = null,
    remoteProfile = null,
    remoteAreaAtLoad = "";

  /* ---------- utilidades ---------- */
  var $ = function (s, r) {
    return (r || document).querySelector(s);
  };
  var $$ = function (s, r) {
    return Array.prototype.slice.call((r || document).querySelectorAll(s));
  };
  function storageKey(k) {
    if (remote && /^(smei-perfil|smei-sessao|smei-onb|smei-brand|smei-qc)$/.test(k)) {
      var u = account.auth.current;
      return "smei-v22-account:" + (u ? u.usuario.id + ":" + u.negocio.id : "anonymous") + ":" + k;
    }
    return k;
  }
  function lg(k) {
    try {
      return localStorage.getItem(storageKey(k));
    } catch (e) {
      return null;
    }
  }
  function ls(k, v) {
    try {
      v == null ? localStorage.removeItem(storageKey(k)) : localStorage.setItem(storageKey(k), v);
    } catch (e) {}
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function ico(n, s, w) {
    return (
      '<svg class="i" width="' +
      (s || 18) +
      '" height="' +
      (s || 18) +
      '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' +
      (w || 2) +
      '" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><use href="#i-' +
      n +
      '"/></svg>'
    );
  }
  function json(k) {
    try {
      return JSON.parse(lg(k) || "null");
    } catch (e) {
      return null;
    }
  }
  function calmo() {
    return (
      document.documentElement.classList.contains("calm") ||
      matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }
  function toast(t) {
    var e = document.createElement("div");
    e.className = "toast";
    e.setAttribute("role", "status");
    e.textContent = t;
    document.body.appendChild(e);
    setTimeout(function () {
      e.remove();
    }, 3200);
  }

  async function showRecovery() {
    var d = document.getElementById("v22-recovery");
    if (!d) {
      d = document.createElement("dialog");
      d.id = "v22-recovery";
      d.className = "dlg";
      d.setAttribute("aria-label", "Recuperar acesso");
      d.style.cssText =
        "width:min(480px,calc(100% - 32px));margin:auto;padding:24px;border:1px solid var(--b);border-radius:20px;background:var(--w);color:var(--t);max-height:calc(100dvh - 32px);overflow:auto";
      d.innerHTML =
        '<form novalidate><h2>Recuperar acesso</h2><p class="m">Solicite um código por e-mail. Ele vale por 15 minutos.</p><label for="rMail">E-mail</label><input class="in" id="rMail" type="email" autocomplete="email"><button class="btn o" type="button" data-recovery-request>Enviar código</button><label for="rToken">Código recebido</label><input class="in" id="rToken" maxlength="43" autocomplete="one-time-code" spellcheck="false"><label for="rPassword">Nova senha</label><input class="in" id="rPassword" type="password" autocomplete="new-password" minlength="8" maxlength="128"><label for="rConfirm">Confirmar senha</label><input class="in" id="rConfirm" type="password" autocomplete="new-password"><p class="err" role="status" aria-live="polite" id="rStatus"></p><div class="acts"><button class="btn o" type="button" data-recovery-close>Voltar</button><button class="btn" type="submit">Redefinir senha</button></div></form>';
      var form = d.querySelector("form");
      form.querySelectorAll("input").forEach(function (input) {
        var label = form.querySelector('label[for="' + input.id + '"]');
        var fld = document.createElement("div");
        fld.className = "fld";
        input.before(fld);
        if (label) fld.appendChild(label);
        fld.appendChild(input);
      });
      document.body.appendChild(d);
      d.querySelector("[data-recovery-close]").onclick = function () {
        d.close();
      };
      d.addEventListener("close", function () {
        d.querySelectorAll("input").forEach(function (i) {
          i.value = "";
        });
        $("#forgot").focus();
      });
      var busy = false;
      async function recoveryAction(request) {
        if (busy) return;
        var status = d.querySelector("#rStatus"),
          email = d.querySelector("#rMail").value.trim(),
          pass = d.querySelector("#rPassword").value,
          token = d.querySelector("#rToken").value.trim();
        if (request && !emailOk(email)) {
          status.textContent = "Informe um e-mail válido.";
          return;
        }
        if (!request) {
          var policy = account.auth.passwordPolicy(pass);
          if (
            policy.error ||
            pass !== d.querySelector("#rConfirm").value ||
            !/^[A-Za-z0-9_-]{43}$/.test(token)
          ) {
            status.textContent =
              policy.error || "Confira o código completo e a confirmação da senha.";
            return;
          }
        }
        busy = true;
        d.querySelectorAll("button").forEach(function (b) {
          b.disabled = true;
        });
        status.textContent = request ? "Solicitando código…" : "Redefinindo senha…";
        try {
          await account.ready;
          var result = await account.auth.request(
            request ? "/auth/recovery/request" : "/auth/recovery/confirm",
            "POST",
            request ? { email: email } : { token: token, nova: pass },
          );
          status.textContent = request
            ? result.message
            : "Senha redefinida. Entre com a nova senha.";
          if (!request)
            d.querySelectorAll("input[type=password],#rToken").forEach(function (i) {
              i.value = "";
            });
        } catch (error) {
          status.textContent = error.message;
        } finally {
          busy = false;
          d.querySelectorAll("button").forEach(function (b) {
            b.disabled = false;
          });
        }
      }
      d.querySelector("[data-recovery-request]").onclick = function () {
        recoveryAction(true);
      };
      d.querySelector("form").onsubmit = function (e) {
        e.preventDefault();
        recoveryAction(false);
      };
    }
    d.querySelector("#rMail").value = $("#eMailL").value;
    d.showModal();
    d.querySelector("#rMail").focus();
  }

  /* ---------- perfil (localStorage) ---------- */
  var PERFIL = "smei-perfil",
    SESSAO = "smei-sessao",
    RASCUNHO = "smei-onb";
  var perfil = remote ? {} : json(PERFIL) || {};
  function salvarPerfil(p) {
    perfil = Object.assign(perfil, p);
    ls(PERFIL, JSON.stringify(perfil));
  }

  /* ---------- tema e modo calmo (mesmas chaves do app) ---------- */
  var dark = matchMedia("(prefers-color-scheme: dark)");
  function aplicarTema() {
    var t = lg("smei-theme") || "auto",
      d = t === "escuro" || (t === "auto" && dark.matches);
    document.documentElement.dataset.theme = d ? "dark" : "light";
  }
  dark.addEventListener && dark.addEventListener("change", aplicarTema);
  function aplicarCalmo() {
    var c = lg("smei-calm") === "1";
    document.documentElement.classList.toggle("calm", c);
    $$("[data-act=calm]").forEach(function (b) {
      b.setAttribute("aria-pressed", c);
    });
  }
  function aplicarMarca() {
    var m =
      { v: "#0e7a43", r: "#6a46d9", k: "#c2185b", l: "#a64a08", g: "#334155" }[
        lg("smei-brand") || ""
      ] || "#0a5cf5";
    document.documentElement.style.setProperty("--brand", m);
  }

  /* ---------- navegação por hash: #/  #/cadastro  #/entrar  #/comecar ---------- */
  var VIEWS = { site: $("#v-site"), auth: $("#v-auth"), ob: $("#v-ob") };
  function rota() {
    return (location.hash.replace(/^#\/?/, "") || "").split("/")[0];
  }
  function mostrar(v) {
    Object.keys(VIEWS).forEach(function (k) {
      VIEWS[k].hidden = k !== v;
    });
  }
  function ir(h) {
    location.hash = h;
  }
  function router(primeira) {
    var r = rota();
    if (remote && r === "comecar" && (!authSettled || !account.auth.current)) {
      mostrar("auth");
      aba("entrar", false);
      if (authSettled) ir("#/entrar");
      return;
    }
    if (r !== "comecar") aplicarMarca();
    if (r === "cadastro" || r === "entrar") {
      mostrar("auth");
      aba(r, false);
      document.title = (r === "entrar" ? "Entrar" : "Criar conta") + " · SocialMEI.IA";
    } else if (r === "comecar") {
      mostrar("ob");
      iniciarOb();
      document.title = "Conte do seu negócio · SocialMEI.IA";
    } else if (/^(produto|paramei|como|ia|demo|precos|perguntas)$/.test(r)) {
      mostrar("site");
      document.title = "SocialMEI.IA · Seu negócio, mais simples";
      rolar(r, !primeira);
      return;
    } else {
      mostrar("site");
      document.title = "SocialMEI.IA · Seu negócio, mais simples";
      if (!primeira) window.scrollTo(0, 0);
    }
    if (!primeira) {
      var f = $(
        r === "comecar"
          ? "#obMain"
          : r === "cadastro" || r === "entrar"
            ? "#authMain"
            : "#conteudo",
      );
      f && f.focus({ preventScroll: true });
    }
    if (r === "cadastro" || r === "entrar" || r === "comecar") window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", function () {
    router(false);
  });

  /* ---------- LANDING ---------- */
  function rolar(id, suave) {
    var e = document.getElementById(id);
    if (!e) return;
    e.scrollIntoView({ behavior: suave && !calmo() ? "smooth" : "auto", block: "start" });
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest("[data-go]");
    if (a) {
      e.preventDefault();
      var id = a.dataset.go;
      $("#links").classList.remove("open");
      $("#menuB").setAttribute("aria-expanded", "false");
      if (rota() && !/^(produto|paramei|como|ia|demo|precos|perguntas)?$/.test(rota())) ir("#/");
      setTimeout(function () {
        rolar(id, true);
      }, 0);
      return;
    }
    var t = e.target.closest("[data-act=tema]");
    if (t) {
      var cur = document.documentElement.dataset.theme;
      ls("smei-theme", cur === "dark" ? "claro" : "escuro");
      aplicarTema();
      return;
    }
    var c = e.target.closest("[data-act=calm]");
    if (c) {
      ls("smei-calm", lg("smei-calm") === "1" ? "0" : "1");
      aplicarCalmo();
      return;
    }
    var d = e.target.closest("[data-demo-app]");
    if (d && remote) {
      e.preventDefault();
      toast("Entre na sua conta para acessar seus dados.");
      ir("#/entrar");
      return;
    }
    if (d) {
      /* sem cadastro: usa o perfil de exemplo do app, mas marca a sessão de demonstração */ ls(
        SESSAO,
        "1",
      );
      return;
    }
    var mb = e.target.closest("#menuB");
    if (mb) {
      var o = $("#links").classList.toggle("open");
      mb.setAttribute("aria-expanded", o);
      return;
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && $("#links").classList.contains("open")) {
      $("#links").classList.remove("open");
      $("#menuB").setAttribute("aria-expanded", "false");
      $("#menuB").focus();
    }
  });
  window.addEventListener(
    "scroll",
    function () {
      $("#nav").classList.toggle("sc", scrollY > 8);
    },
    { passive: true },
  );

  /* mensagens de exemplo da prévia no topo da landing */
  var CHATS = [
    {
      n: "Lia (exemplo)",
      i: "L",
      bg: "#e4dcff",
      fg: "#4a3aa8",
      p: "Como pagar o kit?",
      m: [
        ["rx", "Quero comprar o kit. Pode me explicar como pagar?"],
        ["tx", "Claro, Lia! Pode ser Pix ou na retirada."],
      ],
      s: "Lia, o kit está separado e o pagamento pode ser na retirada. Quer combinar o horário?",
    },
    {
      n: "Bruno (exemplo)",
      i: "B",
      bg: "#dbe8ff",
      fg: "#1d4fb8",
      p: "Qual o valor?",
      m: [
        ["rx", "Qual o valor do serviço?"],
        ["tx", "Oi, Bruno! Posso te mandar um orçamento ainda hoje."],
      ],
      s: "Bruno, o serviço sai a partir de R$ 90. Me conta o que você precisa para eu fechar o valor certinho?",
    },
    {
      n: "Ana (exemplo)",
      i: "A",
      bg: "#dcf3df",
      fg: "#2a7a3a",
      p: "Atende na minha cidade?",
      m: [
        ["rx", "Você atende na minha cidade?"],
        ["tx", "Atendo sim! Me diz o bairro que eu confirmo."],
      ],
      s: "Ana, atendemos sim! Me passa seu bairro e o melhor dia para eu combinar com você?",
    },
  ];
  var cAtual = 0,
    cTimer = null;
  function pintarChat(i, manual) {
    if (!$("#heroTh")) return;
    cAtual = i;
    var c = CHATS[i];
    $("#heroTh").innerHTML = CHATS.map(function (x, k) {
      return (
        '<button type="button" data-ch="' +
        k +
        '" aria-pressed="' +
        (k === i) +
        '"><span class="av" style="background:' +
        x.bg +
        ";color:" +
        x.fg +
        '">' +
        x.i +
        "</span><span><b>" +
        esc(x.n.replace(" (exemplo)", "")) +
        "</b><small>" +
        esc(x.p) +
        "</small></span></button>"
      );
    }).join("");
    $("#heroConv").innerHTML =
      c.m
        .map(function (m, k) {
          return (
            '<div class="msg ' +
            m[0] +
            '" style="animation-delay:' +
            k * 140 +
            'ms">' +
            esc(m[1]) +
            "</div>"
          );
        })
        .join("") +
      '<div class="ia-s"><b>' +
      ico("spark", 14) +
      "Sugestão da IA · revise antes de enviar</b>" +
      esc(c.s) +
      "</div>";
    if (manual) agendarChat();
  }
  function agendarChat() {
    if (!$("#heroTh")) return;
    clearInterval(cTimer);
    if (calmo()) return;
    cTimer = setInterval(function () {
      pintarChat((cAtual + 1) % CHATS.length, false);
    }, 5200);
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-ch]");
    if (b) pintarChat(+b.dataset.ch, true);
  });

  /* revelar ao rolar */
  function revelar() {
    var els = $$(".rv");
    if (!("IntersectionObserver" in window) || calmo()) {
      els.forEach(function (e) {
        e.classList.add("on");
      });
      return;
    }
    var io = new IntersectionObserver(
      function (es) {
        es.forEach(function (x) {
          if (x.isIntersecting) {
            x.target.classList.add("on");
            io.unobserve(x.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
    );
    els.forEach(function (e) {
      io.observe(e);
    });
  }

  /* ---------- CADASTRO / ENTRAR ---------- */
  function aba(k, foco) {
    var c = k === "cadastro";
    $("#panC").hidden = !c;
    $("#panE").hidden = c;
    $("#tabC").setAttribute("aria-selected", c);
    $("#tabE").setAttribute("aria-selected", !c);
    $("#tabC").tabIndex = c ? 0 : -1;
    $("#tabE").tabIndex = c ? -1 : 0;
    $("#artH").textContent = c
      ? "Seu espaço começa aqui."
      : perfil && perfil.nome
        ? "Que bom te ver, " + perfil.nome.split(/\s+/)[0] + "."
        : "O que vamos cuidar hoje?";
    $("#artP").textContent = c
      ? "Conversa, cliente e próxima ação. Tudo encontra seu lugar."
      : "Responder clientes, registrar vendas e revisar cobranças, tudo no mesmo lugar.";
    var tb = $(".tabs");
    if (tb) tb.dataset.on = k; /* auth v20: indicador deslizante */
    var ar = $(".art");
    if (ar) ar.dataset.t = k;
    if (c) previa();
    else perfilNoLogin();
    if (foco) {
      (c ? $("#cNome") : $("#eMailL")).focus();
    }
  }
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-tab]");
    if (t) {
      var k = t.dataset.tab;
      if (rota() !== k) ir("#/" + k);
      else aba(k, true);
      t.getAttribute("role") === "tab" && t.focus();
    }
    var p = e.target.closest("[data-pw]");
    if (p) {
      var i = document.getElementById(p.dataset.pw),
        v = i.type === "password";
      i.type = v ? "text" : "password";
      p.textContent = v ? "Ocultar" : "Mostrar";
      p.setAttribute("aria-pressed", v);
    }
  });
  $(".tabs").addEventListener("keydown", function (e) {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      ir("#/" + (rota() === "entrar" ? "cadastro" : "entrar"));
      setTimeout(function () {
        ($("#tabC").getAttribute("aria-selected") === "true" ? $("#tabC") : $("#tabE")).focus();
      }, 0);
    }
  });

  var COMUNS = [
    "12345678",
    "123456789",
    "1234567890",
    "01234567",
    "87654321",
    "password",
    "password1",
    "senha123",
    "senha1234",
    "qwerty123",
    "abc12345",
    "admin123",
    "iloveyou",
  ];
  function forca(v) {
    if (remote && v) {
      var policy = account.auth.passwordPolicy(v);
      if (policy.error) return { s: 1, ok: false, t: policy.error };
    }
    if (!v)
      return {
        s: 0,
        ok: false,
        t: "Use 8 ou mais caracteres. Uma frase longa é boa e fácil de lembrar.",
      };
    var n = Array.from(v).length;
    if (n < 8)
      return {
        s: 1,
        ok: false,
        t: "Ainda curta: faltam " + (8 - n) + " caractere" + (8 - n > 1 ? "s" : "") + ".",
      };
    if (COMUNS.indexOf(v.toLowerCase()) > -1 || new Set(v).size === 1)
      return { s: 1, ok: false, t: "Essa senha é muito comum. Escolha outra, menos previsível." };
    var v2 =
        (/[a-z]/.test(v) ? 1 : 0) +
        (/[A-Z]/.test(v) ? 1 : 0) +
        (/\d/.test(v) ? 1 : 0) +
        (/[^A-Za-z0-9]/.test(v) ? 1 : 0),
      s = n >= 14 ? 4 : n >= 11 || v2 >= 3 ? 3 : 2;
    return {
      s: s,
      ok: true,
      t: s >= 3 ? "Senha forte. Boa escolha!" : "Senha razoável. Quanto mais longa, melhor.",
    };
  }
  function erro(id, msg, campo) {
    var e = document.getElementById(id);
    if (e) e.textContent = msg || "";
    var f = campo && document.getElementById(campo);
    if (f) f.setAttribute("aria-invalid", msg ? "true" : "false");
    return !!msg;
  }
  function mascaraTel(v) {
    var d = v.replace(/\D/g, "").slice(0, 11);
    if (!d) return "";
    if (d.length <= 2) return "(" + d;
    if (d.length <= 6) return "(" + d.slice(0, 2) + ") " + d.slice(2);
    if (d.length <= 10) return "(" + d.slice(0, 2) + ") " + d.slice(2, 6) + "-" + d.slice(6);
    return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
  }
  /* ao digitar, some o aviso do próprio campo */
  function limpar(c) {
    if (c.getAttribute && c.getAttribute("aria-invalid") === "true")
      c.setAttribute("aria-invalid", "false");
    var f = c.closest && c.closest(".fld,.chk"),
      er =
        f && f.nextElementSibling && f.classList.contains("chk")
          ? f.nextElementSibling
          : f && f.querySelector(".err");
    if (er && er.classList.contains("err")) er.textContent = "";
  }
  var emailOk = function (v) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v);
  };

  function previa() {
    var n = $("#cNome").value.trim(),
      m = $("#cMail").value.trim(),
      t = $("#cTel").value.trim(),
      s = forca($("#cPass").value);
    var a = !!n && emailOk(m) ? 1 : 0,
      b = t.replace(/\D/g, "").length >= 10 ? 1 : 0,
      c = s.ok ? 1 : 0;
    $("#pvNn").textContent = n || "Seu perfil";
    $("#pvNm").textContent = m || "Seu e-mail aparece aqui";
    $("#pvTt").textContent = t || "Um canal para conversar (opcional)";
    $("#pvSs").textContent = c ? "Senha pronta" : "Defina sua senha para continuar";
    $("#pvN").classList.toggle("ok", !!a);
    $("#pvT").classList.toggle("ok", !!b);
    $("#pvS").classList.toggle("ok", !!c);
    $$(".prog .tr i").forEach(function (x, k) {
      x.classList.toggle("on", [a, b, c][k] === 1);
    });
    $("#pvProg").textContent = "Prévia local · " + (a + b + c) + " de 3 dados";
    $("#meter").dataset.s = s.s;
    $("#hPass").textContent = s.t;
    ws(n, n ? n.split(/\s+/)[0] : "", "Seu espaço de exemplo");
    marca("cNome", n.length >= 2);
    marca("cMail", emailOk(m));
    marca("cTel", t.replace(/\D/g, "").length >= 10);
    marca("cPass", s.ok);
  }
  /* ---------- auth v20: prévia viva, marcas de campo, Caps Lock, envio com retorno ---------- */
  function ini2(s) {
    var p = String(s || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    return p.length ? ((p[0][0] || "") + (p[1] ? p[1][0] : p[0][1] || "")).toUpperCase() : "SM";
  }
  function ws(nome, primeiro, bz) {
    var a = $("#pvIni"),
      t = ini2(nome);
    if (a.textContent !== t) {
      a.textContent = t;
      a.classList.remove("pop");
      void a.offsetWidth;
      a.classList.add("pop");
    }
    $("#pvHi").textContent = primeiro ? "Olá, " + primeiro + "!" : "Olá!";
    $("#pvBz").textContent = bz;
  }
  function perfilNoLogin() {
    var n = perfil && perfil.nome ? perfil.nome : "";
    ws(
      n,
      n ? n.split(/\s+/)[0] : "",
      perfil && perfil.negocio ? perfil.negocio : "Seu espaço de exemplo",
    );
    var e = $("#eMailL");
    if (e && !e.value && perfil && perfil.email) {
      e.value = perfil.email;
      marca("eMailL", emailOk(perfil.email));
    }
    /* v21: quem aparece aqui pode não ser quem está usando o computador: dá uma saída clara */
    var w = $("#who"),
      tem = !!(perfil && (perfil.nome || perfil.email));
    if (w) {
      w.hidden = !tem;
      if (tem) $("#whoN").textContent = perfil.nome ? perfil.nome.split(/\s+/)[0] : perfil.email;
    }
  }
  /* "Não é você?": apaga neste navegador o que a demonstração guardou de quem criou a conta */
  var SESSAO_CHAVES = ["smei-perfil", "smei-sessao", "smei-onb", "smei-brand", "smei-qc"];
  $("#notYou").addEventListener("click", function () {
    SESSAO_CHAVES.forEach(function (k) {
      ls(k, null);
    });
    perfil = {};
    obEstado = null;
    passo = 0;
    var m = $("#eMailL");
    m.value = "";
    $("#ePassL").value = "";
    erro("eMailLe", "", "eMailL");
    erro("ePassLe", "", "ePassL");
    marca("eMailL", false);
    $("#forgotMsg").textContent = "";
    aplicarMarca();
    aba("entrar", false);
    $("#whoMsg").textContent =
      "Pronto. Apagamos deste navegador o perfil, a cor da marca e as respostas rápidas salvas.";
    m.focus();
  });
  $("#eMailL").addEventListener("input", function () {
    $("#whoMsg").textContent = "";
  });
  function marca(id, ok) {
    var f = document.getElementById(id);
    f = f && f.closest(".fld");
    if (f) f.classList.toggle("ok", !!ok);
  }
  [
    ["cPass", "caps_cPass"],
    ["ePassL", "caps_ePassL"],
  ].forEach(function (x) {
    var i = document.getElementById(x[0]),
      h = document.getElementById(x[1]);
    function f(e) {
      if (e.getModifierState) h.hidden = !e.getModifierState("CapsLock");
    }
    i.addEventListener("keydown", f);
    i.addEventListener("keyup", f);
    i.addEventListener("blur", function () {
      h.hidden = true;
    });
  });
  /* e-mail: avisa ao sair do campo, sem esperar o envio */
  $("#cMail").addEventListener("blur", function () {
    var v = this.value.trim();
    if (v) erro("eMail", emailOk(v) ? "" : "Esse e-mail parece incompleto.", "cMail");
  });
  $("#eMailL").addEventListener("blur", function () {
    var v = this.value.trim();
    if (v) erro("eMailLe", emailOk(v) ? "" : "Esse e-mail parece incompleto.", "eMailL");
  });
  $("#eMailL").addEventListener("input", function () {
    marca("eMailL", emailOk(this.value.trim()));
  });
  $("#cNome").addEventListener("blur", function () {
    var v = this.value.trim();
    if (v && v.length < 2) erro("eNome", "Como podemos te chamar?", "cNome");
  });
  /* envio: o botão mostra o que está acontecendo antes de seguir (sem espera no modo calmo) */
  function enviar(form, fn) {
    var b = form.querySelector("[type=submit]");
    if (calmo() || !b) {
      fn();
      return;
    }
    var t = b.textContent;
    b.dataset.t = t;
    b.classList.add("busy");
    b.setAttribute("aria-busy", "true");
    b.disabled = true;
    b.textContent = b.dataset.busy || "Enviando…";
    setTimeout(function () {
      fn();
      b.classList.remove("busy");
      b.removeAttribute("aria-busy");
      b.disabled = false;
      b.textContent = t;
    }, 550);
  }
  $("#fC").addEventListener("input", function (e) {
    if (e.target.id === "cTel") e.target.value = mascaraTel(e.target.value);
    previa();
    limpar(e.target);
  });
  $("#fC").addEventListener("submit", async function (e) {
    e.preventDefault();
    var n = $("#cNome").value.trim(),
      m = $("#cMail").value.trim(),
      t = $("#cTel").value.trim(),
      p = $("#cPass").value,
      s = forca(p),
      bad = [];
    if (erro("eNome", n.length < 2 ? "Como podemos te chamar?" : "", "cNome")) bad.push("cNome");
    if (
      erro(
        "eMail",
        !m ? "Informe seu e-mail." : !emailOk(m) ? "Esse e-mail parece incompleto." : "",
        "cMail",
      )
    )
      bad.push("cMail");
    if (
      erro(
        "eTel",
        t && t.replace(/\D/g, "").length < 10 ? "Use o DDD e o número. Ou deixe em branco." : "",
        "cTel",
      )
    )
      bad.push("cTel");
    if (erro("ePass", !p ? "Crie uma senha." : !s.ok ? s.t : "", "cPass")) bad.push("cPass");
    if (erro("eTermos", $("#cTermos").checked ? "" : "Aceite os termos para continuar."))
      bad.push("cTermos");
    if (bad.length) {
      document.getElementById(bad[0]).focus();
      return;
    }
    if (remote) {
      var button = $("#fC [type=submit]");
      if (button.disabled) return;
      button.disabled = true;
      button.classList.add("busy");
      button.setAttribute("aria-busy", "true");
      try {
        await account.ready;
        var registration = { nome: n, email: m, telefone: t, senha: p };
        if ($("#cInvite")) registration.convite = $("#cInvite").value.trim();
        await account.register(registration);
      } catch (error) {
        erro("ePass", error.message, "cPass");
      } finally {
        button.disabled = false;
        button.classList.remove("busy");
        button.removeAttribute("aria-busy");
      }
      return;
    }
    /* a senha nunca é guardada */
    $("#cPass").value = "";
    var dados = { nome: n, email: m, tel: t, criadoEm: new Date().toISOString(), demo: true };
    enviar($("#fC"), function () {
      salvarPerfil(dados);
      ls(RASCUNHO, null);
      obEstado = null;
      ir("#/comecar");
    });
  });

  $("#fE").addEventListener("input", function (e) {
    limpar(e.target);
  });
  $("#fC").addEventListener("change", function (e) {
    limpar(e.target);
  });
  $("#fE").addEventListener("submit", async function (e) {
    e.preventDefault();
    var m = $("#eMailL").value.trim(),
      p = $("#ePassL").value,
      bad = [];
    if (
      erro(
        "eMailLe",
        !m ? "Informe seu e-mail." : !emailOk(m) ? "Esse e-mail parece incompleto." : "",
        "eMailL",
      )
    )
      bad.push("eMailL");
    if (erro("ePassLe", !p ? "Informe sua senha." : "", "ePassL")) bad.push("ePassL");
    if (bad.length) {
      document.getElementById(bad[0]).focus();
      return;
    }
    if (remote) {
      var button = $("#fE [type=submit]");
      if (button.disabled) return;
      button.disabled = true;
      button.classList.add("busy");
      button.setAttribute("aria-busy", "true");
      try {
        await account.ready;
        await account.login({ email: m, senha: p });
      } catch (error) {
        erro("ePassLe", error.message, "ePassL");
      } finally {
        button.disabled = false;
        button.classList.remove("busy");
        button.removeAttribute("aria-busy");
      }
      return;
    }
    $("#ePassL").value = "";
    enviar($("#fE"), function () {
      if (perfil && perfil.negocio) {
        salvarPerfil({ email: m });
        ls(SESSAO, "1");
        toast("Você entrou (demonstração)");
        setTimeout(function () {
          location.href = "socialmei-app.html#/inicio";
        }, 500);
      } else {
        salvarPerfil({
          email: m,
          nome:
            perfil.nome ||
            m
              .split("@")[0]
              .replace(/[._-]+/g, " ")
              .replace(/^./, function (c) {
                return c.toUpperCase();
              }),
          demo: true,
        });
        ir("#/comecar");
      }
    });
  });
  $("#forgot").addEventListener("click", async function () {
    if (remote) {
      await showRecovery();
      return;
    }
    var m = $("#eMailL").value.trim();
    $("#forgotMsg").textContent = emailOk(m)
      ? "Em uma conta de verdade, enviaríamos um link para " + m + ". Aqui é só demonstração."
      : "Digite seu e-mail acima e mostramos como seria o aviso.";
    if (!emailOk(m)) $("#eMailL").focus();
  });

  /* ---------- ONBOARDING ---------- */
  var AREAS = [
    {
      id: "beleza",
      t: "Beleza e estética",
      d: "Cabelo, unhas, maquiagem",
      o: [
        "Corte e escova",
        "Manicure e pedicure",
        "Maquiagem",
        "Design de sobrancelhas",
        "Depilação",
        "Massagem",
      ],
      tipo: "servicos",
    },
    {
      id: "comida",
      t: "Alimentação e confeitaria",
      d: "Bolos, doces, marmitas",
      o: [
        "Bolos e doces",
        "Salgados",
        "Marmitas",
        "Encomendas para festas",
        "Lanches",
        "Pães e café",
      ],
      tipo: "produtos",
    },
    {
      id: "moda",
      t: "Moda e acessórios",
      d: "Roupas, bolsas, bijuterias",
      o: [
        "Roupas",
        "Bijuterias e acessórios",
        "Calçados",
        "Bolsas",
        "Moda íntima",
        "Peças sob medida",
      ],
      tipo: "produtos",
    },
    {
      id: "presentes",
      t: "Presentes e artesanato",
      d: "Peças feitas à mão",
      o: [
        "Presentes personalizados",
        "Velas e aromas",
        "Artesanato",
        "Papelaria",
        "Decoração",
        "Cestas e kits",
      ],
      tipo: "produtos",
    },
    {
      id: "casa",
      t: "Casa, reparos e limpeza",
      d: "Pequenas obras e serviços",
      o: [
        "Reparos e pequenas obras",
        "Elétrica",
        "Pintura",
        "Limpeza",
        "Jardinagem",
        "Montagem de móveis",
      ],
      tipo: "servicos",
    },
    {
      id: "saude",
      t: "Saúde e bem-estar",
      d: "Treino, terapias, cuidados",
      o: [
        "Atendimento individual",
        "Pilates e treino",
        "Nutrição",
        "Terapias",
        "Cuidados com pets",
        "Massagem relaxante",
      ],
      tipo: "servicos",
    },
    {
      id: "educacao",
      t: "Educação e aulas",
      d: "Aulas, cursos, mentorias",
      o: [
        "Aulas particulares",
        "Reforço escolar",
        "Idiomas",
        "Cursos e oficinas",
        "Mentorias",
        "Material didático",
      ],
      tipo: "servicos",
    },
    {
      id: "eventos",
      t: "Festas e eventos",
      d: "Foto, decoração, buffet",
      o: [
        "Fotografia",
        "Filmagem",
        "Decoração de festas",
        "Buffet",
        "Som e DJ",
        "Convites e lembranças",
      ],
      tipo: "ambos",
    },
    {
      id: "loja",
      t: "Loja e revenda",
      d: "Vender produtos de outras marcas",
      o: [
        "Revenda de produtos",
        "Cosméticos",
        "Eletrônicos e acessórios",
        "Produtos naturais",
        "Utilidades domésticas",
        "Brinquedos",
      ],
      tipo: "produtos",
    },
    {
      id: "digital",
      t: "Serviços digitais",
      d: "Design, redes, sites",
      o: [
        "Design e artes",
        "Gestão de redes sociais",
        "Sites e lojas virtuais",
        "Textos e revisão",
        "Edição de vídeo",
        "Consultoria",
      ],
      tipo: "servicos",
    },
    {
      id: "outra",
      t: "Outra atividade",
      d: "Conte com suas palavras",
      o: [
        "Produtos",
        "Serviços",
        "Encomendas",
        "Atendimento com hora marcada",
        "Entregas",
        "Assinaturas e planos",
      ],
      tipo: "ambos",
    },
  ];
  var ROTINA = [
    "Responder clientes no WhatsApp",
    "Responder no Instagram",
    "Enviar orçamentos",
    "Cobrar pagamentos",
    "Controlar estoque",
    "Agendar atendimentos",
    "Divulgar nas redes sociais",
    "Fazer entregas",
    "Fazer pós-venda e lembrar clientes",
    "Anotar o que entra e sai",
  ];
  var FOCOS = [
    {
      id: "atender",
      t: "Responder clientes melhor",
      d: "Conversas e histórico num só lugar",
      nav: "Caixa Unificada",
    },
    {
      id: "vendas",
      t: "Organizar vendas",
      d: "Pedidos, pagamentos e oportunidades",
      nav: "Negócio",
    },
    {
      id: "dinheiro",
      t: "Controlar o dinheiro",
      d: "O que entra, o que sai e o saldo",
      nav: "Relatórios",
    },
    {
      id: "divulgar",
      t: "Divulgar mais",
      d: "Stories, posts e Reels com ajuda",
      nav: "Divulgação",
    },
  ];
  var CORES = [
    ["", "Azul", "#0a5cf5"],
    ["v", "Verde", "#0e7a43"],
    ["r", "Roxo", "#6a46d9"],
    ["k", "Rosa", "#c2185b"],
    ["l", "Laranja", "#a64a08"],
    ["g", "Grafite", "#334155"],
  ];
  var PASSOS = ["Seu negócio", "Suas ofertas", "Sua rotina", "Seu começo", "Revisão"];
  var obEstado = null,
    passo = 0;

  /* v22: o ramo escolhido no topo do site já vem marcado aqui (e o tipo, se a área sugere um) */
  function ramoGuardado() {
    var v = lg("smei-ramo");
    return AREAS.some(function (a) {
      return a.id === v;
    })
      ? v
      : "";
  }
  function novoEstado() {
    var ar = perfil.areaId || ramoGuardado(),
      a0 = AREAS.filter(function (x) {
        return x.id === ar;
      })[0];
    return {
      nome: perfil.nome || "",
      negocio: perfil.negocio || "",
      area: ar,
      tipo: perfil.tipo || (a0 ? a0.tipo : ""),
      cidade: perfil.cidade || "",
      insta: perfil.instagram || "",
      ofertas: perfil.ofertas || [],
      rotina: perfil.rotina || [],
      canais: perfil.canais || ["WhatsApp", "Instagram"],
      foco: perfil.foco || "",
      cor: lg("smei-brand") || "",
    };
  }
  function iniciarOb() {
    if (!obEstado) {
      obEstado = (json(RASCUNHO) && json(RASCUNHO).e) || novoEstado();
      passo = (json(RASCUNHO) && json(RASCUNHO).p) || 0;
    }
    desenharOb();
    var pv = $(".side .pvc"); /* v21: o painel entra suave, uma vez por abertura */
    if (pv) {
      pv.classList.remove("in");
      void pv.offsetWidth;
      pv.classList.add("in");
    }
  }
  function guardarRascunho() {
    ls(RASCUNHO, JSON.stringify({ e: obEstado, p: passo }));
  }
  var area = function () {
    return AREAS.filter(function (a) {
      return a.id === obEstado.area;
    })[0];
  };
  var inic = function (s) {
    var p = String(s || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    return ((p[0] || "S")[0] + (p[1] ? p[1][0] : (p[0] || "M")[1] || "M")).toUpperCase();
  };

  function desenharOb() {
    $("#stepper").innerHTML = PASSOS.map(function (t, k) {
      return (
        '<li class="' +
        (k === passo ? "on" : k < passo ? "done" : "") +
        '"' +
        (k === passo ? ' aria-current="step"' : "") +
        "><b>" +
        (k < passo ? ico("check", 13, 3) : k + 1) +
        "</b><span>" +
        t +
        "</span></li>"
      );
    }).join("");
    $("#obBar").style.width = (passo / (PASSOS.length - 1)) * 100 + "%";
    var h = [passo0, passo1, passo2, passo3, passo4][passo]();
    var ult = passo === PASSOS.length - 1;
    $("#obCard").innerHTML =
      '<div class="ob-step">' +
      h +
      '<div class="ob-n">' +
      (passo > 0
        ? '<button class="btn o" type="button" data-ob="voltar">' +
          ico("back", 18) +
          "Voltar</button>"
        : "") +
      '<button class="btn q sp" type="button" data-ob="pular">Pular por enquanto</button><button class="btn" type="button" data-ob="' +
      (ult ? "fim" : "prox") +
      '">' +
      (ult ? "Entrar no meu espaço" : "Continuar") +
      ico("arrow", 18) +
      "</button></div></div>";
    if (ult) $("#obCard .sp").hidden = true;
    sincronizar();
  }
  function passo0() {
    var e = obEstado;
    return (
      '<span class="chip">Etapa 1 de 5</span><h1 style="margin-top:12px">Vamos conhecer seu negócio</h1><p class="m">Assim o app combina com o seu dia a dia. Você pode mudar tudo depois.</p>' +
      '<div class="fld"><label for="oNome">Seu nome</label><input class="in" id="oNome" value="' +
      esc(e.nome) +
      '" autocomplete="name"><div class="err" id="eoNome" role="alert"></div></div>' +
      '<div class="fld"><label for="oNeg">Nome do negócio</label><input class="in" id="oNeg" value="' +
      esc(e.negocio) +
      '" placeholder="Ex.: Loja da Maria" autocomplete="organization"><div class="err" id="eoNeg" role="alert"></div></div>' +
      '<div class="fld"><span class="lab" id="lArea">Em qual área você trabalha?</span><div class="opts" role="radiogroup" aria-labelledby="lArea">' +
      AREAS.map(function (a) {
        return (
          '<button type="button" class="opt rd" role="radio" aria-checked="' +
          (e.area === a.id) +
          '" data-area="' +
          a.id +
          '"><span class="ck">' +
          ico("check", 13, 3) +
          "</span><span>" +
          a.t +
          "<small>" +
          a.d +
          "</small></span></button>"
        );
      }).join("") +
      '</div><div class="err" id="eoArea" role="alert"></div></div>' +
      '<div class="fld"><span class="lab" id="lTipo">Você trabalha com…</span><div class="opts" role="radiogroup" aria-labelledby="lTipo">' +
      [
        ["produtos", "Produtos"],
        ["servicos", "Serviços"],
        ["ambos", "Os dois"],
      ]
        .map(function (t) {
          return (
            '<button type="button" class="opt rd" role="radio" aria-checked="' +
            (e.tipo === t[0]) +
            '" data-tipo="' +
            t[0] +
            '"><span class="ck">' +
            ico("check", 13, 3) +
            "</span>" +
            t[1] +
            "</button>"
          );
        })
        .join("") +
      "</div></div>" +
      '<div class="fld"><label for="oCid">Cidade <small>(opcional)</small></label><input class="in" id="oCid" value="' +
      esc(e.cidade) +
      '" autocomplete="address-level2"></div>' +
      '<div class="fld"><label for="oIg">Instagram do negócio <small>(opcional, só para a prévia)</small></label><input class="in" id="oIg" value="' +
      esc(e.insta) +
      '" placeholder="@seunegocio" autocapitalize="none"></div>'
    );
  }
  function passo1() {
    var a = area(),
      lista = a ? a.o : AREAS[10].o;
    return (
      '<span class="chip">Etapa 2 de 5</span><h1 style="margin-top:12px">O que você faz bem?</h1><p class="m">Marque o que você vende ou faz' +
      (a ? " em <b>" + esc(a.t) + "</b>" : "") +
      ". São só sugestões para o seu perfil: nenhum produto é cadastrado sozinho.</p>" +
      '<div class="opts" role="group" aria-label="Suas ofertas">' +
      lista
        .map(function (o) {
          return (
            '<button type="button" class="opt" aria-pressed="' +
            (obEstado.ofertas.indexOf(o) > -1) +
            '" data-of="' +
            esc(o) +
            '"><span class="ck">' +
            ico("check", 13, 3) +
            "</span>" +
            esc(o) +
            "</button>"
          );
        })
        .join("") +
      "</div>" +
      '<div class="fld"><label for="oOutro">Outra coisa que você faz <small>(opcional, aperte Enter para adicionar)</small></label><input class="in" id="oOutro" placeholder="Ex.: Lembrancinhas de casamento"></div>' +
      '<div class="opts" id="extras">' +
      obEstado.ofertas
        .filter(function (o) {
          return lista.indexOf(o) < 0;
        })
        .map(function (o) {
          return (
            '<button type="button" class="opt" aria-pressed="true" data-of="' +
            esc(o) +
            '"><span class="ck">' +
            ico("check", 13, 3) +
            "</span>" +
            esc(o) +
            "</button>"
          );
        })
        .join("") +
      "</div>"
    );
  }
  function passo2() {
    return (
      '<span class="chip">Etapa 3 de 5</span><h1 style="margin-top:12px">Como é a sua rotina?</h1><p class="m">Marque o que faz parte do seu dia. O app destaca o que combina com você. Nada é criado automaticamente.</p>' +
      '<div class="opts" role="group" aria-label="Sua rotina">' +
      ROTINA.map(function (o) {
        return (
          '<button type="button" class="opt" aria-pressed="' +
          (obEstado.rotina.indexOf(o) > -1) +
          '" data-ro="' +
          esc(o) +
          '"><span class="ck">' +
          ico("check", 13, 3) +
          "</span>" +
          esc(o) +
          "</button>"
        );
      }).join("") +
      "</div>"
    );
  }
  function passo3() {
    return (
      '<span class="chip">Etapa 4 de 5</span><h1 style="margin-top:12px">Por onde você quer começar?</h1><p class="m">Seu espaço começa a ganhar forma. Você muda tudo depois em Configurações.</p>' +
      '<div class="fld"><span class="lab" id="lFoco">Qual é sua maior prioridade agora?</span><div class="opts" role="radiogroup" aria-labelledby="lFoco">' +
      FOCOS.map(function (f) {
        return (
          '<button type="button" class="opt rd" role="radio" aria-checked="' +
          (obEstado.foco === f.id) +
          '" data-foco="' +
          f.id +
          '"><span class="ck">' +
          ico("check", 13, 3) +
          "</span><span>" +
          f.t +
          "<small>" +
          f.d +
          "</small></span></button>"
        );
      }).join("") +
      "</div></div>" +
      '<div class="fld"><span class="lab" id="lCan">Canais de interesse <small>· nenhuma conexão é feita agora</small></span><div class="opts" role="group" aria-labelledby="lCan">' +
      [
        ["WhatsApp", "Conversas, pedidos e retornos"],
        ["Instagram", "Direct, comentários e novos contatos"],
      ]
        .map(function (c) {
          return (
            '<button type="button" class="opt" aria-pressed="' +
            (obEstado.canais.indexOf(c[0]) > -1) +
            '" data-can="' +
            c[0] +
            '"><span class="ck">' +
            ico("check", 13, 3) +
            "</span><span>" +
            c[0] +
            "<small>" +
            c[1] +
            "</small></span></button>"
          );
        })
        .join("") +
      "</div></div>" +
      '<div class="fld"><span class="lab" id="lCor">Cor da sua marca</span><div class="swatches" role="radiogroup" aria-labelledby="lCor">' +
      CORES.map(function (c) {
        return (
          '<button type="button" class="sw" role="radio" aria-checked="' +
          (obEstado.cor === c[0]) +
          '" aria-label="' +
          c[1] +
          '" title="' +
          c[1] +
          '" data-cor="' +
          c[0] +
          '" style="background:' +
          c[2] +
          '">' +
          ico("check", 20, 3) +
          "</button>"
        );
      }).join("") +
      "</div></div>"
    );
  }
  function passo4() {
    var e = obEstado,
      a = area(),
      f = FOCOS.filter(function (x) {
        return x.id === e.foco;
      })[0];
    var L = function (t, v, k) {
      return (
        '<div class="rev-r"><div><small>' +
        t +
        "</small><b>" +
        (v || '<span class="m">Não informado</span>') +
        '</b></div><button class="lk" type="button" data-ir="' +
        k +
        '">Editar<span class="sr"> ' +
        t +
        "</span></button></div>"
      );
    };
    return (
      '<span class="chip g">Etapa 5 de 5</span><h1 style="margin-top:12px">Seu negócio está quase pronto</h1><p class="m">Confira suas escolhas. Você pode editar qualquer uma antes de entrar.</p><div class="rev">' +
      L("Você", esc(e.nome) + (perfil.email ? " · " + esc(perfil.email) : ""), 0) +
      L(
        "Negócio",
        esc(e.negocio) + (a ? " · " + esc(a.t) : "") + (e.cidade ? " · " + esc(e.cidade) : ""),
        0,
      ) +
      L("Ofertas", e.ofertas.map(esc).join(", "), 1) +
      L("Rotina", e.rotina.map(esc).join(", "), 2) +
      L("Primeiro foco", f ? f.t : "", 3) +
      L("Canais de interesse", e.canais.join(", ") + " · nenhuma conexão é feita", 3) +
      "</div>" +
      '<div class="pxb" style="margin-top:18px">' +
      ico("info", 18, 1.8) +
      "<span>Ao entrar, salvamos este perfil só neste navegador. Isso não cadastra produtos, vendas ou conexões.</span></div>"
    );
  }

  function sincronizar() {
    /* prévia lateral e rascunho */
    var e = obEstado,
      f = FOCOS.filter(function (x) {
        return x.id === e.foco;
      })[0],
      a = area();
    var cor = (CORES.filter(function (c) {
      return c[0] === e.cor;
    })[0] || CORES[0])[2];
    document.documentElement.style.setProperty("--brand", cor);
    $("#sIni").textContent = inic(e.negocio || "Meu negócio");
    $("#sNome").textContent = e.negocio || "Seu negócio";
    $("#sSeg").textContent = a ? a.t : "Conte o que você faz";
    var nav = [
      ["Início", "home"],
      ["Caixa Unificada", "chat"],
      ["Negócio", "store"],
      ["Relatórios", "bars"],
      ["Divulgação", "mega"],
    ];
    $("#sNav").innerHTML = nav
      .map(function (n) {
        return (
          '<div class="' +
          ((f && f.nav === n[0]) || (!f && n[0] === "Início") ? "on" : "") +
          '">' +
          ico(n[1], 18, 1.8) +
          n[0] +
          "</div>"
        );
      })
      .join("");
    $("#sTags").innerHTML =
      e.ofertas
        .slice(0, 4)
        .map(function (o) {
          return '<span class="chip">' + esc(o) + "</span>";
        })
        .join("") +
      (e.ofertas.length > 4 ? '<span class="chip">+' + (e.ofertas.length - 4) + "</span>" : "") +
      e.canais
        .map(function (c) {
          return '<span class="chip y">' + c + "</span>";
        })
        .join("");
    if (passo === 0) {
      marca("oNome", e.nome.trim().length >= 2);
      marca("oNeg", e.negocio.trim().length >= 2);
    } /* v21: mesmo ✓ do cadastro */
    guardarRascunho();
  }
  function lerPasso0() {
    var e = obEstado;
    e.nome = ($("#oNome") || {}).value || e.nome;
    e.negocio = ($("#oNeg") || {}).value || "";
    e.cidade = ($("#oCid") || {}).value || "";
    e.insta = ($("#oIg") || {}).value || "";
  }
  function validarPasso() {
    if (passo !== 0) return true;
    lerPasso0();
    var e = obEstado,
      bad = [];
    if (erro("eoNome", e.nome.trim().length < 2 ? "Como podemos te chamar?" : "", "oNome"))
      bad.push("oNome");
    if (erro("eoNeg", e.negocio.trim().length < 2 ? "Qual o nome do seu negócio?" : "", "oNeg"))
      bad.push("oNeg");
    if (erro("eoArea", e.area ? "" : "Escolha a área que mais combina com você.")) bad.push(null);
    if (bad.length) {
      var f = bad[0] ? document.getElementById(bad[0]) : $("[data-area]");
      f && f.focus();
      return false;
    }
    return true;
  }
  function alternar(lista, v) {
    var i = lista.indexOf(v);
    i > -1 ? lista.splice(i, 1) : lista.push(v);
  }
  $("#obCard").addEventListener("click", function (ev) {
    var b = ev.target.closest("button");
    if (!b) return;
    var e = obEstado;
    if (b.dataset.area) {
      e.area = b.dataset.area;
      var a = area();
      if (!e.tipo) e.tipo = a.tipo;
      e.ofertas = [];
      lerPasso0();
      desenharOb();
      $('[data-area="' + e.area + '"]').focus();
      return;
    }
    if (b.dataset.tipo) {
      e.tipo = b.dataset.tipo;
      lerPasso0();
      desenharOb();
      $('[data-tipo="' + e.tipo + '"]').focus();
      return;
    }
    if (b.dataset.of != null) {
      alternar(e.ofertas, b.dataset.of);
      var k = b.dataset.of;
      desenharOb();
      var n = $$("[data-of]").filter(function (x) {
        return x.dataset.of === k;
      })[0];
      n && n.focus();
      return;
    }
    if (b.dataset.ro != null) {
      alternar(e.rotina, b.dataset.ro);
      b.setAttribute("aria-pressed", e.rotina.indexOf(b.dataset.ro) > -1);
      sincronizar();
      return;
    }
    if (b.dataset.foco) {
      e.foco = b.dataset.foco;
      $$("[data-foco]").forEach(function (x) {
        x.setAttribute("aria-checked", x === b);
      });
      sincronizar();
      return;
    }
    if (b.dataset.can) {
      alternar(e.canais, b.dataset.can);
      b.setAttribute("aria-pressed", e.canais.indexOf(b.dataset.can) > -1);
      sincronizar();
      return;
    }
    if (b.dataset.cor != null) {
      e.cor = b.dataset.cor;
      $$("[data-cor]").forEach(function (x) {
        x.setAttribute("aria-checked", x === b);
      });
      sincronizar();
      return;
    }
    if (b.dataset.ir) {
      passo = +b.dataset.ir;
      desenharOb();
      $("#obMain").focus({ preventScroll: true });
      return;
    }
    var ac = b.dataset.ob;
    if (!ac) return;
    if (ac === "voltar") {
      if (passo === 0) lerPasso0();
      passo--;
      desenharOb();
      mover();
    } else if (ac === "prox") {
      if (!validarPasso()) return;
      passo++;
      desenharOb();
      mover();
    } else if (ac === "pular") {
      if (passo === 0) {
        lerPasso0();
        if (obEstado.nome.trim().length < 2) {
          validarPasso();
          return;
        }
      }
      passo === PASSOS.length - 1 ? finalizar() : (passo++, desenharOb(), mover());
    } else if (ac === "fim") ocupado(b, "Salvando seu espaço…", finalizar);
  });
  /* v21: o botão final mostra o que está acontecendo antes de seguir (sem espera no modo calmo) */
  function ocupado(b, texto, fn) {
    if (b.disabled) return;
    if (calmo()) {
      b.disabled = true;
      Promise.resolve(fn()).finally(function () {
        b.disabled = false;
      });
      return;
    }
    var h = b.innerHTML;
    b.classList.add("busy");
    b.setAttribute("aria-busy", "true");
    b.disabled = true;
    b.textContent = texto;
    setTimeout(function () {
      Promise.resolve(fn()).finally(function () {
        b.classList.remove("busy");
        b.removeAttribute("aria-busy");
        b.disabled = false;
        b.innerHTML = h;
      });
    }, 550);
  }
  function mover() {
    $("#obMain").focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }
  $("#obCard").addEventListener("input", function (e) {
    if (passo === 0) {
      lerPasso0();
      sincronizar();
      limpar(e.target);
    }
  });
  $("#obCard").addEventListener("keydown", function (e) {
    if (e.target.id === "oOutro" && e.key === "Enter") {
      e.preventDefault();
      var v = e.target.value.trim();
      if (!v) return;
      if (obEstado.ofertas.indexOf(v) < 0) obEstado.ofertas.push(v);
      desenharOb();
      $("#oOutro").focus();
    }
    var g = e.target.closest && e.target.closest("[role=radiogroup]");
    if (
      g &&
      (e.key === "ArrowRight" ||
        e.key === "ArrowDown" ||
        e.key === "ArrowLeft" ||
        e.key === "ArrowUp")
    ) {
      var rs = $$("[role=radio]", g),
        i = rs.indexOf(e.target);
      if (i < 0) return;
      e.preventDefault();
      var n =
        rs[
          (i + (e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1) + rs.length) % rs.length
        ];
      n.focus();
      n.click();
    }
  });

  async function finalizar() {
    var e = obEstado,
      a = area();
    if (remote) {
      if (!e.negocio.trim() || !e.nome.trim()) {
        passo = 0;
        desenharOb();
        validarPasso();
        return;
      }
      try {
        await account.ready;
        await account.saveOnboarding(
          Object.assign({}, e, { areaLabel: a ? a.t : "", originalArea: remoteAreaAtLoad }),
          remoteRevision,
          remoteProfile,
        );
      } catch (error) {
        toast(error.message || "Não foi possível salvar. Suas respostas foram preservadas.");
        return;
      }
    }
    if (!e.negocio.trim()) e.negocio = "Meu negócio";
    salvarPerfil({
      nome: e.nome.trim(),
      negocio: e.negocio.trim(),
      areaId: e.area,
      area: a ? a.t : "",
      tipo: e.tipo,
      cidade: e.cidade.trim(),
      instagram: e.insta.trim(),
      ofertas: e.ofertas,
      rotina: e.rotina,
      canais: e.canais,
      foco: e.foco,
      onboarding: true,
    });
    ls("smei-brand", e.cor || null);
    aplicarMarca();
    if (!remote) ls(SESSAO, "1");
    ls(RASCUNHO, null);
    var nome = esc(e.nome.split(/\s+/)[0]);
    var el = document.createElement("div");
    el.className = "fin";
    el.setAttribute("role", "status");
    el.innerHTML =
      '<div><img class="logo-c" src="assets/logo-socialmei.png" alt=""><h1 style="font-size:30px">Tudo certo, ' +
      nome +
      '!</h1><p class="m">Estamos arrumando o seu espaço.</p><ul>' +
      [
        "Preparando o " + esc(e.negocio),
        "Deixando tudo com a sua cor",
        "Separando seus primeiros passos",
      ]
        .map(function (t) {
          return "<li>" + ico("check", 20, 2.6) + "<span>" + t + "</span></li>";
        })
        .join("") +
      '</ul><div class="spn" aria-hidden="true"></div></div>';
    document.body.appendChild(el);
    var lis = $$("li", el),
      rap = calmo(),
      pass = rap ? 60 : 650;
    lis.forEach(function (l, k) {
      setTimeout(
        function () {
          l.classList.add("on");
        },
        pass * (k + 1),
      );
    });
    setTimeout(
      function () {
        location.href = "socialmei-app.html#/bemvindo";
      },
      pass * (lis.length + 1) + (rap ? 60 : 300),
    );
  }

  if (remote)
    account.ready.then(async function () {
      try {
        var policy = await account.auth.request("/auth/registration");
        if (policy.mode === "invite" && !$("#cInvite")) {
          var field = document.createElement("div");
          field.className = "fld";
          field.innerHTML =
            '<label for="cInvite">Código do convite</label><input class="in" id="cInvite" minlength="64" maxlength="64" autocomplete="off"><p class="hint">Use o convite recebido do administrador.</p>';
          $("#fC [type=submit]").before(field);
        }
      } catch (error) {
        $("#forgotMsg").textContent = error.message;
      }
      var user = account.auth.current;
      if (user) {
        perfil = {
          nome: user.usuario.nome,
          email: user.usuario.email,
          tel: user.usuario.telefone || "",
          negocio: user.negocio.nome,
        };
        try {
          var packet = await account.loadProfile();
          remoteRevision = packet.revision;
          remoteProfile = packet.profile;
          if (packet.profile) {
            var p = packet.profile;
            perfil.rotina = [];
            [
              ["appointments", "Agendar atendimentos"],
              ["quotes", "Enviar orçamentos"],
              ["deliveries", "Fazer entregas"],
              ["inventory", "Controlar estoque"],
            ].forEach(function (pair) {
              if (p.capabilities[pair[0]]) perfil.rotina.push(pair[1]);
            });
            perfil.tipo =
              p.offers.length === 2
                ? "ambos"
                : p.offers[0] === "services"
                  ? "servicos"
                  : "produtos";
            perfil.ofertas = p.services.concat(
              p.productCategories.filter(function (x) {
                return p.services.indexOf(x) === -1;
              }),
            );
            perfil.areaId = account.areaForSegment(p.segment);
            remoteAreaAtLoad = perfil.areaId;
          }
        } catch (error) {
          toast(error.message || "Não foi possível carregar o perfil.");
        }
      }
      authSettled = true;
      obEstado = null;
      router(false);
    });

  // Production uses authenticated PostgreSQL accounts. Demo copy remains only
  // in the deliberately disconnected local/browser demonstration.
  function atualizarTextosDeContaReal() {
    if (!remote) return;
    var trocar = function (selector, value) {
      var el = $(selector);
      if (el) el.textContent = value;
    };
    trocar(
      '#panC .pxb span',
      'Sua conta e seu negócio são criados de verdade. A senha é protegida no servidor.',
    );
    trocar(
      '#panE .pxb span',
      'Entre com o e-mail e a senha da sua conta real no SocialMEI.',
    );
    trocar('.hero-top .badge',
      'Contas e dados de negócio armazenados com segurança');
    var description = $('meta[name="description"]');
    if (description) description.setAttribute('content',
      'Conversas, clientes e vendas organizados para o seu negócio.');
    trocar('#demo .sub',
      'Explore uma prévia ilustrativa. Ao criar sua conta, seus dados são salvos no seu espaço.');
    trocar('.foot-n',
      'As prévias exibidas são exemplos; cada conta real possui seu espaço privado.');
    var exemplo = $(
      '#panC .chk span.m'
    );
    if (exemplo) exemplo.textContent = '(documentos sujeitos à revisão antes do lançamento público)';
    var acesso = $(
      '#demo a[href="#/cadastro"]'
    );
    if (acesso) acesso.textContent = 'Criar conta real';
    var button = $('[data-demo-app]');
    if (button) button.textContent = 'Entrar para experimentar';
  }

  /* ---------- início ---------- */
  atualizarTextosDeContaReal();
  aplicarTema();
  aplicarCalmo();
  aplicarMarca();
  pintarChat(0, false);
  agendarChat();
  revelar();
  router(true);
  /* se o modo calmo mudar, para ou retoma a prévia animada */
  new MutationObserver(function () {
    agendarChat();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
})();
