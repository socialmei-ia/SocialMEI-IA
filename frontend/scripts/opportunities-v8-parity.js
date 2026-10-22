/* V8 parity: local-only planning metadata, not part of the CRM API. */
(() => {
  "use strict";
  document.addEventListener("DOMContentLoaded", () => {
    const bridge = window.SocialMEIOpportunityV8Bridge;
    const view = document.querySelector("#opportunitiesView .op8-shell");
    const nativeList = document.getElementById("commercialOpportunityList");
    if (!bridge || !view || !nativeList) return;
    const $ = (selector) => view.querySelector(selector);
    const note = document.createElement("p");
    note.className = "op8-parity-disclosure";
    note.textContent =
      "Busca e Semana usam oportunidades do CRM. Valores, anotações e retornos são " +
      "um planejamento deste navegador: não sincronizam entre dispositivos nem alteram vendas.";
    view.querySelector(".op8-overview").append(note);

    const toolbar = document.createElement("div");
    toolbar.className = "op8-parity-tools";
    toolbar.innerHTML =
      '<label>Buscar cliente ou interesse<input type="search" id="op8Query" ' +
      'placeholder="Pesquisar oportunidades" autocomplete="off"></label>' +
      '<label>Ordenar<select id="op8Sort"><option value="recent">Mais recentes</option>' +
      '<option value="followup">Próximo retorno</option>' +
      '<option value="value">Maior valor local</option></select></label>';
    view.querySelector(".op8-toolbar").after(toolbar);

    const agenda = document.createElement("section");
    agenda.className = "op8-today";
    agenda.innerHTML =
      '<div class="op8-today-head"><h4>Retornos para acompanhar</h4>' +
      '<button type="button" class="management-button" id="op8CopyDue">Copiar retornos</button></div>' +
      '<div id="op8DueList"></div>';
    view.querySelector(".op8-overview").append(agenda);

    const createForm = document.getElementById("opportunityCreateForm");
    let pendingCreate = null;
    if (createForm) {
      const fields = document.createElement("div");
      fields.className = "op8-create-fields";
      fields.innerHTML =
        '<label>Valor estimado (opcional, só neste navegador)' +
        '<input id="op8CreateValue" inputmode="decimal" placeholder="Ex.: 350,50"></label>' +
        '<label>Data de retorno (opcional, só neste navegador)' +
        '<input id="op8CreateDate" type="date"></label>';
      createForm.insertBefore(fields, createForm.lastElementChild);
      createForm.addEventListener(
        "submit",
        () => {
          pendingCreate = {
            scope: bridge.snapshot().scope,
            amount: $("#op8CreateValue")?.value || "",
            date: $("#op8CreateDate")?.value || "",
          };
        },
        true,
      );
      document.addEventListener("socialmei-v8-created", (event) => {
        const scope = bridge.snapshot().scope;
        if (!pendingCreate || pendingCreate.scope !== scope || !event.detail?.id) return;
        const value = parseMoney(pendingCreate.amount);
        if (Number.isFinite(value)) {
          setMeta(event.detail.id, { amount: value, date: pendingCreate.date });
          $("#op8CreateValue").value = "";
          $("#op8CreateDate").value = "";
        }
        pendingCreate = null;
        update();
      });
    }

    const state = { scope: "", meta: {} };
    const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
    function parseMoney(input) {
      if (!String(input || "").trim()) return 0;
      const clean = String(input).trim().replace(/\./g, "").replace(",", ".");
      const value = Number(clean);
      return Number.isFinite(value) && value >= 0 && value <= 1000000000 ? value : NaN;
    }
    function key(scope) {
      return "socialmei-op8-local-v1:" + encodeURIComponent(scope);
    }
    function read(scope) {
      if (!scope) return {};
      try {
        const raw = JSON.parse(localStorage.getItem(key(scope)));
        if (raw?.v !== 1 || raw?.scope !== scope || !raw.items || Array.isArray(raw.items))
          return {};
        const result = {};
        for (const [id, value] of Object.entries(raw.items).slice(0, 100)) {
          if (!/^[a-z0-9-]{8,80}$/i.test(id) || typeof value !== "object" || !value) continue;
          result[id] = {
            amount: Number.isFinite(value.amount) && value.amount >= 0 ? value.amount : 0,
            date: /^\d{4}-\d{2}-\d{2}$/.test(value.date || "") ? value.date : "",
            note: String(value.note || "").slice(0, 140),
            contacted: Boolean(value.contacted),
          };
        }
        return result;
      } catch {
        return {};
      }
    }
    function setMeta(id, patch) {
      if (!state.scope || !bridge.snapshot().items.some((row) => row.id === id)) return false;
      const old = state.meta[id] || {};
      const next = { ...old, ...patch };
      state.meta[id] = next;
      try {
        localStorage.setItem(
          key(state.scope),
          JSON.stringify({ v: 1, scope: state.scope, items: state.meta }),
        );
        return true;
      } catch {
        state.meta[id] = old;
        view.querySelector("#op8Feedback").textContent =
          "Não foi possível salvar o planejamento neste navegador.";
        return false;
      }
    }
    function isoToday() {
      const d = new Date();
      return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0"), String(d.getDate()).padStart(2, "0")].join("-");
    }
    function nextDay(days) {
      const d = new Date();
      d.setDate(d.getDate() + days);
      return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0"), String(d.getDate()).padStart(2, "0")].join("-");
    }
    function eligible() {
      const snapshot = bridge.snapshot();
      return snapshot.ready && !snapshot.busy && ["owner", "admin", "member"].includes(snapshot.role);
    }
    function rows() {
      const query = $("#op8Query").value.trim().toLocaleLowerCase("pt-BR");
      const snapshot = bridge.snapshot();
      const sort = $("#op8Sort").value;
      const data = snapshot.items.filter((row) =>
        (row.client_name + " " + row.title + " " + row.interest_level)
          .toLocaleLowerCase("pt-BR")
          .includes(query),
      );
      data.sort((a, b) =>
        sort === "value"
          ? (state.meta[b.id]?.amount || 0) - (state.meta[a.id]?.amount || 0)
          : sort === "followup"
            ? (state.meta[a.id]?.date || "9999").localeCompare(state.meta[b.id]?.date || "9999")
            : Date.parse(b.updated_at || 0) - Date.parse(a.updated_at || 0),
      );
      return data;
    }
    function button(label, handler) {
      const b = document.createElement("button");
      b.className = "management-button";
      b.type = "button";
      b.textContent = label;
      b.addEventListener("click", handler);
      return b;
    }
    function safeText(tag, text, klass = "") {
      const element = document.createElement(tag);
      element.textContent = String(text);
      if (klass) element.className = klass;
      return element;
    }
    function renderDue(data) {
      const host = $("#op8DueList");
      host.replaceChildren();
      const today = isoToday();
      const due = data.filter((row) => {
        const meta = state.meta[row.id];
        return row.outcome === "open" && meta?.date && meta.date <= today;
      });
      agenda.hidden = !due.length;
      for (const row of due) {
        const item = safeText("div", "", "op8-due-row");
        item.append(
          safeText("strong", row.client_name + " · " + row.title),
          safeText("small", state.meta[row.id].date),
          button("+1 dia", () => {
            if (setMeta(row.id, { date: nextDay(1), contacted: false })) update();
          }),
          button("Contato registrado", () => {
            if (setMeta(row.id, { date: "", contacted: true })) update();
          }),
        );
        host.append(item);
      }
    }
    function extraCard(card, row) {
      const existing = card.querySelector(".op8-extra");
      if (existing) existing.remove();
      const value = state.meta[row.id] || {};
      const details = document.createElement("details");
      details.className = "op8-extra";
      details.append(safeText("summary", "Valor, anotação e retorno (local)"));
      const amount = document.createElement("input");
      amount.inputMode = "decimal";
      amount.placeholder = "Valor R$";
      amount.value = value.amount ? String(value.amount).replace(".", ",") : "";
      amount.setAttribute("aria-label", "Valor estimado de " + row.client_name);
      const date = document.createElement("input");
      date.type = "date";
      date.value = value.date || "";
      date.setAttribute("aria-label", "Próximo retorno para " + row.client_name);
      const note = document.createElement("input");
      note.maxLength = 140;
      note.placeholder = "Anotação local";
      note.value = value.note || "";
      note.setAttribute("aria-label", "Anotação para " + row.client_name);
      const save = button("Salvar planejamento", () => {
        const parsed = parseMoney(amount.value);
        if (!Number.isFinite(parsed)) {
          view.querySelector("#op8Feedback").textContent = "Confira o valor informado.";
          amount.focus();
          return;
        }
        const validDate = !date.value || /^\d{4}-\d{2}-\d{2}$/.test(date.value);
        if (!validDate) return;
        if (setMeta(row.id, { amount: parsed, date: date.value, note: note.value })) {
          view.querySelector("#op8Feedback").textContent =
            "Planejamento salvo apenas neste navegador, sem alterar o CRM.";
          update();
        }
      });
      const quick = document.createElement("div");
      quick.className = "op8-quick";
      for (const [days, label] of [[1, "+1 dia"], [3, "+3 dias"], [7, "+1 semana"]]) {
        quick.append(button(label, () => {
          date.value = nextDay(days);
          if (setMeta(row.id, { date: date.value, contacted: false })) update();
        }));
      }
      details.append(amount, date, note, save, quick);
      card.append(details);
      const summary = document.createElement("span");
      summary.className = "op8-local-meta";
      summary.textContent =
        (value.amount ? money.format(value.amount) : "Sem valor") +
        " · " + (value.date ? "Retomar: " + value.date : "Sem retorno marcado");
      card.insertBefore(summary, details);
    }
    function renderWeek(data) {
      const week = $("#op8Week");
      week.replaceChildren();
      const open = data.filter((row) => row.outcome === "open");
      const days = Array.from({ length: 7 }, (_, n) => nextDay(n));
      days.push("");
      for (const date of days) {
        const column = document.createElement("section");
        column.className = "op8-week-col";
        const label = date || "Sem data";
        const matches = open.filter((row) => (state.meta[row.id]?.date || "") === date);
        column.append(safeText("h4", label + " (" + matches.length + ")"));
        const select = document.createElement("div");
        select.className = "op8-week-cards";
        for (const row of matches) {
          const entry = safeText("div", row.client_name + " · " + row.title, "op8-week-card");
          entry.append(safeText("small", state.meta[row.id]?.amount ? money.format(state.meta[row.id].amount) : "Sem valor"));
          const move = document.createElement("select");
          move.setAttribute("aria-label", "Mover retorno de " + row.client_name);
          for (const day of days) {
            const opt = document.createElement("option");
            opt.value = day;
            opt.textContent = day || "Sem data";
            move.append(opt);
          }
          move.value = date;
          move.addEventListener("change", () => {
            if (setMeta(row.id, { date: move.value, contacted: false })) update();
          });
          entry.append(move);
          select.append(entry);
        }
        column.append(select);
        week.append(column);
      }
    }
    function update() {
      const snapshot = bridge.snapshot();
      if (state.scope !== snapshot.scope) {
        state.scope = snapshot.scope;
        state.meta = read(snapshot.scope);
      }
      const data = rows();
      renderDue(data);
      renderWeek(data);
      for (const card of view.querySelectorAll(".op8-entry")) {
        const row = snapshot.items.find((item) => item.id === card.dataset.opportunityId);
        if (row) {
          card.hidden = !data.includes(row);
          extraCard(card, row);
        }
      }
      for (const item of nativeList.querySelectorAll("[data-commercial-opportunity]")) {
        item.hidden = !data.some((row) => row.id === item.dataset.commercialOpportunity);
      }
      for (const item of view.querySelectorAll(".op8-day-list li")) {
        const title = item.querySelector("strong")?.textContent || "";
        item.hidden = !data.some((row) => row.client_name === title);
      }
      const weekTab = view.querySelector('[data-op8-view="week"]');
      if (weekTab?.getAttribute("aria-pressed") === "true") week.hidden = false;
    }
    for (const input of [$("#op8Query"), $("#op8Sort")])
      input.addEventListener(input.id === "op8Query" ? "input" : "change", update);
    view.addEventListener("click", (event) => {
      if (event.target.closest("[data-op8-view]")) requestAnimationFrame(update);
    });
    $("#op8CopyDue").addEventListener("click", async () => {
      const due = rows().filter((row) => {
        const meta = state.meta[row.id];
        return row.outcome === "open" && meta?.date && meta.date <= isoToday();
      });
      const text = due.map((row) => row.client_name + " — " + row.title).join("\n");
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        view.querySelector("#op8Feedback").textContent =
          "Retornos locais copiados; nenhum contato foi enviado.";
      } catch {
        view.querySelector("#op8Feedback").textContent = "Selecione e copie os retornos manualmente.";
      }
    });
    document.addEventListener("socialmei-opportunity-v8-change", update);
    document.addEventListener("socialmei-view-change", () => requestAnimationFrame(update));
    update();
  });
})();
