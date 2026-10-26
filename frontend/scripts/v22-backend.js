/* V22 transport bridge. Visual templates and animation code remain owned by V22. */
window.SocialMEIV22 = (() => {
  const auth = window.SocialMEIAuth;
  const remote = auth.remote;
  const root = document.getElementById("app");
  const request = (...args) => auth.request(...args);
  let loaded = false;
  let inbox = [];
  let preferences = null;
  let data = { clients: [], products: [], sales: [], finance: [] };
  const date = (value) =>
    value ? new Date(String(value).slice(0, 10) + "T12:00:00").toLocaleDateString("pt-BR") : "—";
  const money = (value) => {
    const n = Number(String(value).replace(/\./g, "").replace(",", "."));
    if (!Number.isFinite(n) || n < 0) throw Error("Confira o valor informado.");
    return n;
  };
  const error = (e) => toast(e.message || "Não foi possível confirmar a operação.");
  function parseDate(text) {
    const [day, month, year] = String(text).split("/").map(Number);
    return new Date(year, month - 1, day).getTime();
  }
  function inPeriod(text) {
    const value = parseDate(text),
      today = new Date();
    today.setHours(23, 59, 59, 999);
    const start = new Date(today);
    if (S.rp === 0) start.setDate(1);
    else if (S.rp === 1) start.setDate(start.getDate() - 6);
    else if (S.rp === 2) start.setDate(start.getDate() - 2);
    else {
      start.setDate(1);
      today.setDate(Math.min(10, today.getDate()));
    }
    start.setHours(0, 0, 0, 0);
    return value >= start.getTime() && value <= today.getTime();
  }
  function inFinancialPeriod(text, days) {
    if (!days) return true;
    const start = new Date();
    start.setDate(start.getDate() - days + 1);
    start.setHours(0, 0, 0, 0);
    return parseDate(text) >= start.getTime() && parseDate(text) <= Date.now();
  }
  const identityKey = () => `${auth.current.usuario.id}:${auth.current.negocio.id}`;
  async function refresh() {
    const [clients, products, sales, finance] = await Promise.all(
      ["/clientes", "/produtos", "/vendas", "/financeiro"].map((p) => request(p)),
    );
    if (![clients, products, sales, finance].every(Array.isArray))
      throw Error("Resposta de gestão inválida.");
    data = {
      clients,
      products,
      sales: sales.filter((v) => ["Pendente", "Pago"].includes(v.status)),
      finance,
    };
    CL.splice(
      0,
      CL.length,
      ...clients.map((c) => {
        const paid = sales.filter((v) => v.cliente_id === c.id && v.status === "Pago");
        const history = sales
          .filter((v) => v.cliente_id === c.id && ["Pago", "Pendente"].includes(v.status))
          .sort((a, b) => b.data.localeCompare(a.data));
        const latest = history[0];
        return [
          c.nome,
          c.nome.split(" ")[0],
          ini(c.nome),
          c.email || "",
          latest ? date(latest.data) : "—",
          paid.reduce((total, v) => total + v.valor, 0),
          "#e4dcff",
          "#4a3aa8",
          latest
            ? [
                String(latest.id),
                date(latest.data),
                latest.item,
                String(latest.quantidade),
                latest.valor,
                latest.status,
              ]
            : null,
          c.observacao || "",
          "",
        ];
      }),
    );
    PR.splice(
      0,
      PR.length,
      ...products.map((p) => [
        p.nome,
        String(p.id),
        p.tipo,
        p.preco,
        p.status === "Ativo" ? 1 : 0,
        "",
        p.custo,
        p.tipo === "Serviço" ? undefined : p.estoque || 0,
        p.minimo || 0,
        p.tipo,
      ]),
    );
    V.splice(
      0,
      V.length,
      ...sales
        .filter((v) => ["Pendente", "Pago"].includes(v.status))
        .map((v) => [
          String(v.id),
          `${v.item} · ${v.quantidade} ${v.quantidade === 1 ? "item" : "itens"}`,
          v.cliente,
          ini(v.cliente),
          date(v.data),
          v.status,
          v.valor,
        ]),
    );
    F.splice(
      0,
      F.length,
      ...finance
        .filter((f) => f.status === "pago")
        .map((f) => [
          date(f.data_pagamento || f.vencimento),
          f.descricao,
          f.tipo,
          f.tipo === "receita" ? 1 : 0,
          f.valor,
        ]),
    );
    document
      .querySelectorAll("iframe")
      .forEach((frame) =>
        frame.contentWindow?.postMessage({ smeiDataChanged: true }, location.origin),
      );
  }
  async function refreshConfirmed() {
    try {
      await refresh();
      render();
      return true;
    } catch (e) {
      loaded = false;
      toast("Salvo no servidor. Atualize a página para recarregar a lista; não repita a operação.");
      return false;
    }
  }
  async function write(path, method, payload, operation = false) {
    if (!loaded) throw Error("Aguarde o carregamento dos dados.");
    let key,
      packet = payload;
    if (operation) {
      key = "socialmei-v22-operation:" + identityKey();
      const pending = JSON.parse(localStorage.getItem(key) || "null");
      const signature = JSON.stringify({ path, method, payload });
      if (pending && pending.signature !== signature)
        throw Error(
          "Existe uma operação sem confirmação. Repita os mesmos dados antes de iniciar outra.",
        );
      packet = pending?.packet || { ...payload, operation_id: crypto.randomUUID() };
      localStorage.setItem(key, JSON.stringify({ signature, packet }));
    }
    try {
      const result = await request(path, method, packet);
      if (key) localStorage.removeItem(key);
      return result;
    } catch (e) {
      if (key && [400, 403, 404, 409, 422].includes(e.status)) localStorage.removeItem(key);
      throw e;
    }
  }
  function form(title, fields, submit, label = "Salvar") {
    openForm(
      title,
      "Os dados serão confirmados no negócio da sua sessão.",
      fields,
      () => "",
      label,
    );
    const dialog = dlg(),
      element = dialog.querySelector("form");
    for (const f of fields) {
      if (f.disabled) {
        const input = element.querySelector("#f_" + f.id);
        if (input) {
          input.disabled = true;
          input.title = "Este campo ainda não tem persistência no servidor.";
        }
      }
    }
    const secret = element.querySelector("#f_password");
    if (secret) {
      secret.type = "password";
      secret.autocomplete = "current-password";
    }
    // Keep V22 validation and markup; replace its local callback at the submit boundary.
    element.onsubmit = async (event) => {
      event.preventDefault();
      const values = {};
      let invalid = false;
      for (const field of fields) {
        const input = document.getElementById("f_" + field.id);
        const value = field.type === "check" ? input.checked : input.value.trim();
        values[field.id] = value;
        const status = document.getElementById("e_" + field.id);
        if (status) status.textContent = "";
        if (field.req && !value) {
          status.textContent = "Preencha este campo.";
          invalid = true;
        }
      }
      const email = fields.find((f) => f.type === "email");
      if (email && values[email.id] && !/^\S+@\S+\.\S+$/.test(values[email.id])) {
        document.getElementById("e_" + email.id).textContent = "Informe um e-mail válido.";
        invalid = true;
      }
      if (invalid) return;
      const buttons = [...element.querySelectorAll("button")];
      buttons.forEach((b) => (b.disabled = true));
      try {
        await submit(values);
        dialog.close();
        try {
          await refresh();
          render();
          toast("Alteração confirmada no negócio.");
        } catch (e) {
          loaded = false;
          toast(
            "Salvo no servidor. Atualize a página para recarregar a lista; não repita o cadastro.",
          );
        }
      } catch (e) {
        error(e);
      } finally {
        buttons.forEach((b) => (b.disabled = false));
      }
    };
  }
  const field = (id, label, value = "", extra = {}) => ({ id, label, value, ...extra });
  function clientForm(edit = false) {
    const c = edit ? data.clients[S.cli] : null;
    form(
      edit ? "Editar cliente" : "Novo cliente",
      [
        field("n", "Nome", c?.nome || "", { req: 1 }),
        field("e", "E-mail", c?.email || "", { type: "email" }),
        field("o", "Observações", c?.observacao || "", { type: "textarea" }),
      ],
      (v) =>
        write("/clientes" + (c ? "/" + c.id : ""), c ? "PATCH" : "POST", {
          nome: v.n,
          email: v.e,
          observacao: v.o,
          ...(c ? { expected_version: c.versao } : {}),
        }),
    );
  }
  function productForm(edit = false) {
    const p = edit ? data.products[S.prod] : null;
    form(
      edit ? "Editar produto ou serviço" : "Novo produto ou serviço",
      [
        field("n", "Nome", p?.nome || "", { req: 1 }),
        field("c", "Categoria", "", { disabled: true }),
        field("t", "Tipo", p?.tipo || "Produto", {
          type: "select",
          options: ["Produto", "Serviço"],
        }),
        field("p", "Preço de venda (R$)", String(p?.preco || 0).replace(".", ","), {
          req: 1,
          type: "money",
        }),
        field("k", "Custo (R$)", String(p?.custo || 0).replace(".", ","), { type: "money" }),
        field("e", "Estoque", String(p?.estoque || 0)),
        field("m", "Estoque mínimo", String(p?.minimo || 0)),
        field("d", "Descrição", "", { type: "textarea", disabled: true }),
        field("a", "Disponível", p ? p.status === "Ativo" : true, { type: "check" }),
      ],
      (v) => {
        const product = {
          nome: v.n,
          tipo: v.t,
          preco: money(v.p),
          custo: money(v.k || "0"),
          status: v.a ? "Ativo" : "Inativo",
          ...(v.t === "Produto" ? { estoque: Number(v.e), minimo: Number(v.m) } : {}),
        };
        if (
          v.t === "Produto" &&
          (!Number.isSafeInteger(product.estoque) || !Number.isSafeInteger(product.minimo))
        )
          throw Error("Informe quantidades inteiras.");
        return write("/produtos" + (p ? "/" + p.id : ""), p ? "PATCH" : "POST", {
          ...product,
          ...(p ? { expected_version: p.versao } : {}),
        });
      },
    );
  }
  async function initialize() {
    if (!remote) return;
    root.hidden = true;
    await auth.ready;
    if (!auth.current) {
      location.replace("entrada.html#/entrar");
      return;
    }
    // Never hydrate authenticated pages from the generic demonstration profile.
    S.user.nome = auth.current.usuario.nome;
    S.user.email = auth.current.usuario.email;
    S.biz.nome = auth.current.negocio.nome;
    S.biz.email = "";
    S.biz.tel = auth.current.negocio.configuracao?.telefone || "";
    try {
      const business = await request("/workspace-profile");
      S.biz.seg = business.profile?.activity || "";
    } catch (e) {
      if (![403, 404, 503].includes(e.status)) throw e;
    }
    S.biz.desc = "";
    try {
      const cap = await request("/message-enrichment/capabilities");
      if (cap.mode === "stub" || cap.instagram_inbox || cap.waha_inbox) {
        const result = await request("/message-enrichment/conversations");
        if (result.workspace_id !== auth.current.negocio.id)
          throw Error("Resposta de outro negócio.");
        inbox = result.items;
      }
    } catch (e) {
      if (![403, 503].includes(e.status)) throw e;
    }
    C.splice(0, C.length);
    for (const row of inbox) {
      const messages = row.messages || [],
        last = messages.at(-1);
      if (!last) continue;
      C.push([
        "me-" + row.id,
        row.contact_name,
        esc(ini(row.contact_name)),
        "#e4dcff",
        "#4a3aa8",
        last?.text || "",
        row.channel === "instagram" ? "ig" : "wa",
        "Aberto",
        last
          ? new Date(last.occurred_at).toLocaleTimeString("pt-BR", {
              hour: "2-digit",
              minute: "2-digit",
            })
          : "—",
      ]);
    }
    T1.splice(0, T1.length);
    T2.splice(0, T2.length);
    preferences = await request("/auth/preferences");
    if (preferences.preferences?.theme) {
      S.theme = { light: "claro", dark: "escuro", auto: "auto" }[preferences.preferences.theme];
      applyTheme();
    }
    const localTheme = A.tema;
    A.tema = (value) => {
      (async () => {
        try {
          if (!preferences.preferences) throw Error("Preferências indisponíveis.");
          const next = {
            ...preferences.preferences,
            theme: { claro: "light", escuro: "dark", auto: "auto" }[value],
          };
          preferences = await request("/auth/preferences", "PATCH", {
            schema_version: 1,
            expected_revision: preferences.revision,
            preferences: next,
          });
          localTheme(value);
          render();
        } catch (e) {
          if (e.status === 409) preferences = await request("/auth/preferences");
          error(e);
        }
      })();
      return false;
    };
    await refresh();
    loaded = true;
    const today = new Date(),
      day = today.getDate();
    TODAY = today.toLocaleDateString("pt-BR", { day: "numeric", month: "short", year: "numeric" });
    PER.splice(
      0,
      PER.length,
      ["Este mês", 1, day],
      ["Últimos 7 dias", day - 6, day],
      ["Últimos 3 dias", day - 2, day],
      ["Início do mês", 1, Math.min(day, 10)],
    );
    S.ag = [];
    S.team = [];
    S.iaUso = 0;
    openAction = (k) => {
      if (k === "cliente") return clientForm();
      if (k === "produto") return productForm();
      if (k === "venda") {
        if (!data.clients.length || !data.products.length)
          return toast("Cadastre um cliente e um produto ou serviço primeiro.");
        return form(
          "Nova venda",
          [
            field("c", "Cliente", "", {
              type: "select",
              options: data.clients.map((c) => c.nome),
              req: 1,
            }),
            field("p", "Produto ou serviço", "", {
              type: "select",
              options: data.products.map((p) => p.nome),
              req: 1,
            }),
            field("q", "Quantidade", "1", { req: 1 }),
          ],
          (v) => {
            if (
              data.clients.filter((c) => c.nome === v.c).length !== 1 ||
              data.products.filter((p) => p.nome === v.p).length !== 1
            )
              throw Error("Existem nomes repetidos. Diferencie os cadastros antes de selecionar.");
            return write(
              "/vendas",
              "POST",
              {
                cliente_id: data.clients.find((c) => c.nome === v.c).id,
                produto_id: data.products.find((p) => p.nome === v.p).id,
                quantidade: Number(v.q),
                data: new Date().toLocaleDateString("en-CA"),
                preco: data.products.find((p) => p.nome === v.p).preco,
                pagamento: "Pix",
                desconto: 0,
                status: "Pendente",
              },
              true,
            );
          },
          "Registrar venda",
        );
      }
      if (k === "lanc")
        return form(
          "Novo lançamento",
          [
            field("d", "Descrição", "", { req: 1 }),
            field("c", "Categoria", "", { disabled: true }),
            field("t", "Tipo", "Entrada", { type: "select", options: ["Entrada", "Saída"] }),
            field("v", "Valor (R$)", "", { req: 1, type: "money" }),
          ],
          (v) =>
            write(
              "/financeiro",
              "POST",
              {
                descricao: v.d,
                tipo: v.t === "Entrada" ? "receita" : "despesa",
                valor: money(v.v),
                vencimento: new Date().toLocaleDateString("en-CA"),
                status: "pago",
              },
              true,
            ),
        );
      return info(
        "Recurso local",
        "<p>Esta ação ainda depende de integração. Nenhuma mensagem ou alteração será enviada ao servidor.</p>",
      );
    };
    editAction = (k) =>
      k === "cli"
        ? clientForm(true)
        : k === "prod"
          ? productForm(true)
          : info(
              "Recurso local",
              "<p>Rotinas ainda são simulações; não executam workflows externos.</p>",
            );
    A.vt = async (index) => {
      try {
        const sale = data.sales[+index];
        if (sale.status !== "Pendente")
          throw Error("Esta ação está disponível apenas para vendas pendentes.");
        await write(
          "/vendas/" + sale.id + "/pagar",
          "POST",
          { expected_version: sale.versao },
          true,
        );
        if (await refreshConfirmed()) toast("Pagamento confirmado.");
      } catch (e) {
        error(e);
      }
      return false;
    };
    A.fx = async (index) => {
      try {
        const record = data.finance.filter((f) => f.status === "pago")[+index];
        await write(
          "/financeiro/" + record.id + "/excluir",
          "POST",
          { expected_version: record.versao },
          true,
        );
        if (await refreshConfirmed()) toast("Lançamento excluído no servidor.");
      } catch (e) {
        error(e);
      }
      return false;
    };
    A.salvar = () => {
      toast("Envio não conectado. Nenhuma mensagem foi enviada.");
      return false;
    };
    A.saveuser = () => {
      (async () => {
        try {
          const nome = document.getElementById("u_nome").value.trim();
          await auth.saveProfile({ nome });
          S.user.nome = auth.current.usuario.nome;
          toast("Nome salvo.");
        } catch (e) {
          error(e);
        }
      })();
      return false;
    };
    A.savebiz = () => {
      (async () => {
        try {
          const nome = document.getElementById("b_nome").value.trim(),
            telefone = document.getElementById("b_tel").value.trim();
          await auth.saveProfile({ nome_negocio: nome, configuracao_negocio: { telefone } });
          S.biz.nome = auth.current.negocio.nome;
          S.biz.tel = telefone;
          render();
          toast("Nome e telefone salvos no negócio.");
        } catch (e) {
          error(e);
        }
      })();
      return false;
    };
    for (const action of ["agnew", "agok", "agdel", "eqnew", "eqdel"])
      A[action] = () => {
        toast("Esta função ainda não tem persistência compartilhada. Nenhum dado foi alterado.");
        return false;
      };
    A.k10prd = () => {
      toast("Anexos de catálogo ainda não estão conectados ao envio.");
      return false;
    };
    SEL.stt = () => toast("Atualização de atendimento ainda não conectada ao servidor.");
    A.sg = (value) => {
      if (value === "dados") {
        A.hv();
        return false;
      }
      toast("Esta proteção ainda não está habilitada no servidor.");
      return false;
    };
    const oldRender = render;
    render = () => {
      oldRender();
      const composer = document.querySelector("#ta");
      if (composer) {
        const button = document.querySelector('[data-a^="salvar:"]');
        if (button) {
          button.disabled = true;
          button.title = "Envio e gravação de resposta ainda não habilitados.";
        }
      }
      for (const id of ["b_seg", "b_desc", "b_email", "u_email"]) {
        const input = document.getElementById(id);
        if (input) {
          input.readOnly = true;
          if (input.tagName === "SELECT") input.disabled = true;
          input.title = "Este campo ainda não possui edição compartilhada no servidor.";
        }
      }
      document
        .querySelectorAll(".nhd3")
        .forEach((e) => (e.textContent = "Dados do negócio da sua sessão."));
      // Empty details must never fall back to a synthetic customer.
    };
    A.sgout = () =>
      form("Sair dos outros aparelhos", [field("password", "Senha atual", "", { req: 1 })], (v) =>
        request("/auth/sessions/revoke-others", "POST", { atual: v.password }),
      );
    A.sair = () => {
      auth.logout("/frontend/socialmei-app.html").catch(error);
      return false;
    };
    render();
    root.hidden = false;
  }
  const ready = initialize().catch((e) => {
    root.hidden = false;
    root.textContent =
      "Não foi possível carregar sua sessão. Atualize a página para tentar novamente.";
    console.error("V22 initialization failed");
  });
  return {
    remote,
    ready,
    request,
    refresh,
    write,
    inPeriod,
    inFinancialPeriod,
    get identity() {
      return auth.current;
    },
    thread(id) {
      const row = inbox.find((r) => "me-" + r.id === id);
      return row
        ? (row.messages || []).map((m) => [
            0,
            m.text,
            new Date(m.occurred_at).toLocaleTimeString("pt-BR", {
              hour: "2-digit",
              minute: "2-digit",
            }),
          ])
        : [];
    },
    get clients() {
      return data.clients;
    },
  };
})();
