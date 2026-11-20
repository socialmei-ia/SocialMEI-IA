/* SocialMEI-IA · v6.5 · Casca do app: marca, título da aba e barra lateral que "espia" ao passar o mouse.
   - Barra recolhida: ao parar o mouse sobre ela (≈350 ms) ou focar com o teclado, expande por cima da página
     SEM empurrar o conteúdo; sai ao tirar o mouse/foco. Não roda em toque nem com movimento reduzido no hover.
   - Marca: ícone no topo no celular (onde a logo lateral não aparece) e frase curta na logo expandida.
   - O título da aba é fixo e curto ("SocialMEI-IA | Seu negócio, mais simples"), definido no HTML. */
(function () {
  "use strict";
  var app = document.getElementById("app");
  if (!app) return;
  var fine = matchMedia("(hover:hover) and (pointer:fine)");
  var timer = 0,
    peeked = null;

  function open(a) {
    if (!a || !a.classList.contains("col") || a.classList.contains("peek")) return;
    a.classList.remove("col");
    a.classList.add("peek");
    a.dataset.peek = "1";
    peeked = a;
  }
  function close() {
    clearTimeout(timer);
    if (peeked && peeked.dataset.peek) {
      peeked.classList.remove("peek");
      peeked.classList.add("col");
      delete peeked.dataset.peek;
    }
    peeked = null;
  }
  function asideOf(t) {
    return t && t.closest ? t.closest("aside") : null;
  }
  app.addEventListener("mouseover", function (e) {
    if (!fine.matches || innerWidth <= 900) return;
    var a = asideOf(e.target);
    if (!a || !a.classList.contains("col")) return;
    if (!timer)
      timer = setTimeout(function () {
        timer = 0;
        open(a);
      }, 350);
  });
  app.addEventListener("mouseout", function (e) {
    var a = asideOf(e.target);
    if (!a) return;
    if (e.relatedTarget && a.contains(e.relatedTarget)) return;
    clearTimeout(timer);
    timer = 0;
    close();
  });
  app.addEventListener("focusin", function (e) {
    var a = asideOf(e.target);
    if (a && innerWidth > 900 && e.target.matches && e.target.matches(":focus-visible")) open(a);
  });
  app.addEventListener("focusout", function (e) {
    var a = asideOf(e.target);
    if (a && !(e.relatedTarget && a.contains(e.relatedTarget))) close();
  });
  app.addEventListener("click", function (e) {
    if (asideOf(e.target) && e.target.closest("a.nv")) close();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") close();
  });

  function paint() {
    var top = app.querySelector(".top");
    if (top && !top.querySelector(".top-mark")) {
      var m = new Image();
      m.className = "top-mark";
      m.src = "assets/icon-192.png";
      m.alt = "";
      m.width = 26;
      m.height = 26;
      m.setAttribute("aria-hidden", "true");
      top.insertBefore(m, top.firstChild);
    }
    var lg = app.querySelector("aside .logo-l");
    if (lg && !lg.querySelector(".logo-tag")) {
      var s = document.createElement("span");
      s.className = "logo-tag";
      s.textContent = "Seu negócio, mais simples";
      lg.appendChild(s);
    }
  }
  var raf = 0;
  new MutationObserver(function () {
    if (!raf)
      raf = requestAnimationFrame(function () {
        raf = 0;
        paint();
      });
  }).observe(app, { childList: true, subtree: true });
  /* ---------- aviso global de conexão (qualquer tela) ---------- */
  var ob = null,
    obT = 0;
  function net() {
    var off = navigator.onLine === false;
    if (off && !ob) {
      clearTimeout(obT);
      ob = document.createElement("div");
      ob.className = "sm-off";
      ob.setAttribute("role", "status");
      ob.textContent =
        "Sem conexão com a internet. O que depende do servidor pode não ser salvo até a conexão voltar.";
      document.body.appendChild(ob);
    } else if (!off && ob) {
      var o = ob;
      ob = null;
      o.classList.add("ok");
      o.textContent = "Conexão restabelecida.";
      obT = setTimeout(function () {
        o.remove();
      }, 2600);
    }
  }
  addEventListener("offline", net);
  addEventListener("online", net);
  net();
  /* ---------- "?" abre a lista de atalhos ---------- */
  var KEYS = [
    ["Ctrl K", "Busca e ações rápidas em todo o app"],
    ["/", "Buscar conversa (na Caixa)"],
    ["Alt ↑ ↓", "Conversa anterior / seguinte"],
    ["Ctrl Enter", "Salvar a resposta escrita"],
    ["Esc", "Fechar menus e painéis abertos"],
    ["?", "Mostrar esta lista"],
  ];
  document.addEventListener("keydown", function (e) {
    if (e.key !== "?" || e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target;
    if (t && (/^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable)) return;
    if (document.querySelector("dialog.sm-keys[open]")) return;
    e.preventDefault();
    var d = document.createElement("dialog");
    d.className = "sm-keys";
    d.setAttribute("aria-labelledby", "sm-keys-h");
    var h = document.createElement("h2");
    h.id = "sm-keys-h";
    h.textContent = "Atalhos do teclado";
    d.appendChild(h);
    var ul = document.createElement("ul");
    KEYS.forEach(function (k) {
      var li = document.createElement("li"),
        kb = document.createElement("span"),
        tx = document.createElement("span");
      k[0].split(" ").forEach(function (part, i) {
        if (part === "/" && i && k[0].indexOf("Alt") > -1) {
          var s = document.createElement("i");
          s.textContent = "ou";
          kb.appendChild(s);
          return;
        }
        var c = document.createElement("kbd");
        c.textContent = part;
        kb.appendChild(c);
      });
      tx.textContent = k[1];
      li.append(kb, tx);
      ul.appendChild(li);
    });
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn o";
    b.textContent = "Fechar";
    b.addEventListener("click", function () {
      d.close();
    });
    d.append(ul, b);
    document.body.appendChild(d);
    d.addEventListener("close", function () {
      d.remove();
    });
    if (d.showModal) d.showModal();
    else d.setAttribute("open", "");
    b.focus();
  });
  paint();
})();
