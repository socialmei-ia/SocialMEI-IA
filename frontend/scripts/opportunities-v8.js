/* Oportunidades V8 — native presentation backed by the existing commercial API. */
(() => {
  "use strict";
  document.addEventListener("DOMContentLoaded", () => {
    const host = document.getElementById("opportunityLifecycle");
    const bridge = window.SocialMEIOpportunityV8Bridge;
    const list = document.getElementById("commercialOpportunityList");
    if (!host || !bridge || !list) return;
    const nativeFilters = list.previousElementSibling;
    const view = document.createElement("section");
    view.className = "op8-shell";
    view.setAttribute("aria-label", "Painel de acompanhamento de oportunidades V8");
    view.innerHTML = `
      <div class="op8-overview">
        <div class="op8-head">
          <div><span class="op8-eyebrow">ACOMPANHAMENTO COMERCIAL</span>
            <h3>Negociações em movimento.</h3>
            <p class="op8-caption" id="op8Summary" role="status" aria-live="polite">Carregando informações do negócio…</p>
          </div>
          <div class="op8-head-actions">
            <button class="management-button" type="button" id="op8Refresh">Atualizar dados</button>
            <button class="management-button pr" type="button" id="op8Create">Nova oportunidade</button>
          </div>
        </div>
        <div class="op8-indicators" aria-label="Situação das negociações">
          <div><small>Em andamento</small><strong id="op8Open">0</strong></div>
          <div><small>Em análise</small><strong id="op8Unknown">0</strong></div>
          <div><small>Quentes</small><strong id="op8Hot">0</strong></div>
          <div><small>Encerradas</small><strong id="op8Closed">0</strong></div>
        </div>
        <div class="op8-priority" id="op8Priority" aria-label="Oportunidades para acompanhar"></div>
      </div>
      <div class="op8-toolbar">
        <div><h3>Explorar oportunidades</h3><p>Escolha uma visualização. Alterações são salvas no negócio.</p></div>
        <div class="op8-switch" role="group" aria-label="Visualizar oportunidades">
          <button type="button" data-op8-view="list" aria-pressed="true">Lista</button>
          <button type="button" data-op8-view="board" aria-pressed="false">Termômetro</button>
          <button type="button" data-op8-view="timeline" aria-pressed="false">Atividade</button>
        </div>
      </div>
      <div id="op8Board" class="op8-board" hidden></div>
      <div id="op8Timeline" class="op8-timeline" hidden></div>
      <p id="op8Feedback" class="op8-feedback" role="status" aria-live="polite"></p>
    `;
    host.insertBefore(view, host.firstChild);
    host.classList.add("op8-enabled");
    const $ = (id) => view.querySelector("#" + id);
    const state = { mode: "list", query: "", scope: null };
    const levels = Object.entries(SocialMEIOpportunityLifecycle.INTEREST);
    const dates = (date) => {
      const value = Date.parse(date || "");
      return Number.isFinite(value)
        ? new Date(value).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" })
        : "Data não informada";
    };
    const el = (tag, className, content) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (content !== undefined) node.textContent = String(content);
      return node;
    };
    const btn = (label, click, className = "management-button") => {
      const button = el("button", className, label);
      button.type = "button";
      button.addEventListener("click", click);
      return button;
    };
    const announce = (message) => {
      $("op8Feedback").textContent = message;
    };
    function navigateNative(row) {
      state.mode = "list";
      syncView();
      const filter = row.outcome === "open" ? "open" : row.outcome;
      nativeFilters?.querySelector(`[data-commercial-filter="${filter}"]`)?.click();
      const target = [...list.querySelectorAll("[data-commercial-opportunity]")].find(
        (item) => item.dataset.commercialOpportunity === row.id,
      );
      if (!target) {
        announce("Atualize a lista para visualizar os detalhes deste registro.");
        return;
      }
      const details = target.querySelector("details");
      if (details) details.open = true;
      target.scrollIntoView({ block: "center", behavior: "smooth" });
      target.querySelector("summary, button")?.focus({ preventScroll: true });
    }
    function writable(snapshot) {
      return snapshot.ready && !snapshot.busy && ["owner", "admin", "member"].includes(snapshot.role);
    }
    function makeMove(row, snapshot) {
      const wrapper = el("div", "op8-move");
      const select = el("select");
      select.setAttribute("aria-label", "Novo nível de interesse para " + row.client_name);
      for (const [value, name] of levels) {
        const option = el("option", "", name);
        option.value = value;
        select.append(option);
      }
      select.value = row.interest_level;
      select.disabled = !writable(snapshot);
      const save = btn("Mover", () => {
        if (select.value === row.interest_level) return;
        const didStart = bridge.changeInterest(row.id, select.value);
        announce(
          didStart ? "Salvando alteração no negócio…" : "Não foi possível iniciar a atualização. Confira suas permissões.",
        );
      }, "management-button op8-save");
      save.disabled = !writable(snapshot);
      wrapper.append(select, save);
      return wrapper;
    }
    function boardCard(row, snapshot) {
      const card = el("article", "op8-entry");
      const name = el("strong", "", row.client_name);
      const title = el("span", "op8-entry-title", row.title);
      const meta = el("small", "", "Atualizada " + dates(row.updated_at));
      card.append(name, title, meta, makeMove(row, snapshot), btn("Abrir acompanhamento", () => navigateNative(row), "op8-textbutton"));
      return card;
    }
    function renderBoard(snapshot) {
      const container = $("op8Board");
      container.replaceChildren();
      const rows = snapshot.items.filter((row) => row.outcome === "open");
      for (const [level, label] of levels) {
        const column = el("section", "op8-column op8-column-" + level);
        const current = rows.filter((row) => row.interest_level === level);
        const h = el("h4", "", label);
        h.append(el("span", "op8-count", current.length));
        column.append(h);
        const region = el("div", "op8-column-body");
        region.setAttribute("aria-label", label + ": " + current.length + " oportunidades");
        if (!current.length) region.append(el("p", "op8-empty", "Nenhuma oportunidade aqui."));
        for (const row of current) region.append(boardCard(row, snapshot));
        column.append(region);
        container.append(column);
      }
      if (snapshot.items.length >= 100)
        container.after(el("p", "op8-notice", "Exibindo até 100 registros recentes. Use a lista para conferir o contexto."));
    }
    function renderTimeline(snapshot) {
      const container = $("op8Timeline");
      container.replaceChildren();
      const rows = [...snapshot.items].sort(
        (a, b) => Date.parse(b.updated_at || "") - Date.parse(a.updated_at || ""),
      );
      if (!rows.length) {
        container.append(el("p", "op8-empty", "As movimentações aparecerão aqui depois de cadastrar oportunidades."));
        return;
      }
      const groups = new Map();
      for (const row of rows) {
        const date = dates(row.updated_at);
        if (!groups.has(date)) groups.set(date, []);
        groups.get(date).push(row);
      }
      for (const [date, items] of groups) {
        const section = el("section", "op8-day");
        section.append(el("h4", "", date));
        const ul = el("ul", "op8-day-list");
        for (const row of items) {
          const item = el("li");
          const content = el("div");
          content.append(el("strong", "", row.client_name), el("p", "", row.title));
          const outcome = row.outcome === "open"
            ? SocialMEIOpportunityLifecycle.INTEREST[row.interest_level]
            : SocialMEIOpportunityLifecycle.OUTCOME[row.outcome];
          const open = btn("Ver detalhes", () => navigateNative(row), "op8-textbutton");
          item.append(content, el("span", "op8-label", outcome), open);
          ul.append(item);
        }
        section.append(ul);
        container.append(section);
      }
    }
    function syncView() {
      view.querySelectorAll("[data-op8-view]").forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset.op8View === state.mode));
      });
      const nativeVisible = state.mode === "list";
      if (nativeFilters) nativeFilters.hidden = !nativeVisible;
      list.hidden = !nativeVisible;
      $("op8Board").hidden = state.mode !== "board";
      $("op8Timeline").hidden = state.mode !== "timeline";
    }
    function refresh() {
      const snapshot = bridge.snapshot();
      if (snapshot.scope !== state.scope) {
        state.scope = snapshot.scope;
        state.mode = "list";
      }
      $("op8Open").textContent = snapshot.totals.open;
      $("op8Unknown").textContent = snapshot.totals.unknown;
      $("op8Hot").textContent = snapshot.totals.hot;
      $("op8Closed").textContent = snapshot.totals.won + snapshot.totals.lost;
      $("op8Summary").textContent = !snapshot.ready
        ? snapshot.problem || "O acompanhamento exige entrar na conta e carregar seus registros."
        : snapshot.totals.open === 0
          ? "Nenhuma negociação aberta. Cadastre a primeira oportunidade logo abaixo."
          : `${snapshot.totals.open} negociação(ões) em andamento neste negócio. Revise o histórico antes de mudar o interesse.`;
      const priority = $("op8Priority");
      priority.replaceChildren();
      const open = snapshot.items
        .filter((row) => row.outcome === "open")
        .sort((a, b) => Date.parse(a.updated_at || "") - Date.parse(b.updated_at || ""))
        .slice(0, 3);
      if (open.length) {
        priority.append(el("h4", "", "Para acompanhar"));
        for (const row of open) {
          const element = el("div", "op8-priority-row");
          element.append(
            el("span", "", row.client_name + " · " + row.title),
            btn("Revisar", () => navigateNative(row), "op8-textbutton"),
          );
          priority.append(element);
        }
        priority.append(el("small", "", "Ordenado por última atualização. Não representa prazo ou compromisso agendado."));
      }
      renderBoard(snapshot);
      renderTimeline(snapshot);
      syncView();
    }
    view.addEventListener("click", (event) => {
      const target = event.target.closest("[data-op8-view]");
      if (!target) return;
      state.mode = target.dataset.op8View;
      syncView();
      if (state.mode !== "list") view.querySelector("#op8" + (state.mode === "board" ? "Board" : "Timeline"))?.focus();
    });
    $("op8Create").addEventListener("click", () => {
      const form = document.getElementById("opportunityCreateForm");
      form?.scrollIntoView({ behavior: "smooth", block: "center" });
      form?.querySelector("select,input")?.focus({ preventScroll: true });
    });
    $("op8Refresh").addEventListener("click", () => bridge.refresh());
    document.addEventListener("socialmei-opportunity-v8-change", refresh);
    document.addEventListener("socialmei-view-change", () => {
      if (typeof currentView === "undefined" || currentView === "Oportunidades") refresh();
    });
    refresh();
  });
})();
