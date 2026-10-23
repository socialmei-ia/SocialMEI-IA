/* Original V4 dock and calendar, backed by the official draft/preparation stores. */
const SocialMEIContentWorkspace = (() => {
  "use strict";
  function filterJobs(jobs, { status = "all", day = "" } = {}) {
    return jobs.filter((job) => {
      if (status !== "all" && job.status !== status) return false;
      if (!day) return true;
      if (!job.scheduled_for) return false;
      try {
        return (
          new Intl.DateTimeFormat("sv-SE", {
            timeZone: job.timezone,
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
          }).format(new Date(job.scheduled_for)) === day
        );
      } catch {
        return false;
      }
    });
  }
  function init() {
    const host = document.getElementById("contentStudioView");
    if (!host) return;
    const tabs = [...host.querySelectorAll("[data-content-workspace-tab]")],
      indicator = document.getElementById("exactV4-ind"),
      names = ["create", "drafts", "agenda", "connections"];
    let current = 0,
      timer = 0;
    const visible = () => currentView === "Divulgação" && host.getClientRects().length > 0;
    function move() {
      const tab = tabs[current];
      indicator.style.width = tab.offsetWidth + "px";
      indicator.style.transform = "translateX(" + tab.offsetLeft + "px)";
      const box = host.getBoundingClientRect();
      host.style.setProperty(
        "--v4-dock-center",
        Math.max(0, box.left) + Math.min(innerWidth, box.width) / 2 + "px",
      );
    }
    function select(name, focus = false) {
      const next = names.indexOf(name);
      if (next < 0) return;
      clearTimeout(timer);
      const prior = current,
        previousPanel = document.getElementById(tabs[prior].getAttribute("aria-controls"));
      current = next;
      tabs.forEach((tab, index) => {
        const active = index === next;
        tab.setAttribute("aria-selected", String(active));
        tab.tabIndex = active ? 0 : -1;
      });
      move();
      if (focus) tabs[next].focus();
      const panel = document.getElementById(tabs[next].getAttribute("aria-controls")),
        direction = next > prior ? 1 : -1;
      const finish = () => {
        tabs.forEach((tab, index) => {
          const target = document.getElementById(tab.getAttribute("aria-controls"));
          target.hidden = index !== current;
          target.classList.remove("out", "pn");
        });
        panel.style.setProperty("--dir", direction);
        panel.classList.add("pn");
        document.dispatchEvent(
          new CustomEvent("socialmei-content-tab-change", { detail: { tab: name } }),
        );
        if (name === "agenda") agenda();
      };
      if (next === prior || matchMedia("(prefers-reduced-motion:reduce)").matches) {
        finish();
        return;
      }
      // Match the original exit/entry sequence; rapid clicks cancel obsolete work.
      previousPanel.style.setProperty("--dir", direction);
      previousPanel.classList.add("out");
      for (const tab of tabs) {
        const target = document.getElementById(tab.getAttribute("aria-controls"));
        if (!target.hidden) target.classList.add("out");
      }
      timer = setTimeout(finish, 160);
    }
    tabs.forEach((tab, index) => {
      tab.title = "Atalho: tecla " + (index + 1);
      tab.addEventListener("click", () => select(names[index]));
      tab.addEventListener("keydown", (event) => {
        const next =
          event.key === "ArrowRight"
            ? (current + 1) % 4
            : event.key === "ArrowLeft"
              ? (current + 3) % 4
              : event.key === "Home"
                ? 0
                : event.key === "End"
                  ? 3
                  : null;
        if (next !== null) {
          event.preventDefault();
          select(names[next], true);
        }
      });
    });
    document.addEventListener("keydown", (event) => {
      if (
        !visible() ||
        event.defaultPrevented ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        event.target.closest("input,textarea,select,[contenteditable]")
      )
        return;
      if (/^[1-4]$/.test(event.key)) {
        event.preventDefault();
        select(names[Number(event.key) - 1], true);
      }
    });
    document.addEventListener("focusin", (event) => {
      if (
        visible() &&
        innerWidth < 700 &&
        event.target.closest("input,textarea,select,[contenteditable]")
      )
        host.querySelector(".exact-v4-root").classList.add("kb");
    });
    document.addEventListener("focusout", () =>
      queueMicrotask(() => {
        if (
          !host.contains(document.activeElement) ||
          !document.activeElement.closest("input,textarea,select,[contenteditable]")
        )
          host.querySelector(".exact-v4-root").classList.remove("kb");
      }),
    );
    // Responsive labels and sidebar width can change after the resize event.
    const dockObserver = new ResizeObserver(() => {
      if (visible()) move();
    });
    tabs.forEach((tab) => dockObserver.observe(tab));
    dockObserver.observe(host);
    window.addEventListener("resize", move);
    document.fonts?.ready.then(move);
    document.addEventListener("socialmei-view-change", () => {
      if (visible()) requestAnimationFrame(move);
      else host.querySelector(".exact-v4-root").classList.remove("kb");
    });
    host.addEventListener("click", (event) => {
      if (
        event.target.closest(
          '[data-content-action="edit"],[data-content-action="duplicate"],[data-preparation-action="edit"],#contentNew',
        )
      )
        select("create");
    });
    const history = document.getElementById("preparationHistory");
    document.getElementById("exactV4-agendaList").append(history);
    const status = document.getElementById("preparationStatus");
    document.getElementById("contentSharedPreparation").prepend(status);
    const refresh = document.getElementById("preparationRefresh").parentElement;
    history.before(refresh);
    const repo = SocialMEIContentDrafts.repository(localStorage, () =>
      SocialMEIBusinessProfile.browserRepository().scope(),
    );
    const ymd = (date) => date.toLocaleDateString("sv-SE"),
      day = document.getElementById("contentAgendaDay"),
      strip = document.getElementById("exactV4-strip"),
      selectDraft = document.getElementById("exactV4-scheduleDraft"),
      at = document.getElementById("exactV4-scheduleTime"),
      schedule = document.getElementById("exactV4-sch");
    day.value = ymd(new Date());
    const all = document.createElement("button");
    all.type = "button";
    all.className = "btn sec";
    all.textContent = "Todos os agendamentos e preparações";
    all.addEventListener("click", () => {
      day.value = "";
      agenda();
    });
    strip.after(all);
    function localDay(job) {
      if (!job.scheduled_for) return "";
      return new Intl.DateTimeFormat("sv-SE", {
        timeZone: job.timezone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date(job.scheduled_for));
    }
    function drafts() {
      const selected = selectDraft.value,
        items = repo.read().items;
      selectDraft.replaceChildren();
      if (!items.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "Salve um rascunho primeiro";
        selectDraft.append(option);
      }
      items.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = item.title + " (" + SocialMEIContentDrafts.FORMATS[item.format] + ")";
        selectDraft.append(option);
      });
      if (items.some((item) => item.id === selected)) selectDraft.value = selected;
      const configured = SocialMEIContentPreparation.enabled(
        SOCIALMEI_CONFIG.contentPreparation,
        SocialMEIAuth.remote,
      );
      schedule.disabled =
        !configured ||
        !items.length ||
        !["owner", "admin", "member"].includes(SocialMEIAuth.current?.papel);
      document.getElementById("exactV4-scheduleHelp").textContent = configured
        ? "A próxima tela exige revisão, uma conta fictícia e confirmação antes de registrar a simulação. Nada é publicado."
        : "Agendamento compartilhado exige conta autenticada e modo de simulação habilitado no servidor. Nada foi conectado.";
    }
    function hint() {
      const item = repo.read().items.find((item) => item.id === selectDraft.value);
      if (!item) return;
      const hours = { story: "19:00", feed: "12:00", reel: "20:00" };
      at.value = hours[item.format];
      document.getElementById("exactV4-sh").textContent =
        "Horário sugerido para " +
        SocialMEIContentDrafts.FORMATS[item.format] +
        ": " +
        at.value +
        ". É só uma dica geral, não vem dos dados do seu perfil.";
    }
    selectDraft.addEventListener("change", hint);
    schedule.addEventListener("click", () => {
      if (schedule.disabled || !selectDraft.value) return;
      const date = day.value || ymd(new Date());
      if (date < ymd(new Date()) || !at.value) return;
      SocialMEIContentStudio.openDraft(selectDraft.value, () => {
        document.getElementById("preparationNew").click();
        document.getElementById("preparationWhen").value = date + "T" + at.value;
        document.getElementById("preparationReviewed").checked = false;
        select("create");
        host.querySelector(".native-v4-extra").open = true;
        document.getElementById("preparationReviewed").focus();
      });
    });
    function agenda() {
      const jobs = SocialMEIContentPreparation.jobs(),
        selected = day.value,
        filter = document.getElementById("contentAgendaStatus").value;
      strip.replaceChildren();
      const days = Array.from({ length: 14 }, (_, i) => {
        const d = new Date();
        d.setDate(d.getDate() + i);
        return ymd(d);
      });
      if (selected && !days.includes(selected)) days.push(selected);
      for (const key of days) {
        const date = new Date(key + "T12:00"),
          button = document.createElement("button");
        button.type = "button";
        button.className =
          "dy" +
          (jobs.some(
            (job) => localDay(job) === key && !["cancelled", "failed"].includes(job.status),
          )
            ? " ev"
            : "");
        button.dataset.d = key;
        button.setAttribute("aria-pressed", String(key === selected));
        button.setAttribute(
          "aria-label",
          date.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" }),
        );
        const small = document.createElement("small"),
          number = document.createElement("b");
        small.textContent = date.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
        number.textContent = date.getDate();
        button.append(small, number);
        button.addEventListener("click", () => {
          day.value = key;
          agenda();
        });
        strip.append(button);
      }
      document.getElementById("exactV4-dl").textContent = selected
        ? new Date(selected + "T12:00").toLocaleDateString("pt-BR", {
            weekday: "long",
            day: "numeric",
            month: "long",
          })
        : "Todos os agendamentos e preparações";
      const allowed = new Set(
        filterJobs(jobs, { status: filter, day: selected }).map((job) => job.id),
      );
      for (const row of history.querySelectorAll("[data-preparation-row]")) {
        row.hidden = !allowed.has(row.dataset.preparationRow);
        row.classList.add("it");
      }
      document.getElementById("contentAgendaCount").textContent =
        allowed.size + " preparação(ões) na seleção · salvas no negócio; somente simulação.";
      drafts();
    }
    for (const id of ["contentAgendaStatus", "contentAgendaDay"])
      document.getElementById(id).addEventListener("change", agenda);
    document.addEventListener("socialmei-content-drafts-change", () => {
      drafts();
    });
    document.addEventListener("socialmei-preparations-change", agenda);
    const home = document.createElement("aside");
    home.className = "content-home-agenda management-note";
    home.hidden = true;
    home.setAttribute("aria-label", "Próximos agendamentos simulados");
    document.querySelector("#clientHomeView .desk-opening")?.append(home);
    document.addEventListener("socialmei-preparations-change", () => {
      const upcoming = SocialMEIContentPreparation.jobs()
        .filter((job) => job.status === "scheduled" && Date.parse(job.scheduled_for) > Date.now())
        .sort((a, b) => Date.parse(a.scheduled_for) - Date.parse(b.scheduled_for))
        .slice(0, 3);
      home.replaceChildren();
      home.hidden = !upcoming.length;
      if (!upcoming.length) return;
      const title = document.createElement("strong");
      title.textContent = "Próximos agendamentos · somente simulação";
      home.append(title);
      for (const job of upcoming) {
        const p = document.createElement("p");
        p.textContent =
          job.title +
          " · " +
          new Date(job.scheduled_for).toLocaleString("pt-BR", { timeZone: job.timezone }) +
          " · " +
          job.timezone;
        home.append(p);
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "management-button";
      button.textContent = "Abrir agenda de testes";
      button.addEventListener("click", () => {
        setView("Divulgação");
        day.value = "";
        select("agenda");
      });
      home.append(button);
    });
    select("create");
    drafts();
    hint();
  }
  if (typeof document !== "undefined") init();
  const api = { filterJobs };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  return api;
})();
