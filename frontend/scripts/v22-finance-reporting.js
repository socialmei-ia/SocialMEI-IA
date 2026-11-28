/* Recorded financial flows; never a bank balance or profit estimate. */
(() => {
  const host = window.SocialMEIV22,
    auth = window.SocialMEIAuth;
  if (!host?.remote || !auth?.remote || window.SocialMEIFinanceReports) return;
  const el = (tag, text) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = String(text);
    return n;
  };
  const scope = () => auth.current && `${auth.current.usuario.id}:${auth.current.negocio.id}`;
  const money = (value) => {
    if (typeof value !== "string" || !/^-?\d+\.\d{2}$/.test(value))
      throw Error("Valores financeiros não confirmados pelo servidor.");
    const [integer, fraction] = value.split(".");
    return "R$ " + integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + fraction;
  };

  function downloadReport(data) {
    const amounts = (row) => [row.incoming, row.outgoing, row.balance ?? ""];
    const rows = [
      ["Escopo", "In\u00edcio", "Fim", "Entradas", "Sa\u00eddas", "Saldo"],
      ["Pago", data.period.start, data.period.end, ...amounts(data.paid)],
      [
        "Pago no per\u00edodo anterior",
        data.previous.start,
        data.previous.end,
        ...amounts(data.previous),
      ],
      ["Em aberto por vencimento", data.period.start, data.period.end, ...amounts(data.pending)],
      ...(data.overdue
        ? [["Em atraso at\u00e9 a consulta", "", data.overdue.as_of, ...amounts(data.overdue)]]
        : []),
      ...data.daily.map((row) => ["Caixa por dia", row.date, row.date, ...amounts(row)]),
      ...(data.categories || []).map((row) => [
        "Categoria paga: " + (row.category || "Sem categoria"),
        data.period.start,
        data.period.end,
        row.kind === "receita" ? row.total : "",
        row.kind === "despesa" ? row.total : "",
        "",
      ]),
    ];
    const csv = rows
      .map((row) => row.map((value) => '"' + String(value).replaceAll('"', '""') + '"').join(";"))
      .join("\r\n");
    const url = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
    const link = el("a");
    link.href = url;
    link.download = "financeiro-" + data.period.start + "-" + data.period.end + ".csv";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function printReport(content, period, business) {
    const popup = window.open("about:blank", "_blank");
    if (!popup) throw Error("Permita abrir a janela de impress\u00e3o e tente novamente.");
    popup.opener = null;
    popup.document.title = "Financeiro registrado";
    const style = popup.document.createElement("style");
    style.textContent =
      "body{font-family:system-ui,sans-serif;margin:24px}th,td{padding:4px;text-align:left}thead{display:table-header-group}tr{break-inside:avoid}";
    popup.document.head.append(style);
    popup.document.body.append(
      popup.document.importNode(el("h1", "Financeiro registrado"), true),
      popup.document.importNode(
        el("p", business + " | " + period.start + " a " + period.end),
        true,
      ),
      popup.document.importNode(content, true),
    );
    popup.print();
  }

  function mountMei(view) {
    if (
      !/^#\/negocio(?:\/resumo)?\/?$/.test(location.hash) ||
      view.querySelector("[data-mei-tracking]")
    )
      return;
    const owner = scope();
    const section = el("section");
    section.className = "pg";
    section.dataset.meiTracking = "";
    const message = el("p", "Consultando faturamento registrado…");
    message.setAttribute("role", "status");
    section.append(el("h2", "Acompanhamento do MEI"), message);
    view.append(section);
    const same = () => section.isConnected && owner === scope();
    const canEdit = () => ["owner", "admin"].includes(auth.current?.papel);
    async function load() {
      try {
        const report = await host.request("/reporting/mei");
        if (!same() || report.workspace_id !== auth.current.negocio.id) return;
        message.textContent =
          "Ano-calendário " + report.year + " · vendas registradas: " + money(report.system_sales);
        const summary = el("div");
        summary.dataset.meiSummary = "";
        if (report.opened_on) {
          summary.append(el("p", "Estimativa para acompanhamento: " + money(report.estimate)));
          if (report.prior_through)
            summary.append(
              el(
                "p",
                money(report.prior_amount) +
                  " informado até " +
                  report.prior_through +
                  " · " +
                  money(report.system_sales_used) +
                  " em vendas a partir de " +
                  report.system_from,
              ),
            );
          if (report.limit) {
            const status = {
              near: " · atenção a partir de 80%",
              exceeded: " · acima do limite de referência",
            };
            summary.append(
              el(
                "p",
                "Limite de referência do MEI geral: " +
                  money(report.limit) +
                  (status[report.level] || ""),
              ),
            );
          } else summary.append(el("p", "Limite de referência ainda indisponível para este ano."));
          const source = el("a", "Consultar a fonte oficial do limite");
          source.href = report.limit_source;
          source.target = "_blank";
          source.rel = "noopener noreferrer";
          summary.append(source);
        } else
          summary.append(
            el("p", "Informe a abertura se o negócio estiver enquadrado como MEI geral."),
          );
        summary.append(
          el(
            "p",
            "O valor usa vendas registradas e os valores anteriores informados. Consulte a documentação fiscal para o faturamento completo.",
          ),
        );
        const das = el("a", "Consultar guias e situação do DAS no Simples Nacional");
        das.href =
          "https://www8.receita.fazenda.gov.br/SimplesNacional/Aplicacoes/ATSPO/pgmei.app/Identificacao";
        das.target = "_blank";
        das.rel = "noopener noreferrer";
        summary.append(das);
        if (canEdit()) summary.append(editor(report));
        section.querySelector("[data-mei-summary]")?.remove();
        section.append(summary);
      } catch (error) {
        if (same()) message.textContent = error.message || "Acompanhamento do MEI indisponível.";
      }
    }
    function editor(report) {
      const panel = el("details");
      panel.append(el("summary", "Configurar acompanhamento do MEI geral"));
      const form = el("form");
      form.className = "row wr";
      panel.append(
        el(
          "p",
          "Se informar faturamento anterior, some todas as vendas da abertura ou do começo do ano até a data final. As vendas desse intervalo ficam fora da soma automática.",
        ),
        form,
      );
      const input = (label, type, value) => {
        const wrap = el("label", label);
        const field = el("input");
        field.className = "in";
        field.type = type;
        field.value = value ?? "";
        wrap.append(field);
        form.append(wrap);
        return field;
      };
      const opening = input("Data de abertura no CNPJ", "date", report.opened_on);
      opening.required = true;
      const until = input("Faturamento anterior até (opcional)", "date", report.prior_through);
      const amount = input(
        "Valor anterior (R$)",
        "number",
        report.prior_through ? report.prior_amount : "",
      );
      amount.min = "0";
      amount.step = "0.01";
      const source = input("Referência do valor anterior", "text", report.source_note);
      source.maxLength = 300;
      const button = el("button", "Salvar acompanhamento");
      button.className = "btn o";
      button.type = "submit";
      form.append(button);
      let attempt;
      form.onsubmit = async (event) => {
        event.preventDefault();
        if (!same() || !canEdit() || button.disabled) return;
        const data = {
          opened_on: opening.value,
          prior_through: until.value || null,
          prior_amount: amount.value || null,
          source_note: source.value,
          expected_revision: report.revision,
        };
        const signature = JSON.stringify(data);
        if (!attempt || attempt.signature !== signature)
          attempt = { signature, id: crypto.randomUUID() };
        button.disabled = true;
        try {
          await host.request("/reporting/mei", "POST", { ...data, operation_id: attempt.id });
          if (same()) await load();
        } catch (error) {
          if (same())
            message.textContent = error.message || "Não foi possível salvar o acompanhamento.";
          if (same() && error.status === 409) await load();
        } finally {
          button.disabled = false;
        }
      };
      return panel;
    }
    load();
    mountDas(section, same, canEdit);
  }

  function mountDas(section, same, canEdit) {
    const details = el("details");
    const message = el("p");
    message.setAttribute("role", "status");
    const content = el("div");
    details.append(
      el("summary", "Registros manuais do DAS"),
      el("p", "Declarações internas. A confirmação oficial continua no PGMEI."),
      message,
      content,
    );
    section.append(details);
    const query = "/reporting/mei/das";
    let attempt;
    async function load() {
      try {
        message.textContent = "Consultando registros…";
        const result = await host.request(query);
        if (!same() || result.workspace_id !== auth.current.negocio.id) return;
        content.replaceChildren();
        message.textContent = result.items.length ? "" : "Nenhum registro manual.";
        if (canEdit()) content.append(editor());
        for (const row of result.items) {
          const month = el("details");
          month.append(
            el(
              "summary",
              row.competencia.slice(0, 7) +
                " · " +
                (row.pago_em
                  ? "Informado em " + row.pago_em + " · " + money(row.valor)
                  : "Registro corrigido"),
            ),
          );
          const history = el("ul");
          month.append(history);
          if (canEdit()) month.append(editor(row));
          month.addEventListener("toggle", async () => {
            if (!month.open || history.children.length) return;
            try {
              const data = await host.request(
                query + "?competencia=" + encodeURIComponent(row.competencia),
              );
              if (!same() || !history.isConnected || data.workspace_id !== auth.current.negocio.id)
                return;
              for (const item of data.items) {
                const label = item.pago_em
                  ? "Pagamento declarado em " + item.pago_em + " · " + money(item.valor)
                  : "Correção";
                history.append(
                  el("li", "Revisão " + item.revision + " · " + label + " · " + item.referencia),
                );
              }
            } catch (error) {
              if (same() && history.isConnected) message.textContent = error.message;
            }
          });
          content.append(month);
        }
      } catch (error) {
        if (same()) message.textContent = error.message || "Registros do DAS indisponíveis.";
      }
    }
    function editor(row) {
      const form = el("form");
      form.className = "row wr";
      const input = (type, label, value) => {
        const wrapper = el("label", label);
        const field = el("input");
        field.type = type;
        field.className = "in";
        field.value = value || "";
        wrapper.append(field);
        form.append(wrapper);
        return field;
      };
      const month = input("month", "Competência", row?.competencia.slice(0, 7));
      const day = input("date", "Data paga informada", row?.pago_em);
      const amount = input("number", "Valor (R$)", row?.valor);
      const note = input("text", "Referência do comprovante ou motivo da correção");
      month.required = note.required = true;
      note.maxLength = 300;
      month.readOnly = !!row;
      amount.min = "0.01";
      amount.step = "0.01";
      const save = el("button", row ? "Atualizar declaração" : "Declarar pagamento");
      save.className = "btn o";
      save.type = "submit";
      form.append(save);
      if (row?.pago_em) {
        const cancel = el("button", "Revogar declaração");
        cancel.type = "submit";
        cancel.className = "btn o";
        cancel.dataset.revokeDas = "";
        form.append(cancel);
      }
      form.onsubmit = async (event) => {
        event.preventDefault();
        if (!same() || !canEdit() || save.disabled) return;
        const remove = event.submitter?.hasAttribute("data-revoke-das");
        if (remove && !window.confirm("Revogar o registro interno desta competência?")) return;
        if (!remove && (!day.value || !amount.value)) {
          message.textContent = "Informe a data e o valor.";
          return;
        }
        const formData = {
          competencia: month.value + "-01",
          expected_revision: row?.revision || 0,
          pago_em: remove ? null : day.value,
          valor: remove ? null : amount.value,
          referencia: note.value,
        };
        const signature = JSON.stringify(formData);
        if (attempt?.signature !== signature) attempt = { signature, id: crypto.randomUUID() };
        save.disabled = true;
        try {
          await host.request(query, "POST", { ...formData, operation_id: attempt.id });
          if (same()) await load();
        } catch (error) {
          if (same())
            message.textContent = error.message || "Não foi possível confirmar o registro.";
        } finally {
          save.disabled = false;
        }
      };
      return form;
    }
    details.addEventListener("toggle", () => {
      if (details.open && !content.children.length) void load();
    });
  }

  function mount() {
    const view = document.getElementById("v");
    if (view && scope()) mountMei(view);
    if (
      !view ||
      !scope() ||
      !location.hash.startsWith("#/relatorios") ||
      view.querySelector("[data-finance-report]")
    )
      return;
    const owner = scope(),
      section = el("section");
    section.dataset.financeReport = "true";
    section.className = "sm-data";
    section.style.cssText =
      "margin:20px 0;padding:20px;border:1px solid var(--b);border-radius:16px;background:var(--w);color:var(--t)";
    section.append(el("h2", "Financeiro registrado"));
    const form = el("form"),
      dates = [];
    form.style.cssText = "display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:14px 0";
    for (const text of ["Financeiro desde", "Financeiro até"]) {
      const label = el("label", text),
        input = el("input");
      label.style.cssText = "display:grid;gap:6px;max-width:100%";
      input.type = "date";
      input.required = true;
      input.style.cssText =
        "padding:10px;background:var(--w);color:var(--t);border:1px solid var(--b);border-radius:8px;max-width:100%;box-sizing:border-box";
      label.append(input);
      form.append(label);
      dates.push(input);
    }
    const filter = el("button", "Consultar financeiro do período"),
      refresh = el("button", "Atualizar financeiro");
    filter.type = "submit";
    refresh.type = "button";
    filter.className = refresh.className = "btn o";
    form.append(filter, refresh);
    const message = el("p"),
      content = el("div");
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
    section.append(form, message, content);
    view.append(section);
    let revision = 0;
    const alive = (id) =>
      section.isConnected &&
      location.hash.startsWith("#/relatorios") &&
      scope() === owner &&
      revision === id;
    async function load(custom) {
      const id = ++revision;
      filter.disabled = refresh.disabled = true;
      dates.forEach((n) => {
        n.disabled = true;
      });
      message.textContent = "Consultando lançamentos persistidos…";
      content.replaceChildren();
      section.querySelector("[data-finance-export]")?.remove();
      try {
        const query = custom
          ? "?" + new URLSearchParams({ start: dates[0].value, end: dates[1].value })
          : "";
        const data = await host.request("/reporting/finance" + query);
        if (!alive(id)) return;
        if (
          data.workspace_id !== auth.current.negocio.id ||
          !Array.isArray(data.daily) ||
          data.daily.length > 366 ||
          !Number.isSafeInteger(data.undated_paid_count) ||
          data.undated_paid_count < 0 ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.period?.start) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.period?.end)
        )
          throw Error("Indicadores financeiros não confirmados pelo servidor.");
        dates[0].value = data.period.start;
        dates[1].value = data.period.end;
        const list = el("ul");
        for (const [label, value] of [
          ["Entradas registradas como pagas", data.paid.incoming],
          ["Saídas registradas como pagas", data.paid.outgoing],
          ["Saldo dos lançamentos pagos no período", data.paid.balance],
          ["Saldo do período anterior", data.previous.balance],
          ["Variação do saldo entre os períodos", data.balance_change],
          ["A receber por vencimento", data.pending.incoming],
          ["A pagar por vencimento", data.pending.outgoing],
        ])
          list.append(el("li", label + ": " + money(value)));
        content.append(
          list,
          el("p", "Comparação: " + data.previous.start + " a " + data.previous.end),
        );
        if (data.overdue) {
          const aging = el("ul");
          aging.append(
            el("li", "Recebimentos em atraso: " + money(data.overdue.incoming)),
            el("li", "Pagamentos em atraso: " + money(data.overdue.outgoing)),
          );
          content.append(el("h3", "Contas vencidas at\u00e9 " + data.overdue.as_of), aging);
        }
        if (data.categories?.length) {
          const categories = el("ul");
          for (const row of data.categories) {
            const kind = row.kind === "receita" ? "Entrada" : "Saída";
            categories.append(
              el("li", [row.category || "Sem categoria", kind, money(row.total)].join(" · ")),
            );
          }
          content.append(el("h3", "Lançamentos pagos por categoria"), categories);
          if (data.categories_truncated)
            content.append(
              el(
                "p",
                "São exibidas as 100 maiores categorias por tipo. Os totais incluem todos os lançamentos.",
              ),
            );
        }
        if (data.undated_paid_count)
          content.append(
            el(
              "p",
              `Atenção: ${data.undated_paid_count} lançamento(s) pago(s) com vencimento neste período não têm data de pagamento e não entram no saldo.`,
            ),
          );
        if (!data.paid.count) content.append(el("p", "Nenhum pagamento registrado neste período."));
        else {
          const table = el("table"),
            head = el("tr"),
            body = el("tbody");
          table.style.cssText = "width:100%;table-layout:fixed;overflow-wrap:anywhere";
          table.append(el("caption", "Evolução diária pela data de pagamento"));
          for (const label of ["Data", "Entradas", "Saídas", "Saldo"]) head.append(el("th", label));
          const th = el("thead");
          th.append(head);
          table.append(th);
          for (const item of data.daily) {
            if (!/^\d{4}-\d{2}-\d{2}$/.test(item.date)) throw Error("Data financeira inválida.");
            const row = el("tr");
            for (const value of [
              item.date.split("-").reverse().join("/"),
              money(item.incoming),
              money(item.outgoing),
              money(item.balance),
            ])
              row.append(el("td", value));
            body.append(row);
          }
          table.append(body);
          content.append(table);
        }
        content.append(el("p", data.description), el("p", data.pending_description));
        const exports = el("div");
        exports.className = "row wr";
        for (const [label, execute] of [
          ["Exportar financeiro em CSV", () => downloadReport(data)],
          [
            "Imprimir ou salvar financeiro em PDF",
            () => printReport(content, data.period, auth.current.negocio.nome),
          ],
        ]) {
          const button = el("button", label);
          button.type = "button";
          button.className = "btn o";
          button.onclick = () => {
            if (!alive(id)) return;
            try {
              execute();
            } catch (error) {
              message.textContent = error.message;
            }
          };
          exports.append(button);
        }
        content.after(exports);
        exports.dataset.financeExport = "";
        message.textContent = "Financeiro consultado · fuso: " + data.period.timezone;
      } catch (error) {
        if (alive(id)) {
          content.replaceChildren();
          message.textContent = error.message || "Não foi possível consultar o financeiro.";
        }
      } finally {
        if (alive(id)) {
          filter.disabled = refresh.disabled = false;
          dates.forEach((n) => {
            n.disabled = false;
          });
        }
      }
    }
    form.onsubmit = (e) => {
      e.preventDefault();
      if (form.reportValidity()) load(true);
    };
    refresh.onclick = () => load(!!dates[0].value && !!dates[1].value);
    load(false);
  }
  window.SocialMEIFinanceReports = { refresh: mount };
  const previous = window.render;
  if (typeof previous === "function")
    window.render = function (...args) {
      const result = previous.apply(this, args);
      queueMicrotask(mount);
      return result;
    };
  window.addEventListener("hashchange", () => queueMicrotask(mount));
  queueMicrotask(mount);
})();
