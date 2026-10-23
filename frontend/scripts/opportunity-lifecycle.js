/* Exact V8 composition; the authenticated commercial store remains the only CRM writer. */
document.addEventListener("DOMContentLoaded", () => {
  "use strict";
  const api = SocialMEIOpportunityLifecycle,
    auth = SocialMEIAuth;
  const page = document.getElementById("opportunitiesView");
  const legacy = page?.querySelector(":scope > .management-stack");
  if (!page || !legacy) return;
  const oldTitle = document.getElementById("opportunitiesTitle");
  if (oldTitle) {
    oldTitle.id = "opportunityMessagesTitle";
    oldTitle.textContent = "Análise de mensagens";
  }
  const root = document.createElement("section");
  root.id = "opportunityLifecycle";
  root.className = "exact-v8";
  root.setAttribute("aria-label", "Acompanhamento comercial");
  root.innerHTML = SocialMEIOpportunityV8View.markup;
  const analysis = document.createElement("details");
  analysis.className = "native-message-analysis";
  analysis.id = "opportunityMessageAnalysis";
  const summary = document.createElement("summary");
  summary.textContent = "Análise de mensagens e revisão humana";
  analysis.append(summary);
  legacy.before(root, analysis);
  analysis.append(legacy);
  // Original viewport typography follows the available native canvas, excluding the sidebar.
  const sizeCanvas = () => {
    const width = root.getBoundingClientRect().width;
    if (width) root.style.setProperty("--v8-vw", width / 100 + "px");
  };
  new ResizeObserver(sizeCanvas).observe(root);
  sizeCanvas();
  const nativeIds = {
    form: "opportunityCreateForm",
    client: "opportunityClient",
    what: "opportunityTitle",
    interest: "opportunityInterest",
    list: "commercialOpportunityList",
  };
  const $ = (id) => root.querySelector("#" + CSS.escape(nativeIds[id] || "v8-" + id));
  const IL = {
      analysis: ["Em análise", 0],
      cold: ["Frio", 1],
      warm: ["Morno", 2],
      hot: ["Quente", 3],
    },
    IK = Object.keys(IL);
  const FL = [
    ["open", "Em andamento"],
    ["analysis", "Em análise"],
    ["cold", "Frio"],
    ["warm", "Morno"],
    ["hot", "Quente"],
    ["won", "Venda realizada"],
    ["lost", "Não avançou"],
  ];
  const DAY = 864e5,
    now = Date.now;
  const BRL = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  const S = {
    items: [],
    f: "open",
    q: "",
    s: "rec",
    x: {},
    nw: null,
    v: "list",
    sel: null,
    scope: null,
    loaded: false,
    histories: {},
  };
  const store = api.createStore({
    identity: () => auth.current,
    headers: () => ({ "X-SocialMEI-Client": "browser", ...auth.headers() }),
    origin: location.origin,
    fetch: (...args) => fetch(...args),
    change: controls,
  });
  const planning = SocialMEIOpportunityV8Planning.createRepository({
    scope: () => store.snapshot().scope,
    writable: () => writable(),
    exists: (id) => store.snapshot().items.some((row) => row.id === id),
    storage: {
      getItem: (key) => localStorage.getItem(key),
      setItem: (key, value) => localStorage.setItem(key, value),
    },
  });
  const parseMoney = SocialMEIOpportunityV8Planning.parseMoney;
  const esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
    );
  const ic = (k) => '<svg class="ic" aria-hidden="true"><use href="#v8-i-' + k + '"/></svg>';
  const fdt = (t) =>
    new Date(t).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  const sd = (t) => new Date(t).setHours(0, 0, 0, 0);
  const off = (t) => Math.round((sd(t) - sd(now())) / DAY);
  const rel = (t) => {
    const d = off(t);
    return d === 0
      ? "hoje"
      : d === 1
        ? "amanhã"
        : d === -1
          ? "ontem"
          : d > 1
            ? "em " + d + " dias"
            : "há " + -d + " dias";
  };
  const mny = (value) => (value ? BRL.format(value) : "—");
  const nm = (o) => o.c.replace(/\(.*\)/, "").trim();
  function writable() {
    const s = store.snapshot();
    return auth.remote && s.ready && !s.busy && ["owner", "admin", "member"].includes(s.role);
  }
  function isDue(o) {
    return (
      o.r === "open" && (o.f ? o.f <= now() : now() - Math.max(o.u, o.meta.updatedAt) > 3 * DAY)
    );
  }
  function project() {
    const snapshot = store.snapshot();
    if (S.scope !== snapshot.scope) {
      S.scope = snapshot.scope;
      S.x = {};
      S.sel = null;
      S.q = "";
      S.f = "open";
      S.histories = {};
      S.loaded = false;
      S.v = "list";
      $("form").reset();
      $("q").value = "";
    }
    S.items = snapshot.items.map((row) => {
      const meta = planning.get(row.id),
        date = meta.date ? new Date(meta.date + "T09:00:00").getTime() : null;
      const remote =
        S.histories[row.id]?.revision === row.revision ? S.histories[row.id].events : [];
      return {
        id: row.id,
        c: row.client_name,
        w: row.title,
        i: row.interest_level === "unknown" ? "analysis" : row.interest_level,
        r: row.outcome,
        reason: api.REASONS[row.outcome_reason] || row.outcome_note || "",
        n: meta.note,
        v: meta.amount,
        f: date,
        u: Date.parse(row.updated_at || row.created_at) || 0,
        meta,
        raw: row,
        h: [
          ...remote.map((event) => ({ t: Date.parse(event.created_at), s: eventLabel(event) })),
          ...meta.events.map((event) => ({ ...event, s: event.s + " · somente neste navegador" })),
        ]
          .filter((e) => Number.isFinite(e.t))
          .sort((a, b) => a.t - b.t),
      };
    });
  }
  function eventLabel(event) {
    return [
      {
        create: "Oportunidade criada",
        edit: "Interesse alterado",
        close: "Negociação encerrada",
        reopen: "Oportunidade reaberta",
        sale: "Venda vinculada",
      }[event.action] || "Atualização",
      api.INTEREST[event.current?.interest_level],
      api.OUTCOME[event.current?.outcome],
      api.REASONS[event.reason] || event.reason,
      event.note,
      "Responsável " + (event.actor_id ?? "indisponível"),
      "Revisão " + (event.current?.revision ?? ""),
    ]
      .filter(Boolean)
      .join(" · ");
  }
  function controls() {
    const yes = writable();
    root
      .querySelectorAll(
        '#opportunityCreateForm input,#opportunityCreateForm select,#opportunityCreateForm button,.in input,.in select,.in textarea,.in [data-act]:not([data-act="history"]),.tk,.ch,[data-act="mv"]',
      )
      .forEach((e) => (e.disabled = !yes));
    $("refresh").disabled = !auth.remote || !auth.current || store.snapshot().busy;
    $("refresh").classList.toggle("busy", store.snapshot().busy);
    $("refresh").querySelector("span").textContent = store.snapshot().busy
      ? "Atualizando…"
      : "Atualizar oportunidades";
  }
  const messages = document.createElement("p");
  messages.id = "v8-status";
  messages.className = "mut";
  messages.setAttribute("role", "status");
  messages.setAttribute("aria-live", "polite");
  messages.hidden = true;
  root.querySelector(".foot").before(messages);
  function toast(text, error = false, undo) {
    messages.textContent = text;
    messages.hidden = false;
    const item = document.createElement("div");
    item.className = "t" + (error ? " e" : "");
    const label = document.createElement("span");
    label.textContent = text;
    item.append(label);
    if (undo) {
      const button = document.createElement("button");
      button.className = "link";
      button.textContent = "Desfazer";
      button.onclick = async () => {
        button.disabled = true;
        try {
          await undo();
          item.remove();
        } catch (e) {
          toast(e.message, true);
        } finally {
          button.disabled = false;
        }
      };
      item.append(button);
    }
    $("toast").append(item);
    setTimeout(() => item.remove(), undo ? 6000 : 4000);
  }
  function focusToken() {
    const el = document.activeElement;
    if (!root.contains(el)) return null;
    return {
      id: el.id,
      scope: S.scope,
      kind: el.classList.contains("tk")
        ? "tk"
        : el.classList.contains("ch")
          ? "ch"
          : el.classList.contains("dh")
            ? "day"
            : null,
      col: el.dataset.col,
      row: el.closest("[data-id]")?.dataset.id,
      act: el.dataset.act,
      value: el.dataset.v,
    };
  }
  function restoreFocus(token) {
    if (!token || token.scope !== S.scope) return;
    let target = token.id && root.querySelector("#" + CSS.escape(token.id));
    if (token.kind === "tk" || token.kind === "ch")
      target = root.querySelector("." + token.kind + '[data-id="' + CSS.escape(token.row) + '"]');
    if (token.kind === "day")
      target = root.querySelector('.dh[data-col="' + CSS.escape(token.col) + '"]');
    if (!target && token.row)
      target = root.querySelector(
        '[data-id="' +
          CSS.escape(token.row) +
          '"] [data-act="' +
          CSS.escape(token.act || "tog") +
          '"]' +
          (token.value ? '[data-v="' + CSS.escape(token.value) + '"]' : ""),
      );
    if (!target || target.disabled || !target.getClientRects().length)
      target =
        S.v === "list"
          ? root.querySelector('.fl[aria-pressed="true"]')
          : root.querySelector('.views [aria-pressed="true"]');
    target?.focus({ preventScroll: true });
  }
  async function run(action, text, after, undo) {
    const token = focusToken();
    try {
      const result = await action();
      const note = after?.(result);
      project();
      render();
      restoreFocus(token);
      if (text !== false || note)
        toast(note || text || "Alteração confirmada no negócio atual.", false, undo?.(result));
      return result;
    } catch (error) {
      if (S.scope !== store.snapshot().scope) {
        project();
        render();
      } else controls();
      toast(error.message + " Seus campos foram preservados. Atualize se houver conflito.", true);
      restoreFocus(token);
      return null;
    }
  }
  function localChange(o, patch, text) {
    try {
      const old = planning.get(o.id);
      const receipt = planning.save(o.id, {
        ...patch,
        events: [...old.events, { t: now(), s: text }].slice(-20),
      });
      const token = focusToken();
      project();
      render();
      restoreFocus(token);
      toast(text + " Somente neste navegador.", false, () => {
        planning.undo(receipt);
        project();
        render();
        toast("Planejamento local desfeito.");
      });
      return true;
    } catch (e) {
      toast(e.message, true);
      return false;
    }
  }
  async function setInt(o, key) {
    if (!o || !IL[key] || o.i === key || !writable()) return;
    const old = o.raw.interest_level,
      sourceFocus = focusToken();
    return run(
      () => store.update(o.raw, { interest_level: key === "analysis" ? "unknown" : key }),
      nm(o) + ": " + IL[key][0] + ".",
      () => {
        delete S.histories[o.id];
      },
      (saved) => async () => {
        const current = store.snapshot().items.find((r) => r.id === saved.id);
        if (!current || current.revision !== saved.revision)
          throw new Error("O registro mudou. Atualize antes de desfazer.");
        const result = await run(
          () => store.update(current, { interest_level: old }),
          "Interesse desfeito após confirmação do CRM.",
          () => {
            delete S.histories[o.id];
          },
        );
        if (!result) throw new Error("Não foi possível desfazer no CRM.");
        restoreFocus(sourceFocus);
      },
    );
  }
  function nativeAudit(o) {
    const row = o.raw;
    const choices =
      SocialMEISales.connectionState === "ready"
        ? appData.vendas.filter(
            (s) =>
              s.cliente_id === row.client_id &&
              !s.excluida &&
              ["Pendente", "Pago"].includes(s.status),
          )
        : [];
    const current = row.sale_id
      ? "<p>Venda vinculada: " + esc(row.sale_id) + ". O vínculo não confirma pagamento.</p>"
      : "";
    const unavailable =
      row.sale_unavailable || row.sale_status === "cancelada"
        ? "<p>A venda vinculada foi cancelada ou está indisponível. Confira Vendas; o histórico comercial foi preservado.</p>"
        : "";
    return (
      '<details class="native-audit"><summary>Auditoria e venda vinculada</summary>' +
      current +
      unavailable +
      '<div class="ro"><label for="v8-sale-' +
      esc(o.id) +
      '">Venda já registrada para este cliente</label><select id="v8-sale-' +
      esc(o.id) +
      '"><option value="">Selecione uma venda ativa</option>' +
      choices
        .map(
          (s) =>
            '<option value="' +
            esc(s.id) +
            '">Venda ' +
            esc(s.id) +
            " · " +
            esc(s.item || "Item") +
            " · " +
            esc(s.status) +
            "</option>",
        )
        .join("") +
      '</select><button type="button" class="btn sm" data-act="sale" data-write>Vincular venda existente</button></div><p class="mut">Registre a venda em Vendas antes de vinculá-la. Fechar a oportunidade não altera pagamentos nem estoque.</p><button class="btn sm" type="button" data-act="history">Ver histórico</button><p class="mut" role="status">' +
      (S.histories[o.id]
        ? "Histórico remoto consultado."
        : "Consulte o histórico remoto para conferir responsáveis e revisões.") +
      '</p></details><p class="local-label">Anotação, valor e retorno: planejamento local, não sincronizado.</p>'
    );
  }
  function op(k) {
    return S.items.filter(function (o) {
      return o.r === "open" && (!k || o.i === k);
    });
  }
  function cnt(k) {
    return k === "open"
      ? op().length
      : k === "won" || k === "lost"
        ? S.items.filter(function (o) {
            return o.r === k;
          }).length
        : op(k).length;
  }
  function sum(a) {
    return a.reduce(function (s, o) {
      return s + o.v;
    }, 0);
  }
  function filt() {
    var q = S.q.toLowerCase();
    var l = S.items.filter(function (o) {
      var ok =
        S.f === "open"
          ? o.r === "open"
          : S.f === "won" || S.f === "lost"
            ? o.r === S.f
            : o.r === "open" && o.i === S.f;
      return ok && (!q || (o.c + " " + o.w).toLowerCase().indexOf(q) > -1);
    });
    return l.sort(
      S.s === "ret"
        ? function (a, b) {
            return (a.f || 9e15) - (b.f || 9e15);
          }
        : S.s === "val"
          ? function (a, b) {
              return b.v - a.v;
            }
          : function (a, b) {
              return b.u - a.u;
            },
    );
  }
  function seg(v, act) {
    return (
      '<div class="seg" style="--k:' +
      IL[v][1] +
      '" role="group" aria-label="Nível de interesse"><i></i>' +
      IK.map(function (k) {
        return (
          '<button type="button" data-act="' +
          act +
          '" data-v="' +
          k +
          '" aria-pressed="' +
          (k === v) +
          '">' +
          ic(k) +
          IL[k][0] +
          "</button>"
        );
      }).join("") +
      "</div>"
    );
  }
  function build() {
    $("filters").insertAdjacentHTML(
      "beforeend",
      FL.map(function (f) {
        return (
          '<button class="fl" data-f="' +
          f[0] +
          '" aria-pressed="false">' +
          ic(f[0]) +
          "<span>" +
          f[1] +
          '</span><span class="n">0</span></button>'
        );
      }).join(""),
    );
  }
  function move() {
    var b = root.querySelector('.fl[aria-pressed="true"]'),
      t = $("ft");
    if (b) {
      t.style.width = b.offsetWidth + "px";
      t.style.transform = "translateX(" + b.offsetLeft + "px)";
    }
  }
  function upd() {
    root.querySelectorAll(".fl").forEach(function (b) {
      b.setAttribute("aria-pressed", S.f === b.dataset.f);
      b.querySelector(".n").textContent = cnt(b.dataset.f);
    });
    move();
    var d = S.items.filter(isDue).length,
      v = sum(op());
    $("sum").innerHTML =
      (d
        ? "<b>" + d + (d > 1 ? " negociações pedem" : " negociação pede") + " retorno hoje.</b> "
        : "Nada urgente por hoje. ") + (v ? BRL.format(v) + " em negociação." : "");
  }
  function today() {
    var d = S.items.filter(isDue).sort(function (a, b) {
        return IL[b.i][1] - IL[a.i][1];
      }),
      el = $("today");
    el.hidden = !d.length || S.v !== "list";
    if (!d.length) return;
    $("tlist").innerHTML = d
      .map(function (o) {
        return (
          '<div class="tr" data-id="' +
          esc(o.id) +
          '"><div><b>' +
          esc(o.c) +
          '</b> <span class="mut">· ' +
          esc(o.w) +
          (o.v ? " · " + BRL.format(o.v) : "") +
          '</span><div class="why">' +
          (o.f
            ? "Retorno combinado: " + rel(o.f)
            : "Sem atualização " + (off(o.u) === 0 ? "hoje" : rel(o.u))) +
          " · " +
          IL[o.i][0] +
          '</div></div><div class="ta"><button class="btn sm pri" data-act="tc">Registrei contato</button><button class="btn sm" data-act="fu" data-d="1">+1 dia</button><button class="btn sm" data-act="fu" data-d="3">+3 dias</button><button class="btn sm" data-act="open">Abrir</button></div></div>'
        );
      })
      .join("");
  }
  var EM = {
    open: [
      "Nenhuma oportunidade em andamento",
      "Comece registrando um interesse no formulário.",
      "Criar oportunidade",
    ],
    analysis: ["Nada em análise", "Nenhuma negociação aberta está classificada como Em análise."],
    cold: ["Nenhuma oportunidade Fria", "Nenhuma negociação aberta está classificada como Frio."],
    warm: ["Nenhuma oportunidade Morna", "Nenhuma negociação aberta está classificada como Morno."],
    hot: [
      "Nenhuma oportunidade Quente",
      "Nenhuma negociação aberta está classificada como Quente.",
    ],
    won: ["Nenhuma venda realizada", "Ainda não há oportunidades encerradas como Venda realizada."],
    lost: ["Nada encerrado sem avanço", "Não há registros marcados como Não avançou."],
  };
  function emp() {
    var t = S.q
      ? ["Nada encontrado", "Nenhum registro corresponde à busca neste filtro."]
      : EM[S.f];
    return (
      '<div class="empty"><svg class="fold" viewBox="0 0 96 96" fill="none" stroke="#5b8cff" aria-hidden="true"><path d="M10 30h26l6 8h44v38H10z" fill="rgba(47,107,255,.14)"/><path d="M10 30v-8h24l6 8"/><circle cx="58" cy="58" r="12" fill="rgba(5,11,27,.45)"/><path d="m67 67 9 9M72 16l4-6M80 24l7-3"/></svg><h4>' +
      t[0] +
      "</h4><p>" +
      t[1] +
      "<br>Mostrando até 100 oportunidades recentes deste negócio.<br>Fechar uma oportunidade não altera pagamentos nem estoque.</p>" +
      (t[2] ? '<button class="btn pri" data-act="focus">' + t[2] + "</button>" : "") +
      "</div>"
    );
  }
  function row(o) {
    var x = !!S.x[o.id],
      po = o.r === "open",
      ik = IL[o.i];
    var ini = initials(o);
    var int = po
      ? '<span class="int ' +
        o.i +
        '">' +
        ic(o.i) +
        ik[0] +
        ' <span class="mt" aria-hidden="true">' +
        [1, 2, 3]
          .map(function (n) {
            return "<i" + (n <= ik[1] ? ' class="on"' : "") + "></i>";
          })
          .join("") +
        "</span></span>"
      : '<span class="int ' +
        (o.r === "won" ? "won" : "") +
        '">' +
        ic(o.r) +
        (o.r === "won" ? "Venda realizada" : "Não avançou") +
        "</span>";
    var nx = po
      ? o.f
        ? '<span class="nx' +
          (isDue(o) ? " late" : "") +
          '">' +
          (o.f <= now() ? "Retomar já · " : "Retomar ") +
          rel(o.f) +
          "</span>"
        : '<span class="nx">Sem retorno marcado</span>'
      : '<span class="nx">Encerrada ' + rel(o.u) + "</span>";
    var tl = o.h
      .slice()
      .reverse()
      .map(function (h) {
        return (
          "<li>" +
          esc(h.s) +
          '<time datetime="' +
          new Date(h.t).toISOString() +
          '">' +
          fdt(h.t) +
          "</time></li>"
        );
      })
      .join("");
    var acts = po
      ? seg(o.i, "int") +
        '<div class="ro"><span class="mut">Retomar em:</span>' +
        [
          [1, "1 dia"],
          [3, "3 dias"],
          [7, "1 semana"],
          [0, "Sem data"],
        ]
          .map(function (p) {
            return (
              '<button class="btn sm" data-act="fu" data-d="' + p[0] + '">' + p[1] + "</button>"
            );
          })
          .join("") +
        '</div><div class="ro"><button class="btn sm" data-act="tc">Registrei contato</button><button class="btn sm" data-act="closef">Encerrar…</button></div>'
      : '<div class="ro"><button class="btn sm" data-act="reopenf">Reabrir…</button></div>';
    return (
      '<article class="r' +
      (S.nw === o.id ? " new" : "") +
      '" data-id="' +
      esc(o.id) +
      '" data-commercial-opportunity="' +
      esc(o.id) +
      '" data-x="' +
      x +
      '"><button class="rh" aria-expanded="' +
      x +
      '" aria-controls="v8-x' +
      esc(o.id) +
      '" data-act="tog"><span class="av" aria-hidden="true">' +
      esc(ini) +
      '</span><span class="who"><b>' +
      esc(o.c) +
      "</b><small>" +
      esc(o.w) +
      "</small></span>" +
      int +
      '<span class="val">' +
      mny(o.v) +
      "</span>" +
      nx +
      '<span class="chev">' +
      ic("chev") +
      "</span></button>" +
      '<div class="xp" id="v8-x' +
      esc(o.id) +
      '"><div><div class="in"><div class="mut">Atualizado em ' +
      fdt(o.u) +
      (o.reason ? " · Motivo: " + esc(o.reason) : "") +
      "</div>" +
      acts +
      '<div class="ro"><label class="sr" for="v8-n' +
      esc(o.id) +
      '">Anotação</label><input class="nt" id="v8-n' +
      esc(o.id) +
      '" value="' +
      esc(o.n) +
      '" placeholder="Anotação de acompanhamento" maxlength="140"><label class="sr" for="v8-v' +
      esc(o.id) +
      '">Valor</label><input class="vl" id="v8-v' +
      esc(o.id) +
      '" inputmode="decimal" value="' +
      (o.v || "") +
      '" placeholder="Valor R$"><button class="btn sm" data-act="note">Salvar</button></div>' +
      '<div data-box="cf" hidden><div class="ro"><label class="sr" for="v8-r' +
      esc(o.id) +
      '">Resultado</label><select id="v8-r' +
      esc(o.id) +
      '"><option value="won">Venda realizada</option><option value="lost">Não avançou</option></select><input id="v8-m' +
      esc(o.id) +
      '" placeholder="Motivo (obrigatório se não avançou)" maxlength="100"><button class="btn sm pri" data-act="close">Confirmar</button></div><div class="ro">' +
      ["Preço", "Sem resposta", "Escolheu outro", "Adiou"]
        .map(function (w) {
          return '<button class="chip" data-act="why" data-w="' + w + '">' + w + "</button>";
        })
        .join("") +
      "</div></div>" +
      '<div class="ro" data-box="rf" hidden><label class="sr" for="v8-j' +
      esc(o.id) +
      '">Justificativa</label><input id="v8-j' +
      esc(o.id) +
      '" placeholder="Justificativa para reabrir" maxlength="100"><button class="btn sm pri" data-act="reopen">Reabrir</button></div>' +
      nativeAudit(o) +
      '<ul class="tl" aria-label="Histórico">' +
      tl +
      "</ul></div></div></div></article>"
    );
  }
  function colOf(o) {
    if (!o.f) return "none";
    var d = off(o.f);
    return d < 0 ? "late" : d > 6 ? "none" : String(d);
  }
  function week() {
    var cols = [["late", "Atrasadas"]];
    for (var d = 0; d < 7; d++)
      cols.push([
        String(d),
        d === 0
          ? "Hoje"
          : d === 1
            ? "Amanhã"
            : new Date(now() + d * DAY).toLocaleDateString("pt-BR", {
                weekday: "short",
                day: "numeric",
              }),
      ]);
    cols.push(["none", "Depois ou sem data"]);
    var b = {};
    op().forEach(function (o) {
      var k = colOf(o);
      (b[k] = b[k] || []).push(o);
    });
    $("wk").className = "wk" + (S.sel ? " tgt" : "");
    $("wk").innerHTML = cols
      .map(function (c) {
        var a = (b[c[0]] || []).sort(function (x, y) {
          return IL[y.i][1] - IL[x.i][1];
        });
        return (
          '<div class="dc" data-col="' +
          c[0] +
          '"><button class="dh" data-act="mv" data-col="' +
          c[0] +
          '"' +
          (c[0] === "late" ? " disabled" : "") +
          "><span>" +
          c[1] +
          ' <span class="n">' +
          a.length +
          "</span></span></button>" +
          a
            .map(function (o) {
              return (
                '<button class="ch" draggable="true" data-id="' +
                esc(o.id) +
                '" data-act="pick" aria-pressed="' +
                (S.sel === o.id) +
                '"><b>' +
                esc(nm(o)) +
                "</b><br>" +
                esc(o.w) +
                "<small>" +
                ic(o.i) +
                IL[o.i][0] +
                (o.v ? " · " + BRL.format(o.v) : "") +
                "</small></button>"
              );
            })
            .join("") +
          (a.length ? "" : '<div class="mut" style="padding:0 12px 12px">Livre</div>') +
          "</div>"
        );
      })
      .join("");
  }
  function initials(o) {
    return nm(o)
      .split(/\s+/)
      .map((word) => word.match(/\p{L}/u)?.[0])
      .filter(Boolean)
      .slice(0, 2)
      .join("")
      .toLocaleUpperCase("pt-BR");
  }
  function rects() {
    var r = {};
    root.querySelectorAll(".tk").forEach(function (t) {
      r[t.dataset.id] = t.getBoundingClientRect();
    });
    return r;
  }
  function flip(pr) {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    root.querySelectorAll(".tk").forEach(function (t) {
      var p = pr[t.dataset.id];
      if (!p) return;
      var n = t.getBoundingClientRect(),
        dx = p.left - n.left,
        dy = p.top - n.top;
      if (dx || dy)
        t.animate([{ transform: "translate(" + dx + "px," + dy + "px)" }, { transform: "none" }], {
          duration: 480,
          easing: "cubic-bezier(.22,1,.36,1)",
        });
    });
  }
  function board() {
    var a = document.activeElement,
      fid = a && a.classList && a.classList.contains("tk") ? a.dataset.id : null;
    $("board").innerHTML = IK.map(function (k) {
      var l = op(k).sort(function (x, y) {
        return y.v - x.v;
      });
      return (
        '<div class="bz z-' +
        k +
        '" data-zone="' +
        k +
        '"><div class="bh">' +
        ic(k) +
        "<b>" +
        IL[k][0] +
        '</b><span class="n">' +
        l.length +
        '</span></div><div class="bay">' +
        l
          .map(function (o) {
            var z = Math.round(Math.min(130, 44 + Math.sqrt(o.v || 0) * 0.9));
            return (
              '<button class="tk' +
              (isDue(o) ? " due" : "") +
              '" data-id="' +
              esc(o.id) +
              '" style="width:' +
              z +
              "px;height:" +
              z +
              'px" aria-label="' +
              esc(nm(o)) +
              ", " +
              esc(o.w) +
              ", " +
              IL[k][0] +
              (o.v ? ", " + BRL.format(o.v) : "") +
              (isDue(o) ? ", pede retorno" : "") +
              '. Setas esquerda e direita mudam o interesse." title="' +
              esc(nm(o)) +
              (o.v ? " · " + BRL.format(o.v) : "") +
              '">' +
              esc(initials(o)) +
              "</button>"
            );
          })
          .join("") +
        (l.length ? "" : '<span class="mut">Nenhuma</span>') +
        "</div></div>"
      );
    }).join("");
    if (fid) {
      var t = root.querySelector('.tk[data-id="' + fid + '"]');
      if (t) t.focus({ preventScroll: true });
    }
  }
  function render() {
    const rect = rects(),
      list = filt();
    const drafts = new Map();
    if (root.dataset.scope === S.scope)
      for (const card of $("list").querySelectorAll("[data-id]")) {
        drafts.set(card.dataset.id, {
          values: [...card.querySelectorAll("input[id],select[id],textarea[id]")]
            .filter(
              (field) =>
                field.value !==
                (field.tagName === "SELECT"
                  ? (
                      [...field.options].find((option) => option.defaultSelected) ||
                      field.options[0]
                    )?.value
                  : field.defaultValue),
            )
            .map((field) => [field.id, field.value]),
          boxes: [...card.querySelectorAll("[data-box]")]
            .filter((box) => !box.hidden)
            .map((box) => box.dataset.box),
          audit: !!card.querySelector(".native-audit")?.open,
        });
      }
    root.dataset.scope = S.scope || "";
    const focus = focusToken();
    $("list").innerHTML = list.length ? list.map(row).join("") : emp();
    $("cols").hidden = !list.length;
    $("lt").hidden = !list.length;
    $("lt").textContent =
      list.length +
      (list.length === 1 ? " oportunidade" : " oportunidades") +
      (sum(list) ? " · " + BRL.format(sum(list)) + " estimados neste navegador" : "");
    for (const card of $("list").querySelectorAll("[data-id]")) {
      const draft = drafts.get(card.dataset.id);
      if (!draft) continue;
      for (const [id, value] of draft.values) {
        const field = card.querySelector("#" + CSS.escape(id));
        if (field) field.value = value;
      }
      for (const name of draft.boxes) {
        const box = card.querySelector('[data-box="' + name + '"]');
        if (box) box.hidden = false;
      }
      const audit = card.querySelector(".native-audit");
      if (audit) audit.open = draft.audit;
    }
    board();
    flip(rect);
    week();
    const chosen = S.sel && S.items.find((o) => o.id === S.sel);
    if (S.sel && !chosen) S.sel = null;
    $("sel").hidden = !chosen;
    if (chosen) $("sn").textContent = nm(chosen) + " selecionado(a). Toque em um dia para mover.";
    root.querySelector(".views").style.setProperty("--k", { list: 0, board: 1, week: 2 }[S.v]);
    root
      .querySelectorAll(".views button")
      .forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === S.v)));
    $("vl").hidden = S.v !== "list";
    $("vb").hidden = S.v !== "board";
    $("vw").hidden = S.v !== "week";
    upd();
    today();
    controls();
    root.querySelectorAll(".fl").forEach((b) => {
      b.dataset.commercialFilter = b.dataset.f === "analysis" ? "unknown" : b.dataset.f;
      b.setAttribute(
        "aria-label",
        FL.find((f) => f[0] === b.dataset.f)[1] + " (" + cnt(b.dataset.f) + ")",
      );
    });
    const snapshot = store.snapshot();
    if (!snapshot.ready)
      $("sum").textContent = snapshot.problem
        ? "Consulta indisponível. Dados anteriores somente para leitura."
        : auth.remote
          ? "Entre na sua conta e carregue as oportunidades deste negócio."
          : "O acompanhamento comercial requer uma conta conectada ao backend. A análise local está disponível abaixo.";
    else if (!writable() && !snapshot.busy) $("sum").append(" Acesso somente leitura.");
    S.nw = null;
    if (focus && focus.row) restoreFocus(focus);
    document.dispatchEvent(new Event("socialmei-opportunity-v8-change"));
  }
  function view(mode) {
    S.v = mode;
    S.sel = null;
    render();
  }
  function openRow(id) {
    const item = S.items.find((o) => o.id === id);
    if (!item) return;
    S.f = item.r === "open" ? "open" : item.r;
    S.q = "";
    $("q").value = "";
    S.x[id] = true;
    view("list");
    const target = root.querySelector(
      '#commercialOpportunityList [data-id="' + CSS.escape(id) + '"]',
    );
    target?.scrollIntoView({
      behavior: SocialMEIMotion.reduced ? "auto" : "smooth",
      block: "center",
    });
    target?.querySelector(".rh")?.focus({ preventScroll: true });
    loadHistory(item);
  }
  function moveTo(o, col) {
    if (!o || col === "late" || !writable()) return;
    const date =
      col === "none"
        ? ""
        : new Date(new Date().setDate(new Date().getDate() + Number(col))).toLocaleDateString(
            "sv-SE",
          );
    localChange(
      o,
      { date, contacted: false },
      date
        ? "Retorno movido para " + new Date(date + "T12:00").toLocaleDateString("pt-BR")
        : "Retorno removido",
    );
  }
  function quickDate(o, days) {
    const d = new Date();
    d.setDate(d.getDate() + days);
    localChange(
      o,
      { date: days ? d.toLocaleDateString("sv-SE") : "", contacted: false },
      days ? "Retorno marcado para " + rel(d.getTime()) : "Data de retorno removida",
    );
  }
  async function loadHistory(o) {
    if (!auth.remote || !auth.current) return;
    const scope = S.scope;
    try {
      const events = await store.history(o.id);
      if (scope !== store.snapshot().scope) return;
      S.histories[o.id] = { revision: o.raw.revision, events };
      project();
      // Reading history must not replace fields the person is currently editing.
      const card = $("list").querySelector('[data-id="' + CSS.escape(o.id) + '"]');
      const timeline = card?.querySelector(".tl");
      const updated = S.items.find((row) => row.id === o.id);
      if (timeline && updated)
        timeline.innerHTML = updated.h
          .slice()
          .reverse()
          .map(
            (event) =>
              "<li>" +
              esc(event.s) +
              '<time datetime="' +
              new Date(event.t).toISOString() +
              '">' +
              fdt(event.t) +
              "</time></li>",
          )
          .join("");
      const status = card?.querySelector('.native-audit [role="status"]');
      if (status) status.textContent = "Histórico remoto consultado.";
    } catch (e) {
      toast(e.message, true);
    }
  }
  const setErr = (id, field, text) => {
    $(field).className = "f" + (text ? " err" : "");
    $(id).textContent = text || "";
  };
  $("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!writable()) return;
    const client = Number($("client").value),
      title = $("what").value.trim(),
      amount = parseMoney($("val").value),
      days = Number($("fup").value);
    setErr("e1", "fc", client ? "" : "Escolha um cliente da lista.");
    setErr(
      "e2",
      "fw",
      title.length >= 3 ? "" : "Descreva o que o cliente procura (mínimo 3 letras).",
    );
    setErr("e3", "fv", Number.isNaN(amount) ? "Digite um valor como 350 ou 350,50." : "");
    if (!client || title.length < 3 || Number.isNaN(amount)) {
      if (Number.isNaN(amount)) root.querySelector(".mo").open = true;
      toast("Confira os campos destacados.", true);
      (!client ? $("client") : title.length < 3 ? $("what") : $("val")).focus();
      return;
    }
    const captured = {
      scope: S.scope,
      amount,
      date: days
        ? new Date(new Date().setDate(new Date().getDate() + days)).toLocaleDateString("sv-SE")
        : "",
    };
    await run(
      () => store.create({ client_id: client, title, interest_level: $("interest").value }),
      "Oportunidade criada no negócio atual.",
      (created) => {
        S.f = "open";
        S.q = "";
        $("q").value = "";
        S.nw = created.id;
        let warning = "";
        if (captured.scope === store.snapshot().scope && (captured.amount || captured.date))
          try {
            planning.save(created.id, { amount: captured.amount, date: captured.date });
          } catch (e) {
            warning =
              "Oportunidade criada no CRM. " +
              e.message +
              " Edite o planejamento nesta oportunidade; não a crie novamente.";
          }
        $("what").value = "";
        $("client").value = "";
        if (!warning) $("val").value = "";
        document.dispatchEvent(
          new CustomEvent("socialmei-v8-created", { detail: { id: created.id } }),
        );
        return warning;
      },
    );
  });
  $("q").addEventListener("input", (event) => {
    S.q = event.target.value;
    render();
  });
  $("sort").addEventListener("change", (event) => {
    S.s = event.target.value;
    render();
  });
  root.addEventListener("click", async (event) => {
    const menu = event.target.closest("[data-menu]");
    if (menu) {
      const target = $(menu.dataset.menu.replace(/^v8-/, "")),
        opening = target.hidden;
      closeMenus();
      target.hidden = !opening;
      menu.setAttribute("aria-expanded", String(opening));
      return;
    }
    const filter = event.target.closest("[data-f]");
    if (filter) {
      S.f = filter.dataset.f;
      render();
      filter.focus({ preventScroll: true });
      filter.scrollIntoView({ inline: "nearest", block: "nearest" });
      return;
    }
    const button = event.target.closest("[data-act]");
    if (!button || button.disabled) return;
    const act = button.dataset.act,
      card = button.closest("[data-id]"),
      o = card && S.items.find((item) => item.id === card.dataset.id),
      key = button.dataset.v;
    if (["focus", "newop"].includes(act)) {
      $("client").scrollIntoView({
        block: "center",
        behavior: SocialMEIMotion.reduced ? "auto" : "smooth",
      });
      $("client").focus({ preventScroll: true });
      return;
    }
    if (act === "palette") {
      cpOpen();
      return;
    }
    if (act === "copy") {
      copyDue();
      return;
    }
    if (act === "view") {
      view(key);
      closeMenus();
      return;
    }
    if (act === "selopen") {
      if (S.sel) openRow(S.sel);
      return;
    }
    if (act === "pick") {
      S.sel = o && S.sel !== o.id ? o.id : null;
      render();
      return;
    }
    if (act === "mv") {
      const item = S.items.find((x) => x.id === S.sel);
      S.sel = null;
      moveTo(item, button.dataset.col);
      return;
    }
    if (!o) return;
    if (act === "tog") {
      S.x[o.id] = !S.x[o.id];
      card.dataset.x = String(S.x[o.id]);
      button.setAttribute("aria-expanded", String(!!S.x[o.id]));
      if (S.x[o.id] && !S.histories[o.id]) loadHistory(o);
      return;
    }
    if (act === "open") {
      openRow(o.id);
      return;
    }
    if (act === "history") {
      loadHistory(o);
      return;
    }
    if (!writable()) return;
    if (act === "int") {
      await setInt(o, key);
      return;
    }
    if (act === "fu") {
      quickDate(o, Number(button.dataset.d));
      return;
    }
    if (act === "tc") {
      localChange(o, { date: "", contacted: true }, "Contato registrado");
      return;
    }
    if (act === "note") {
      const amount = parseMoney(card.querySelector(".vl").value),
        note = card.querySelector(".nt").value.trim();
      if (Number.isNaN(amount)) {
        toast("Digite um valor como 350 ou 350,50.", true);
        card.querySelector(".vl").focus();
        return;
      }
      localChange(o, { amount, note }, "Informações atualizadas");
      return;
    }
    if (act === "closef" || act === "reopenf") {
      const box = card.querySelector('[data-box="' + (act === "closef" ? "cf" : "rf") + '"]');
      box.hidden = !box.hidden;
      if (!box.hidden) box.querySelector("input").focus();
      return;
    }
    if (act === "why") {
      button.closest("[data-box]").querySelector("input").value = button.dataset.w;
      return;
    }
    if (act === "close") {
      const outcome = $("r" + o.id).value,
        note = $("m" + o.id).value.trim();
      if (outcome === "lost" && !note) {
        toast("Informe o motivo para encerrar como Não avançou.", true);
        $("m" + o.id).focus();
        return;
      }
      const reason =
        outcome === "won"
          ? "sale_completed"
          : {
              Preço: "price",
              "Escolheu outro": "other_supplier",
              Adiou: "timing",
              Desistiu: "gave_up",
            }[note] || "other";
      await run(
        () => store.close(o.raw, outcome, reason, note),
        "Oportunidade encerrada. Pagamentos e estoque não foram alterados.",
        () => {
          delete S.histories[o.id];
        },
      );
      return;
    }
    if (act === "reopen") {
      const reason = $("j" + o.id).value.trim();
      if (!reason) {
        toast("Escreva uma justificativa para reabrir.", true);
        $("j" + o.id).focus();
        return;
      }
      await run(
        () => store.reopen(o.raw, reason),
        "Negociação reaberta.",
        () => {
          delete S.histories[o.id];
        },
      );
      return;
    }
    if (act === "sale") {
      const sale = Number(root.querySelector("#v8-sale-" + CSS.escape(o.id)).value);
      if (!Number.isSafeInteger(sale) || sale < 1) {
        toast("Selecione uma venda ativa deste cliente.", true);
        return;
      }
      await run(
        () => store.linkSale(o.raw, sale),
        "Venda vinculada. O vínculo não confirma pagamento.",
        () => {
          delete S.histories[o.id];
        },
      );
    }
  });
  async function copyDue() {
    const due = S.items.filter(isDue);
    if (!due.length) {
      toast("Nenhum retorno pendente hoje.");
      return;
    }
    const text =
      "Retornos de hoje:\n" +
      due.map((o) => "• " + nm(o) + " — " + o.w + " (" + IL[o.i][0] + ")").join("\n");
    try {
      await navigator.clipboard.writeText(text);
      toast("Lista copiada. Nenhuma mensagem enviada.");
    } catch {
      toast("Não foi possível copiar. Confira a permissão do navegador.", true);
    }
  }
  let paletteIndex = 0,
    paletteCommands = [],
    returnFocus = null;
  function commands() {
    const choices = [
      {
        t: "Nova oportunidade",
        k: "Ação",
        f: () => {
          $("client").focus();
          $("client").scrollIntoView({ block: "center" });
        },
      },
      { t: "Ver lista", k: "Ir para", f: () => view("list") },
      { t: "Ver termômetro", k: "Ir para", f: () => view("board") },
      { t: "Ver semana", k: "Ir para", f: () => view("week") },
      { t: "Copiar retornos de hoje", k: "Ação", f: copyDue },
      {
        t: "Alternar tema",
        k: "Ação",
        f: () =>
          SocialMEIThemes.select(SocialMEIThemes.current().base === "dark" ? "light" : "dark"),
      },
      {
        t: "Análise de mensagens e revisão humana",
        k: "Ir para",
        f: () => {
          analysis.open = true;
          summary.focus();
          analysis.scrollIntoView({ block: "start" });
        },
      },
    ];
    for (const o of S.items)
      choices.push({
        t: nm(o) + " — " + o.w,
        k: o.r === "open" ? "Abrir" : "Encerrada",
        f: () => openRow(o.id),
      });
    if (SocialMEIClients.connectionState === "ready")
      for (const client of appData.clientes)
        choices.push({
          t: "Cliente: " + client.nome,
          k: "Selecionar",
          f: () => {
            $("client").value = String(client.id);
            $("what").focus();
            $("form").scrollIntoView({ block: "center" });
          },
        });
    return choices;
  }
  function cpRender() {
    const query = $("ci").value.toLocaleLowerCase("pt-BR");
    paletteCommands = commands()
      .filter((c) => c.t.toLocaleLowerCase("pt-BR").includes(query))
      .slice(0, 8);
    paletteIndex = Math.max(0, Math.min(paletteIndex, paletteCommands.length - 1));
    $("cl").innerHTML = paletteCommands.length
      ? paletteCommands
          .map(
            (c, i) =>
              '<li role="option" id="v8-command-' +
              i +
              '" aria-selected="' +
              (i === paletteIndex) +
              '" data-i="' +
              i +
              '"><span>' +
              esc(c.t) +
              "</span><small>" +
              esc(c.k) +
              "</small></li>",
          )
          .join("")
      : "<li>Nada encontrado</li>";
    $("ci").setAttribute(
      "aria-activedescendant",
      paletteCommands.length ? "v8-command-" + paletteIndex : "",
    );
  }
  function cpOpen() {
    returnFocus = document.activeElement;
    $("cp").hidden = false;
    $("ci").value = "";
    paletteIndex = 0;
    cpRender();
    $("ci").focus();
  }
  function cpClose() {
    if ($("cp").hidden) return;
    $("cp").hidden = true;
    if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
  }
  function cpGo(index) {
    const command = paletteCommands[index];
    if (command) {
      cpClose();
      command.f();
    }
  }
  $("ci").addEventListener("input", () => {
    paletteIndex = 0;
    cpRender();
  });
  $("ci").addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      paletteIndex += event.key === "ArrowDown" ? 1 : -1;
      cpRender();
    } else if (event.key === "Enter") {
      event.preventDefault();
      cpGo(paletteIndex);
    } else if (event.key === "Escape") {
      event.preventDefault();
      cpClose();
    } else if (event.key === "Tab") event.preventDefault();
  });
  $("cl").addEventListener("click", (event) => {
    const option = event.target.closest("[data-i]");
    if (option) cpGo(Number(option.dataset.i));
  });
  $("cp").addEventListener("click", (event) => {
    if (event.target === $("cp")) cpClose();
  });
  function closeMenus() {
    root.querySelectorAll(".menu").forEach((e) => (e.hidden = true));
    root.querySelectorAll("[data-menu]").forEach((e) => e.setAttribute("aria-expanded", "false"));
  }
  document.addEventListener("click", (event) => {
    if (!event.target.closest("#opportunityLifecycle .mw")) closeMenus();
  });
  document.addEventListener(
    "keydown",
    (event) => {
      if (currentView !== "Oportunidades" || !document.body.classList.contains("experience-app"))
        return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        event.stopImmediatePropagation();
        $("cp").hidden ? cpOpen() : cpClose();
        return;
      }
      if (event.key === "Escape") {
        closeMenus();
        cpClose();
        return;
      }
      if (
        event.defaultPrevented ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        event.target.closest("input,select,textarea,[contenteditable]") ||
        !$("cp").hidden ||
        activeModalDialog()
      )
        return;
      if (event.key === "/") {
        event.preventDefault();
        event.stopImmediatePropagation();
        view("list");
        $("q").focus();
      } else if (event.key.toLowerCase() === "n") {
        event.preventDefault();
        $("client").focus();
      }
    },
    true,
  );
  let drag = null;
  function zoneAt(x, y) {
    const zone = document.elementFromPoint(x, y)?.closest(".bz");
    return zone && root.contains(zone) ? zone : null;
  }
  $("board").addEventListener("pointerdown", (event) => {
    const chip = event.target.closest(".tk");
    if (!chip || event.button || !writable()) return;
    drag = { chip, id: chip.dataset.id, x: event.clientX, y: event.clientY, on: false };
    chip.setPointerCapture(event.pointerId);
  });
  document.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x,
      dy = event.clientY - drag.y;
    if (!drag.on) {
      if (Math.abs(dx) + Math.abs(dy) < 8) return;
      drag.on = true;
      drag.chip.classList.add("drag");
    }
    drag.chip.style.transform = "translate(" + dx + "px," + dy + "px) scale(1.1)";
    const zone = zoneAt(event.clientX, event.clientY);
    root.querySelectorAll(".bz").forEach((z) => z.classList.toggle("ov", z === zone));
  });
  function endDrag(event, cancel) {
    if (!drag) return;
    const active = drag;
    drag = null;
    root.querySelectorAll(".bz").forEach((z) => z.classList.remove("ov"));
    const transform = active.chip.style.transform;
    active.chip.classList.remove("drag");
    active.chip.style.transform = "";
    if (cancel) return;
    if (!active.on) {
      openRow(active.id);
      return;
    }
    const zone = zoneAt(event.clientX, event.clientY),
      o = S.items.find((i) => i.id === active.id);
    if (zone && o && zone.dataset.zone !== o.i) {
      setInt(o, zone.dataset.zone);
      return;
    }
    if (!SocialMEIMotion.reduced)
      active.chip.animate([{ transform }, { transform: "none" }], {
        duration: 300,
        easing: "cubic-bezier(.22,1,.36,1)",
      });
  }
  document.addEventListener("pointerup", (event) => endDrag(event, false));
  document.addEventListener("pointercancel", (event) => endDrag(event, true));
  $("board").addEventListener("click", (event) => {
    const chip = event.target.closest(".tk");
    if (chip && event.detail === 0) openRow(chip.dataset.id);
  });
  $("board").addEventListener("keydown", (event) => {
    const chip = event.target.closest(".tk");
    if (!chip || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const o = S.items.find((i) => i.id === chip.dataset.id),
      index = IL[o.i][1] + (event.key === "ArrowRight" ? 1 : -1);
    if (index >= 0 && index <= 3) setInt(o, IK[index]);
  });
  const weekRoot = $("wk");
  weekRoot.addEventListener("dragstart", (event) => {
    const chip = event.target.closest(".ch");
    if (chip && writable()) {
      event.dataTransfer.setData("text/plain", chip.dataset.id);
      event.dataTransfer.effectAllowed = "move";
    }
  });
  weekRoot.addEventListener("dragover", (event) => {
    const col = event.target.closest(".dc");
    if (col && col.dataset.col !== "late" && writable()) {
      event.preventDefault();
      col.classList.add("ov");
    }
  });
  weekRoot.addEventListener("dragleave", (event) => {
    const col = event.target.closest(".dc");
    if (col && !col.contains(event.relatedTarget)) col.classList.remove("ov");
  });
  weekRoot.addEventListener("drop", (event) => {
    const col = event.target.closest(".dc");
    if (!col || col.dataset.col === "late" || !writable()) return;
    event.preventDefault();
    const o = S.items.find((i) => i.id === event.dataTransfer.getData("text/plain"));
    if (o && colOf(o) !== col.dataset.col) moveTo(o, col.dataset.col);
    else render();
  });
  $("refresh").addEventListener("click", () =>
    run(() => store.reload(), "Lista atualizada com os dados do negócio atual."),
  );
  let frame = 0;
  root.querySelector(".hero2").addEventListener("pointermove", (event) => {
    if (frame || SocialMEIMotion.reduced) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      const rect = $("ill").getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      $("ill").style.setProperty(
        "--px",
        ((event.clientX - rect.left) / rect.width - 0.5).toFixed(2),
      );
      $("ill").style.setProperty(
        "--py",
        ((event.clientY - rect.top) / rect.height - 0.5).toFixed(2),
      );
    });
  });
  function syncClients() {
    const selected = $("client").value,
      options = SocialMEIClients.connectionState === "ready" ? appData.clientes : [];
    const signature = JSON.stringify(options.map((c) => [c.id, c.nome]));
    if ($("client").dataset.signature === signature) return;
    $("client").dataset.signature = signature;
    $("client").innerHTML =
      '<option value="">Selecione um cliente cadastrado</option>' +
      options.map((c) => '<option value="' + esc(c.id) + '">' + esc(c.nome) + "</option>").join("");
    $("client").value = selected;
  }
  function sync() {
    const active =
      currentView === "Oportunidades" && document.body.classList.contains("experience-app");
    document.body.classList.toggle("exact-opportunity-active", active);
    if (!active) {
      closeMenus();
      cpClose();
      if (drag) {
        drag.chip.style.transform = "";
        drag = null;
      }
    }
    const snapshot = store.snapshot();
    if (snapshot.scope !== S.scope) {
      project();
      render();
    }
    syncClients();
    controls();
    if (active) requestAnimationFrame(move);
    if (active && auth.remote && auth.current && !S.loaded) {
      S.loaded = true;
      run(() => store.reload(), false);
    }
  }
  window.SocialMEIOpportunityV8Bridge = Object.freeze({
    snapshot: () => store.snapshot(),
    changeInterest: async (id, interest) => {
      const o = S.items.find((i) => i.id === id);
      return !!(await setInt(o, interest === "unknown" ? "analysis" : interest));
    },
    refresh: () => run(() => store.reload(), "Dados atualizados no negócio atual."),
  });
  document.addEventListener("socialmei-view-change", sync);
  document.addEventListener("socialmei-data-change", sync);
  document.addEventListener("socialmei-business-profile-change", sync);
  window.addEventListener("resize", move);
  document.fonts?.ready.then(move);
  build();
  project();
  render();
  auth.ready.then(sync);
});
