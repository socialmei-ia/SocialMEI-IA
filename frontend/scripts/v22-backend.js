/* V22 transport bridge. Visual templates and animation code remain owned by V22. */
window.SocialMEIV22 = (() => {
  const auth = window.SocialMEIAuth;
  const remote = auth.remote;
  const root = document.getElementById("app");
  const request = (...args) => auth.request(...args);
  let loaded = false;
  let inbox = [];
  let inboxScope = null;
  let preferences = null;
  let operationBusy = false;
  let data = { clients: [], products: [], sales: [], finance: [] };
  let dataScope = null;
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
    if (!auth.current) throw Error("Sua sessão mudou. Entre novamente.");
    const expectedScope = identityKey();
    const [clients, products, sales, finance] = await Promise.all(
      ["/clientes", "/produtos", "/vendas", "/financeiro"].map((p) => request(p)),
    );
    if (!auth.current || identityKey() !== expectedScope)
      throw Error("Sua sessão mudou. Atualize os dados do negócio atual.");
    if (![clients, products, sales, finance].every(Array.isArray))
      throw Error("Resposta de gestão inválida.");
    dataScope = expectedScope;
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
        p.categoria || p.tipo,
        p.preco,
        p.status === "Ativo" ? 1 : 0,
        p.descricao || "",
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
      ...finance.flatMap((f) => {
        const common = [f.descricao, f.categoria || "Sem categoria", f.tipo === "receita" ? 1 : 0];
        if (f.parcelas?.length)
          return f.parcelas.map((item) => [date(item.data), ...common, Number(item.valor), f.id, true]);
        if (f.status === "pago" && f.data_pagamento)
          return [[date(f.data_pagamento), ...common, f.valor, f.id, false]];
        return [];
      }),
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
  const operationKey = () => "socialmei-v22-operation:" + identityKey();
  function pendingOperation() {
    const raw = localStorage.getItem(operationKey());
    if (!raw) return null;
    try {
      const pending = JSON.parse(raw);
      const { path, method, payload } = JSON.parse(pending.signature);
      if (
        !(
          /^\/(vendas|financeiro)(\/[1-9]\d*(\/(registrar|pagar|cancelar|excluir|liquidacoes|estornar-parcela))?)?$/.test(path) ||
          (method === "POST" && /^\/financeiro\/de-venda\/[1-9]\d*$/.test(path)) ||
          (method === "POST" && /^\/opportunities\/[a-f0-9-]{36}\/convert$/i.test(path))
        ) ||
        !["POST", "PATCH"].includes(method) ||
        !payload ||
        !/^[a-f0-9-]{36}$/i.test(pending.packet?.operation_id) ||
        JSON.stringify({ ...payload, operation_id: pending.packet.operation_id }) !==
          JSON.stringify(pending.packet)
      )
        throw Error();
      return { ...pending, path, method, stored: raw };
    } catch (_) {
      throw Error("Não foi possível ler a operação pendente. Preserve os dados e peça suporte.");
    }
  }
  function paintPendingOperation() {
    const view = document.getElementById("v");
    if (!view) return;
    view.querySelectorAll("[data-operation-recovery]").forEach((notice) => notice.remove());
    if (operationBusy || !localStorage.getItem(operationKey())) return;
    const section = document.createElement("section");
    section.dataset.operationRecovery = "true";
    section.className = "pg row wr";
    section.setAttribute("aria-label", "Operação sem confirmação");
    const message = document.createElement("p");
    message.textContent =
      "Há uma venda ou lançamento sem confirmação. Confira o resultado antes de registrar outra operação.";
    message.setAttribute("role", "status");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn o";
    button.textContent = "Conferir operação pendente";
    button.onclick = () => {
      try {
        const pending = pendingOperation();
        if (!pending) return render();
        const identity = identityKey();
        const key = operationKey();
        const title = pending.path.startsWith("/financeiro") ? "Lan\u00e7amento financeiro" : "Venda";
        info(
          "Conferir operação pendente",
          "<p>" +
            title +
            ": a consulta repetirá o pedido original com o mesmo identificador, mesmo se a data ou os dados exibidos mudaram.</p><p>O servidor devolverá o resultado já registrado ou concluirá o pedido se ele ainda não foi aceito.</p>",
        );
        const confirm = document.createElement("button");
        confirm.type = "button";
        confirm.className = "btn";
        confirm.textContent = "Confirmar consulta da operação";
        confirm.onclick = async () => {
          if (operationBusy) return;
          if (identity !== identityKey() || localStorage.getItem(key) !== pending.stored) {
            dlg().close();
            render();
            toast("A sessão ou a operação pendente mudou. Confira novamente antes de continuar.");
            return;
          }
          operationBusy = true;
          confirm.disabled = true;
          try {
            await request(pending.path, pending.method, pending.packet);
            if (identity !== identityKey()) return;
            if (localStorage.getItem(key) === pending.stored) localStorage.removeItem(key);
            dlg().close();
            loaded = true;
            if (await refreshConfirmed()) toast("Operação confirmada no servidor.");
          } catch (e) {
            if (identity !== identityKey()) return;
            if ([400, 403, 404, 409, 422].includes(e.status)) {
              if (localStorage.getItem(key) === pending.stored) localStorage.removeItem(key);
              dlg().close();
              await refreshConfirmed();
            }
            error(e);
          } finally {
            operationBusy = false;
            confirm.disabled = false;
            if (identity === identityKey()) paintPendingOperation();
          }
        };
        dlg().append(confirm);
      } catch (e) {
        error(e);
      }
    };
    section.append(message, button);
    view.prepend(section);
  }
  async function write(path, method, payload, operation = false) {
    if (!auth.current || dataScope !== identityKey())
      throw Error("Sua sessão mudou. Recarregue os dados antes de salvar.");
    if (!loaded) throw Error("Aguarde o carregamento dos dados.");
    const expectedScope = identityKey();
    let key,
      stored,
      packet = payload;
    if (operation) {
      if (operationBusy) throw Error("Aguarde a confirmação da operação em andamento.");
      key = operationKey();
      const pending = pendingOperation();
      const signature = JSON.stringify({ path, method, payload });
      if (pending && pending.signature !== signature)
        throw Error(
          "Existe uma operação sem confirmação. Use Conferir operação pendente antes de iniciar outra.",
        );
      packet = pending?.packet || { ...payload, operation_id: crypto.randomUUID() };
      stored = JSON.stringify({ signature, packet });
      localStorage.setItem(key, stored);
      operationBusy = true;
    }
    try {
      const result = await request(path, method, packet);
      if (!auth.current || identityKey() !== expectedScope)
        throw Error("Sua sessão mudou. Confira a operação no negócio de origem antes de repetir.");
      if (key && localStorage.getItem(key) === stored) localStorage.removeItem(key);
      return result;
    } catch (e) {
      if (
        key &&
        [400, 403, 404, 409, 422].includes(e.status) &&
        localStorage.getItem(key) === stored
      )
        localStorage.removeItem(key);
      throw e;
    } finally {
      if (key) {
        operationBusy = false;
        if (auth.current && identityKey() === expectedScope && localStorage.getItem(key)) {
          const dialog = document.querySelector("dialog[open]");
          dialog?.close();
          render();
        }
      }
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
      if (f.choices) {
        const input = element.querySelector("#f_" + f.id);
        input.replaceChildren(...f.choices.map((choice) => new Option(choice.label, choice.value)));
      }
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
  function recordChoices(records, optional = false) {
    const counts = new Map();
    for (const record of records) counts.set(record.nome, (counts.get(record.nome) || 0) + 1);
    const choices = records.map((record) => ({
      value: String(record.id),
      label: record.nome + (counts.get(record.nome) > 1 ? " · #" + record.id : ""),
    }));
    return optional ? [{ value: "", label: "Sem cliente" }, ...choices] : choices;
  }
  function clientForm(edit = false) {
    const c = edit ? data.clients[S.cli] : null;
    form(
      edit ? "Editar cliente" : "Novo cliente",
      [
        field("n", "Nome", c?.nome || "", { req: 1 }),
        field("e", "E-mail", c?.email || "", { type: "email" }),
        field("tel", "Telefone", c?.telefone || "", { type: "tel" }),
        field("ig", "Instagram", c?.instagram || ""),
        field("o", "Observações", c?.observacao || "", { type: "textarea" }),
      ],
      (v) =>
        write("/clientes" + (c ? "/" + c.id : ""), c ? "PATCH" : "POST", {
          nome: v.n,
          email: v.e,
          ...(!c || v.tel !== (c.telefone || "") ? { telefone: v.tel || null } : {}),
          ...(!c || v.ig !== (c.instagram || "") ? { instagram: v.ig || null } : {}),
          observacao: v.o,
          ...(c ? { expected_version: c.versao } : {}),
        }),
    );
  }

  async function clientHistory() {
    if (!auth.current || dataScope !== identityKey()) return;
    const customer = data.clients[S.cli];
    if (!customer) return;
    const scope = identityKey();
    info("Histórico do cliente", '<p data-history-status role="status">Consultando histórico…</p>');
    const original = dlg().querySelector("[data-history-status]");
    try {
      const result = await request("/clientes/" + customer.id + "/historico");
      if (!auth.current || identityKey() !== scope || !dlg().open || !original.isConnected) return;
      const stamp = (value) => value
        ? new Date(value.length === 10 ? value + "T12:00:00" : value).toLocaleDateString("pt-BR")
        : "Sem data";
      const appointmentState = { pending: "Pendente", confirmed: "Confirmado", completed: "Concluído", cancelled: "Cancelado", no_show: "Ausência" };
      const opportunityState = { open: "Em andamento", won: "Venda realizada", lost: "Não avançou" };
      const groups = [
        ["Conversas vinculadas", result.conversas, (row) => [row.channel === "whatsapp" ? "WhatsApp" : "Instagram", row.contact_name, stamp(row.last_message_at)]],
        ["Agendamentos", result.agendamentos, (row) => [row.service_name, stamp(row.scheduled_for), appointmentState[row.status] || row.status]],
        ["Vendas", result.vendas, (row) => [row.item, stamp(row.data), row.status, brl(Number(row.valor))]],
        ["Oportunidades", result.oportunidades, (row) => [row.title, stamp(row.updated_at), opportunityState[row.outcome] || row.outcome]],
      ];
      const content = document.createDocumentFragment();
      for (const [label, items, line] of groups) {
        const title = document.createElement("h3");
        title.textContent = label;
        content.append(title);
        const list = document.createElement("ul");
        for (const row of items) {
          const item = document.createElement("li");
          item.textContent = line(row).filter(Boolean).join(" · ");
          list.append(item);
        }
        if (items.length) content.append(list);
        else {
          const empty = document.createElement("p");
          empty.textContent = "Nenhum registro.";
          content.append(empty);
        }
      }
      original.replaceWith(content);
    } catch (error) {
      if (auth.current && identityKey() === scope && original.isConnected)
        original.textContent = error.message || "Não foi possível consultar.";
    }
  }
  document.addEventListener("click", (event) => {
    if (event.target.closest?.("[data-customer-history]")) void clientHistory();
  });


  const canWriteFinance = () => ["owner", "admin", "member"].includes(auth.current?.papel);
  function financeForm(record) {
    if (!canWriteFinance()) return;
    const today = new Date().toLocaleDateString("sv-SE");
    form(
      record ? "Corrigir lan\u00e7amento em aberto" : "Novo lan\u00e7amento",
      [
        field("d", "Descri\u00e7\u00e3o", record?.descricao || "", { req: 1 }),
        field("cc", "Categoria", record?.categoria || "", { max: 80 }),
        field("t", "Tipo", record?.tipo === "despesa" ? "Sa\u00edda" : "Entrada", {
          type: "select",
          options: ["Entrada", "Sa\u00edda"],
        }),
        field("v", "Valor (R$)", record ? String(record.valor).replace(".", ",") : "", { req: 1, type: "money" }),
        field("due", "Vencimento", record?.vencimento || today, { req: 1, type: "date" }),
        ...(record ? [] : [field("st", "Situa\u00e7\u00e3o", "Em aberto", {
          type: "select",
          options: ["Em aberto", "J\u00e1 pago"],
        })]),
      ],
      (v) =>
        write(
          "/financeiro" + (record ? "/" + record.id : ""),
          record ? "PATCH" : "POST",
          {
            descricao: v.d,
            categoria: v.cc,
            tipo: v.t === "Entrada" ? "receita" : "despesa",
            valor: money(v.v),
            vencimento: v.due,
            ...(record
              ? { expected_version: record.versao, cliente_id: record.cliente_id, pessoa: record.pessoa }
              : { status: v.st === "J\u00e1 pago" ? "pago" : "aberto" }),
          },
          true,
        ),
    );
  }

  function paintOpenFinance() {
    if (location.hash !== "#/negocio/financeiro") return;
    const view = document.getElementById("v");
    if (!view || !auth.current || dataScope !== identityKey() || view.querySelector("[data-open-finance]")) return;
    if (!canWriteFinance()) {
      view.querySelectorAll('button[data-a="novo:lanc"], button[data-a^="fx:"]').forEach((button) => {
        button.disabled = true;
        button.title = "Acesso somente leitura";
      });
    }
    const section = document.createElement("section");
    section.className = "pg";
    section.dataset.openFinance = "true";
    const title = document.createElement("h2");
    title.textContent = "Contas em aberto";
    section.append(title);
    if (canWriteFinance()) {
      const activeSales = new Set(data.finance.filter((entry) => entry.venda_id != null).map((entry) => entry.venda_id));
      const choices = data.sales.filter((sale) => sale.status === "Pendente" && sale.valor > 0 && !activeSales.has(sale.id));
      if (choices.length) {
        const link = document.createElement("button");
        link.type = "button";
        link.className = "btn o";
        link.textContent = "Criar recebível de venda";
        const opened = identityKey();
        link.onclick = () => {
          if (!auth.current || identityKey() !== opened || !canWriteFinance()) return;
          form(
            "Criar recebível de venda",
            [
              field("sale", "Venda pendente ainda sem recebível", "", {
                type: "select", req: 1, options: [""],
                choices: [{ value: "", label: "Selecione" }, ...choices.map((sale) => ({
                  value: String(sale.id), label: "#" + sale.id + " · " + sale.item + " · " + brl(sale.valor),
                }))],
              }),
              field("due", "Vencimento", new Date().toLocaleDateString("sv-SE"), { type: "date", req: 1 }),
            ],
            (values) => {
              const sale = choices.find((entry) => String(entry.id) === values.sale);
              if (!sale) throw Error("Selecione uma venda da lista.");
              if (!window.confirm("Confirme que esta venda ainda não foi registrada como recebível avulso.")) throw Error("Operação cancelada.");
              return write("/financeiro/de-venda/" + sale.id, "POST", {
                expected_version: sale.versao, vencimento: values.due,
              }, true);
            },
          );
        };
        section.append(link);
      }
    }
    const records = data.finance.filter((row) => ["aberto", "atrasado"].includes(row.status));
    if (!records.length) {
      const empty = document.createElement("p");
      empty.textContent = "Nenhuma conta a pagar ou a receber.";
      section.append(empty);
    }
    const active = identityKey();
    for (const row of records) {
      const line = document.createElement("div");
      line.className = "row sp wr";
      const label = document.createElement("p");
      const kind = row.tipo === "receita" ? "A receber" : "A pagar";
      const balance = (Math.round(Number(row.valor) * 100) - Math.round(Number(row.liquidado_parcial || 0) * 100)) / 100;
      label.textContent = kind + " \u00b7 " + row.descricao + " \u00b7 " + brl(balance) + " em aberto \u00b7 vencimento " + date(row.vencimento);
      line.append(label);
      if (canWriteFinance()) {
        const buttons = document.createElement("div");
        buttons.className = "row wr";
        const action = (text, callback) => {
          const button = document.createElement("button");
          button.className = "btn o sm2";
          button.type = "button";
          button.textContent = text;
          button.onclick = () => {
            if (auth.current && identityKey() === active && canWriteFinance()) callback();
          };
          buttons.append(button);
        };
        if (!Number(row.liquidado_parcial) && !row.venda_id) action("Corrigir", () => financeForm(row));
        action("Registrar parcela", () => form(
          "Registrar parcela",
          [
            field("v", "Valor da parcela (R$)", "", { req: 1, type: "money" }),
            field("pd", "Data de pagamento", new Date().toLocaleDateString("sv-SE"), { req: 1, type: "date" }),
          ],
          (values) => write("/financeiro/" + row.id + "/liquidacoes", "POST", {
            expected_version: row.versao, valor: String(money(values.v)), data: values.pd,
          }, true),
        ));
        for (const [text, permission, route] of [
          [row.tipo === "receita" ? "Registrar recebimento" : "Registrar pagamento",
            "Confirma o registro interno da quita\u00e7\u00e3o de \"" + row.descricao + "\"?", "pagar"],
          ["Cancelar conta", "Cancelar a conta em aberto \"" + row.descricao + "\"?", "excluir"],
        ]) {
          if (route === "excluir" && Number(row.liquidado_parcial)) continue;
          action(text, async () => {
            if (!window.confirm(permission)) return;
            try {
              await write("/financeiro/" + row.id + "/" + route, "POST", { expected_version: row.versao }, true);
              if (auth.current && identityKey() === active && (await refreshConfirmed())) toast("Lan\u00e7amento atualizado.");
            } catch (failure) {
              if (auth.current && identityKey() === active) error(failure);
            }
          });
        }
        line.append(buttons);
      }
      line.append(financeHistoryButton(row, active));
      section.append(line);
    }
    const settled = data.finance.filter((row) => row.status === "pago" && Number(row.liquidado_parcial));
    if (settled.length) {
      const details = document.createElement("details"),
        summary = document.createElement("summary");
      summary.textContent = "Contas quitadas com parcelas";
      details.append(summary);
      for (const row of settled) details.append(financeHistoryButton(row, active));
      section.append(details);
    }
    view.append(section);
  }

  function financeHistoryButton(row, scope) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn o sm2";
    button.textContent = "Parcelas: " + row.descricao;
    button.onclick = async () => {
      const active = () => auth.current && identityKey() === scope;
      if (!active()) return;
      info("Histórico de parcelas", '<p data-finance-history role="status">Consultando…</p>');
      const original = dlg().querySelector("[data-finance-history]");
      try {
        const { items } = await request("/financeiro/" + row.id + "/liquidacoes");
        if (!active() || !dlg().open || !original.isConnected) return;
        const list = document.createElement("ul");
        for (const item of items) {
          const entry = document.createElement("li");
          entry.textContent = date(item.data) + " · " + brl(Number(item.valor)) +
            (item.estornado_em ? " · Corrigida: " + item.motivo_estorno : "");
          if (!item.estornado_em && canWriteFinance()) {
            const reverse = document.createElement("button");
            reverse.type = "button";
            reverse.className = "btn o sm2";
            reverse.textContent = "Estornar registro";
            reverse.onclick = () => {
              if (!active()) return;
              dlg().close();
              form(
                "Estornar registro da parcela",
                [field("why", "Motivo da correção", "", { req: 1, max: 300 })],
                ({ why }) => write("/financeiro/" + row.id + "/estornar-parcela", "POST", {
                  expected_version: row.versao, parcela_id: item.id, motivo: why,
                }, true),
                "Confirmar correção",
              );
            };
            entry.append(reverse);
          }
          list.append(entry);
        }
        if (items.length) original.replaceWith(list);
        else original.textContent = "Nenhuma parcela registrada.";
      } catch (failure) {
        if (active() && original.isConnected) original.textContent = failure.message;
      }
    };
    return button;
  }

  function productForm(edit = false) {
    const p = edit ? data.products[S.prod] : null;
    form(
      edit ? "Editar produto ou serviço" : "Novo produto ou serviço",
      [
        field("n", "Nome", p?.nome || "", { req: 1 }),
        field("c", "Categoria", p?.categoria || ""),
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
        field("d", "Descrição", p?.descricao || "", { type: "textarea" }),
        field("a", "Disponível", p ? p.status === "Ativo" : true, { type: "check" }),
      ],
      (v) => {
        const product = {
          nome: v.n,
          categoria: v.c || "",
          descricao: v.d || "",
          tipo: v.t,
          preco: money(v.p),
          custo: money(v.k || "0"),
          status: v.a ? "Ativo" : "Inativo",
          ...(v.t === "Produto" && p?.duracao_minutos != null ? { duracao_minutos: null } : {}),
          ...(v.t === "Produto"
            ? { estoque: Number(v.e), minimo: Number(v.m) }
            : { estoque: null, minimo: null }),
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
    const dialog = dlg(),
      type = dialog.querySelector("#f_t");
    const inventory = () => {
      const service = type.value === "Serviço";
      for (const id of ["#f_e", "#f_m"]) {
        const input = dialog.querySelector(id);
        input.disabled = service;
        input.title = service ? "Serviços não possuem estoque." : "";
      }
    };
    type.addEventListener("change", inventory);
    inventory();
  }
  // Incoming Meta webhooks persist server-side. Poll while the inbox is visible
  // so messages appear without requiring a full page reload.
  /* v7.9 · Fotos de perfil e iniciais. Somente data URI JPEG/PNG/WebP, com limite de tamanho. */
  const AVATAR_MAX = 600000;
  const safeAvatar = (value) =>
    typeof value === "string" &&
    value.length <= AVATAR_MAX &&
    /^data:image\/(?:jpeg|png|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(value)
      ? value
      : "";
  /* Iniciais por letras Unicode: ignora emojis, números e símbolos; primeira e última palavra. */
  const initialsOf = (name) => {
    const words = String(name ?? "")
      .normalize("NFC")
      .split(/\s+/)
      .map((w) => (w.match(/\p{L}/u) || [""])[0])
      .filter(Boolean);
    if (!words.length) return "?";
    const pair = words.length > 1 ? words[0] + words[words.length - 1] : words[0];
    return pair.toLocaleUpperCase("pt-BR");
  };
  const PALETTE = [
    ["#e4dcff", "#4a3aa8"],
    ["#dbe8ff", "#1d4fb8"],
    ["#dcf3df", "#2a7a3a"],
    ["#fddede", "#a62b2b"],
    ["#fff0d6", "#8a5a00"],
    ["#d9f2f2", "#13686b"],
  ];
  const paletteFor = (key) => {
    let h = 0;
    for (const ch of String(key)) h = (h * 31 + ch.codePointAt(0)) >>> 0;
    return PALETTE[h % PALETTE.length];
  };
  /* Estado real da conversa, derivado só das mensagens que o servidor devolveu. */
  const pick = (row, keys) => {
    for (const k of keys) {
      const v = row?.[k];
      if (typeof v === "string" && v.trim()) return v.trim();
    }
    return "";
  };
  function smThreadMessages(row,id){
    const seen=new Set();
    return [...(row.messages||[]),...(window.SocialMEIInstagramDirect?.confirmed(id)||[]),...(window.SocialMEIWhatsAppReplies?.confirmed(id)||[])]
      .filter(m=>{if(m.id==null)return true;const key=String(m.id);if(seen.has(key))return false;seen.add(key);return true;})
      .sort((a,b)=>new Date(a.occurred_at)-new Date(b.occurred_at));
  }
  function conversationMeta(row) {
    const messages = row.messages || [];
    const last = messages.at(-1);
    const incoming = messages.filter((m) => m.direction !== "outgoing");
    const outgoing = messages.filter((m) => m.direction === "outgoing");
    const lastIn = incoming.at(-1);
    const lastOut = outgoing.at(-1);
    return {
      lastDirection: last?.direction === "outgoing" ? "out" : "in",
      lastAt: last?.occurred_at || null,
      lastInAt: lastIn?.occurred_at || null,
      lastOutAt: lastOut?.occurred_at || null,
      firstAt: messages[0]?.occurred_at || null,
      incoming: incoming.length,
      outgoing: outgoing.length,
      phone: pick(row, ["contact_phone", "phone", "wa_id"]),
      handle: pick(row, ["contact_username", "contact_handle", "username", "handle"]),
      origin: row.origin || "",
      unreadCount: row.unread_count || 0,
      pinned: row.pinned === true,
      snoozedUntil: row.snoozed_until || null,
    };
  }
  let inboxPolling = false;
  let inboxReadDone = null;
  const inboxSettled = () => inboxReadDone || Promise.resolve();
  let inboxFingerprint = "";
  let inboxCapabilities = null;
  /* v7.9 · saúde da caixa (somente leitura para a interface) e conclusões marcadas neste navegador. */
  let inboxState = "loading";
  let inboxLastOk = null;
  const DONE_KEY = "smei-v79-done";
  const readDone = () => {
    try {
      const v = JSON.parse(localStorage.getItem(DONE_KEY) || "{}");
      return v && typeof v === "object" && !Array.isArray(v) ? v : {};
    } catch {
      return {};
    }
  };
  /* "Concluída" é uma marcação local; reabre sozinha se o cliente escrever depois dela. */
  const isDone = (id, meta) => {
    const at = readDone()[id];
    return !!at && !(meta?.lastInAt && Date.parse(meta.lastInAt) > at);
  };
  const listTime = (iso) => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const n = new Date();
    const days = Math.round(
      (new Date(n.getFullYear(), n.getMonth(), n.getDate()) -
        new Date(d.getFullYear(), d.getMonth(), d.getDate())) /
        864e5,
    );
    if (days <= 0) return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    if (days === 1) return "Ontem";
    if (days < 7) return d.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
    return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  };
  let smInboxEpoch=0;
  // Keep the composer and loaded media nodes alive during background polling.
  let smDeferred=false;
  function smInboxPaint(){
    if(!loaded||!H.startsWith('/caixa'))return;
    const current=H.split('/')[2];
    if(current&&!C.some(c=>c[0]===current)){smDeferred=false;go('/caixa');return;}
    const search=document.querySelector('#v .cl input[data-q],#v .cx4-mob input[data-q]');
    const playing=[...document.querySelectorAll('#v .ms audio')].some(a=>!a.paused&&!a.ended);
    const busy=playing||!!document.querySelector('#v .ms button[data-sm-media]:disabled')||document.activeElement?.id==='ta'||document.activeElement?.id==='k10q'||(search&&(search===document.activeElement||search.value));
    if(busy){
      smDeferred=true;
      const pane=document.querySelector('#v .cl');
      if(pane&&!(search&&(search===document.activeElement||search.value))){
        const nav=pane.querySelector('.cx4-rows');
        const tmp=document.createElement('div');tmp.innerHTML=cxPane(current||null);
        const next=tmp.querySelector('.cx4-rows');
        if(nav&&next)nav.innerHTML=next.innerHTML;
      }
      return;
    }
    smDeferred=false;
    const ms=document.querySelector('#v .ms');
    if(ms&&ms.scrollHeight-ms.scrollTop-ms.clientHeight>80){S.k10sv=['#v .ms','#v .cl','#v .cx'].map(x=>document.querySelector(x)?.scrollTop||0);}
    else if(ms)S.k10bot=true;
    render();
  }
  async function refreshInbox({ silent = false } = {}) {
    if (inboxPolling || !remote || !auth.current) return;
    inboxPolling = true;
    let finishInboxRead;
    inboxReadDone = new Promise(resolve => { finishInboxRead = resolve; });
    const workspace = auth.current.negocio.id;
    const scope = identityKey();
    const epoch=smInboxEpoch;
    const sameSession = () => auth.current && identityKey() === scope && epoch===smInboxEpoch;
    try {
      const cap = await request("/message-enrichment/capabilities");
      if (!sameSession()) return;
      const available = cap.mode === "stub" || cap.instagram_inbox || cap.waha_inbox;
      const result = available
        ? await request("/message-enrichment/conversations")
        : { workspace_id: workspace, items: [] };
      if (!sameSession()) return;
      if (result.workspace_id !== workspace) throw Error("Resposta de outro negócio.");
      if (!Array.isArray(result.items)) throw Error("Resposta da Caixa Unificada inválida.");
      inboxCapabilities = cap;
      inboxState = available ? "ok" : "unavailable";
      inboxLastOk = Date.now();
      const fingerprint = JSON.stringify([
        scope,
        cap.mode,
        !!cap.instagram_inbox,
        !!cap.waha_inbox,
        result.items.map((row) => [
          row.id,
          row.revision,
          row.unread_count,
          row.unread,
          row.last_inbound_id,
          row.pinned,
          row.snoozed_until,
          row.origin,
          row.account_ref,
          row.contact_name,
          row.avatar_version,
          safeAvatar(row.contact_avatar).length,
          row.messages?.map((message) => [
            message.id,
            message.provider_analysis?.source,
            message.provider_analysis?.sentiment,
            message.provider_analysis?.confidence,
            message.provider_analysis?.explanation,
            message.attachments || [],
          ]),
        ]),
      ]);
      if (fingerprint === inboxFingerprint) {if(silent&&smDeferred)smInboxPaint();return;}
      inboxFingerprint = fingerprint;
      inbox = result.items;
      inboxScope = scope;
      C.splice(0, C.length);
      for (const row of inbox) {
        const messages = row.messages || [];
        const last = messages.at(-1);
        if (!last) continue;
        const [bg, fg] = paletteFor(row.contact_name || row.id);
        C.push([
          "me-" + row.id,
          row.contact_name,
          esc(initialsOf(row.contact_name)),
          bg,
          fg,
          last.text || "",
          row.channel === "instagram" ? "ig" : "wa",
          isDone("me-" + row.id, conversationMeta(row)) ? "Concluído" : "Aberto",
          listTime(last.occurred_at),
          row.unread === true,
          /* [10] foto real validada ("" quando ausente) e [11] metadados reais da conversa. */
          safeAvatar(row.contact_avatar),
          conversationMeta(row),
        ]);
      }
      if (silent && sameSession()) smInboxPaint();
    } catch (e) {
      if (!sameSession()) return;
      inboxState = [403, 503].includes(e.status) ? "unavailable" : "error";
      if (silent) smInboxPaint();
      if (!silent && ![403, 503].includes(e.status)) throw e;
    } finally {
      inboxPolling = false;
      inboxReadDone = null;
      finishInboxRead();
    }
  }
  // Never poll while hidden or without a session. No duplicate timers.
  if (remote)
    window.setInterval(() => {
      if (!document.hidden && loaded && H.startsWith("/caixa")) refreshInbox({ silent: true });
    }, 6000);
  function paintInboxLabels() {
    if (!H.startsWith("/caixa")) return;
    // Replace only label text; retain the native icons, layout and motion hooks.
    const label = (selector, value) => {
      const element = document.querySelector(selector);
      if (!element) return;
      const node = [...element.childNodes].find((child) => child.nodeType === 3);
      if (node) node.textContent = value;
      else element.appendChild(document.createTextNode(value));
    };
    const receiving = inboxCapabilities?.instagram_inbox || inboxCapabilities?.waha_inbox;
    const status = receiving
      ? "Recebimento habilitado no servidor"
      : inboxCapabilities?.mode === "stub"
        ? "Mensagens sintéticas de teste"
        : inboxCapabilities
          ? "Recebimento não habilitado"
          : "Recebimento não confirmado";
    label(".pg > .row.sp.wr > .row.wr > .pill", "Caixa do negócio");
    label(".pg > .row.sp.wr > .row.wr > .m.sm", status);
    const dot = document.querySelector(".pg > .row.sp.wr > .row.wr > .m.sm > .dot");
    if (dot) {
      dot.classList.toggle("g", !!receiving);
      dot.classList.toggle("y", !receiving);
    }
    const row = inbox.find((item) => H === "/caixa/me-" + item.id);
    if (!row) return;
    const provider = ["instagram", "waha"].includes(row.origin);
    const channel = row.channel === "instagram" ? "Instagram" : "WhatsApp";
    label(
      ".ct > .hd > .row > .row > div > .m.sm",
      `${channel} · ${provider ? "recebido no servidor" : "mensagem sintética de teste"}`,
    );
    label(".ct > .hd > .wn > b", "Envio indisponível");
    label(
      ".ct > .hd > .wn > .m",
      provider ? "Mensagens recebidas salvas no servidor." : "Conversa sintética; nada é enviado.",
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
    S.biz.seg = "";
    S.biz.desc = "";
    S.biz.logo = null;
    S.biz.tel = auth.current.negocio.configuracao?.telefone || "";
    S.biz.horario = auth.current.negocio.configuracao?.horario || "";
    /* SM_INSTAGRAM_LOGO_V2 */
    if (/^data:image\/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(auth.current.negocio.configuracao?.instagram_profile?.avatar || "")) { S.biz.logo = auth.current.negocio.configuracao.instagram_profile.avatar; }
    try {
      const business = await request("/workspace-profile");
      S.biz.seg = business.profile?.activity || "";
    } catch (e) {
      if (![403, 404, 503].includes(e.status)) throw e;
    }
    C.splice(0, C.length);
    await refreshInbox();
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
        if (!data.products.length) return toast("Cadastre um produto ou serviço primeiro.");
        return form(
          "Nova venda",
          [
            field("c", "Cliente (opcional)", "", {
              type: "select",
              options: ["", ...data.clients.map((c) => c.nome)],
              choices: recordChoices(data.clients, true),
            }),
            field("p", "Produto ou serviço", "", {
              type: "select",
              options: data.products.map((p) => p.nome),
              choices: recordChoices(data.products),
              req: 1,
            }),
            field("q", "Quantidade", "1", { req: 1 }),
          ],
          (v) => {
            const customer = v.c ? data.clients.find((c) => String(c.id) === v.c) : null;
            const product = data.products.find((p) => String(p.id) === v.p);
            if ((v.c && !customer) || !product)
              throw Error(
                "Selecione um cadastro disponível neste negócio. Atualize se a lista mudou.",
              );
            return write(
              "/vendas",
              "POST",
              {
                cliente_id: customer ? customer.id : null,
                produto_id: product.id,
                quantidade: Number(v.q),
                data: new Date().toLocaleDateString("en-CA"),
                preco: product.preco,
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
      if (k === "lanc") return financeForm();
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
        const cash = F[+index];
        if (!cash || cash[6]) return false;
        const record = data.finance.find((row) => row.id === cash[5]);
        if (!canWriteFinance() || !record || !window.confirm("Cancelar este lan\u00e7amento registrado?")) return false;
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
            telefone = document.getElementById("b_tel").value.trim(),
            horario = (document.getElementById("b_horario")?.value ?? S.biz.horario ?? "").trim();
          await auth.saveProfile({
            nome_negocio: nome,
            configuracao_negocio: { telefone, horario },
          });
          S.biz.nome = auth.current.negocio.nome;
          S.biz.tel = telefone;
          S.biz.horario = horario;
          render();
          toast("Dados e horário de funcionamento salvos no negócio.");
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
      paintPendingOperation();
      paintOpenFinance();
      const phone = document.getElementById("b_tel");
      if (phone && !document.getElementById("b_horario")) {
        const field = document.createElement("div"),
          label = document.createElement("label"),
          input = document.createElement("input");
        label.htmlFor = "b_horario";
        label.textContent = "Horário de funcionamento";
        input.id = "b_horario";
        input.className = "in";
        input.type = "text";
        input.maxLength = 160;
        input.value = S.biz.horario || "";
        input.placeholder = "Ex.: segunda a sexta, 09:00–18:00";
        field.append(label, input);
        phone.insertAdjacentElement("afterend", field);
      }
      paintInboxLabels();
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
    get searchScope() {
      return {
        records: !!auth.current && dataScope === identityKey(),
        inbox: !!auth.current && inboxScope === identityKey(),
      };
    },
    thread(id) {
      const row =
        auth.current && inboxScope === identityKey()
          ? inbox.find((r) => "me-" + r.id === id)
          : null;
      return row
        ? smThreadMessages(row,id)
            .map((m) => [
              m.direction === "outgoing" ? 1 : 0,
              m.text,
              new Date(m.occurred_at).toLocaleTimeString("pt-BR", {
                hour: "2-digit",
                minute: "2-digit",
              }),
              m.direction === "outgoing"
                ? m.provider === "waha"
                  ? "Aceita para envio · entrega não verificada"
                  : "Aceita pela Meta · entrega não verificada"
                : "",
              m.occurred_at,
              m.id ?? null,
              m.attachments || [],
            ])
        : [];
    },
    get clients() {
      return auth.current && dataScope === identityKey() ? data.clients : [];
    },
    get products() {
      return auth.current && dataScope === identityKey() ? data.products : [];
    },
    /* v7.0.1: vendas do escopo atual com cliente_id (somente leitura); null quando o escopo mudou. */
    get sales() {
      return auth.current && dataScope === identityKey() ? data.sales : null;
    },
    /* v7.9 · Resumo real do atendimento: inclui respostas já confirmadas pelos módulos de envio. */
    stateOf(id) {
      const row =
        auth.current && inboxScope === identityKey()
          ? inbox.find((r) => "me-" + r.id === id)
          : null;
      if (!row) return null;
      const all = smThreadMessages(row,id);
      const last = all.at(-1);
      const out = all.filter((m) => m.direction === "outgoing");
      const inn = all.filter((m) => m.direction !== "outgoing");
      return {
        total: all.length,
        incoming: inn.length,
        outgoing: out.length,
        lastDirection: last?.direction === "outgoing" ? "out" : "in",
        lastAt: last?.occurred_at || null,
        lastInAt: inn.at(-1)?.occurred_at || null,
        lastOutAt: out.at(-1)?.occurred_at || null,
        firstAt: all[0]?.occurred_at || null,
        revision: row.revision,
      };
    },
    inboxHealth() {
      return {
        state: inboxState,
        lastOk: inboxLastOk,
        mode: inboxCapabilities?.mode || null,
        receiving: !!(inboxCapabilities?.instagram_inbox || inboxCapabilities?.waha_inbox),
      };
    },
    async hideConversation(id) {
      const scope=identityKey();
      if(!/^me-[1-9][0-9]*$/.test(id)||!inbox.some(r=>'me-'+r.id===id)||inboxScope!==scope)throw Error('Conversa indisponível.');
      const result=await request('/message-enrichment/conversations/'+id.slice(3)+'/hide','POST');
      if(!auth.current||identityKey()!==scope||result.hidden!==true||String(result.conversation_id)!==id.slice(3))throw Error('Exclusão não confirmada.');
      smInboxEpoch++;
      inbox=inbox.filter(r=>'me-'+r.id!==id);
      const index=C.findIndex(r=>r[0]===id);if(index>=0)C.splice(index,1);
      inboxFingerprint='';
      return true;
    },
    activeInboxPreferences() {
      return auth.current && inboxScope === identityKey()
        ? inbox.filter(row => ['waha', 'instagram'].includes(row.origin))
            .map(({id, contact_name, channel}) => ({id, contact_name, channel}))
        : [];
    },
    async archivedConversations() {
      const scope = identityKey();
      const workspace = auth.current?.negocio.id;
      if (!scope || !workspace) throw Error('Sessão indisponível.');
      const result = await request('/message-enrichment/archived-conversations');
      if (scope !== identityKey() || result.workspace_id !== workspace || !Array.isArray(result.items))
        throw Error('Lista indisponível para esta sessão.');
      return result.items;
    },
    async updateInboxPreferences(action, ids, readThrough, snoozedUntil) {
      const scope = identityKey();
      const workspace = auth.current?.negocio.id;
      if (!scope || !workspace || !ids.length || !ids.every(id => Number.isSafeInteger(id) && id > 0))
        throw Error('Conversa indisponível.');
      const payload = {action, conversation_ids: ids};
      if (readThrough != null) payload.read_through_id = readThrough;
      if (snoozedUntil != null) payload.snoozed_until = snoozedUntil;
      const result = await request('/message-enrichment/inbox-preferences', 'POST', payload);
      if (scope !== identityKey() || result.workspace_id !== workspace || result.action !== action ||
          JSON.stringify(result.conversation_ids) !== JSON.stringify(ids))
        throw Error('Alteração não confirmada nesta sessão.');
      smInboxEpoch++;
      if (action === 'archive' || action === 'hide') {
        inbox = inbox.filter(row => !ids.includes(row.id));
        for (let i = C.length - 1; i >= 0; i--)
          if (ids.includes(Number(C[i][0].slice(3)))) C.splice(i, 1);
      }
      inboxFingerprint = '';
      if (inboxPolling) {
        // The older request cannot paint after the epoch advanced. Refresh after it settles.
        await inboxSettled();
      }
      if (scope === identityKey()) await refreshInbox({silent: true});
    },
    async hiddenConversations() {
      const scope = identityKey();
      const workspace = auth.current?.negocio.id;
      if (!workspace) throw Error('Sessão indisponível.');
      const result = await request('/message-enrichment/hidden-conversations');
      if (scope !== identityKey() || result.workspace_id !== workspace || !Array.isArray(result.items))
        throw Error('Lista indisponível para esta sessão.');
      return result.items;
    },
    async restoreConversation(id) {
      const scope = identityKey();
      if (!scope || !Number.isSafeInteger(id) || id < 1) throw Error('Conversa indisponível.');
      const result = await request('/message-enrichment/conversations/' + id + '/restore', 'POST');
      if (scope !== identityKey() || result.hidden !== false || result.conversation_id !== id)
        throw Error('Restauração não confirmada.');
      smInboxEpoch++;
      inboxFingerprint = '';
      await refreshInbox({ silent: true });
    },
    reloadInbox() {
      return refreshInbox({ silent: true });
    },
    setDone(id, done) {
      const map = readDone();
      if (done) map[id] = Date.now();
      else delete map[id];
      try {
        localStorage.setItem(DONE_KEY, JSON.stringify(map));
      } catch {}
    },
    initials: initialsOf,
    safeAvatar,
    conversation(id) {
      return auth.current && inboxScope === identityKey()
        ? inbox.find((row) => "me-" + row.id === id) || null
        : null;
    },
  };
})();

;(()=>{
 const urls=new Map();

 function release(){
  for(const [slot,url] of urls)
   if(!slot.isConnected){
    URL.revokeObjectURL(url);
    urls.delete(slot);
   }
 }

 new MutationObserver(release).observe(
  document.body,{childList:true,subtree:true}
 );

 window.addEventListener('pagehide',()=>{
  for(const url of urls.values())URL.revokeObjectURL(url);
  urls.clear();
 });

 document.addEventListener('click',async e=>{
  const b=e.target.closest?.('button[data-sm-media]');
  if(!b)return;

  e.preventDefault();
  e.stopImmediatePropagation();

  const id=Number(b.dataset.smMedia);
  const slot=b.nextElementSibling;
  const api=window.SocialMEIV22;
  const identity=api?.identity;

  if(!identity||!Number.isSafeInteger(id)||id<=0||
     slot?.dataset.smMediaSlot!==String(id)||b.disabled)return;

  const same=()=>b.isConnected&&slot.isConnected&&api.identity===identity;

  b.disabled=true;
  slot.textContent='Carregando arquivo…';

  try{
   const path=b.dataset.smMediaSource==='instagram'?'instagram-attachments':'attachments';
   const r=await api.request('/message-enrichment/'+path+'/'+id);

   if(!same())return;

   const allowed=[
    'audio/mpeg','audio/ogg','audio/wav','audio/mp4',
    'image/jpeg','image/png','image/webp','application/pdf'
   ];

   if(r.id!==id||!allowed.includes(r.mime)||
      typeof r.data!=='string'||r.data.length>14000000)
       throw Error('Arquivo inválido');

   const binary=atob(r.data);
   const bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
   const url=URL.createObjectURL(new Blob([bytes],{type:r.mime}));

   if(urls.has(slot))URL.revokeObjectURL(urls.get(slot));

   urls.set(slot,url);
   slot.replaceChildren();

   if(r.mime.startsWith('audio/')){
    const audio=document.createElement('audio');
    audio.controls=true;
    audio.preload='metadata';
    audio.style.maxWidth='100%';
    audio.src=url;
    slot.append(audio);
   }else if(r.mime.startsWith('image/')){
    const img=document.createElement('img');
    img.alt='Imagem recebida';
    img.style.cssText='max-width:100%;max-height:320px;object-fit:contain;border-radius:8px;display:block';
    img.src=url;
    slot.append(img);
   }

   const link=document.createElement('a');
   link.href=url;
   link.className='lk';

   const ext={
    'audio/mpeg':'mp3','audio/ogg':'ogg',
    'audio/wav':'wav','audio/mp4':'m4a',
    'image/jpeg':'jpg','image/png':'png',
    'image/webp':'webp','application/pdf':'pdf'
   };

   link.download='anexo-'+id+'.'+ext[r.mime];
   link.textContent='Salvar arquivo';

   slot.append(link);
   b.hidden=true;

  }catch(err){
   if(same())slot.textContent='Arquivo indisponível. Tente novamente.';
  }finally{
   if(b.isConnected)b.disabled=false;
  }
 },true);
})();
