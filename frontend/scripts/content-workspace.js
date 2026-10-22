/* Accessible content workspace over the existing editor and scoped preparation store. */
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
    const tabs = [...host.querySelectorAll("[data-content-workspace-tab]")];
    const descriptions = {
      create: ["plus", "Criar conteúdo", "Ideias e legendas locais"],
      drafts: ["note", "Rascunhos", "Conteúdos neste navegador"],
      agenda: ["detail", "Agenda", "Preparações e testes"],
      connections: ["ig", "Conexões", "Canais e permissões"],
    };
    tabs.forEach((tab) => {
      const [icon, label, description] = descriptions[tab.dataset.contentWorkspaceTab];
      tab.innerHTML = `${renderIcon(icon)}<span><strong>${label}</strong><small>${description}</small></span>`;
    });
    const formats = host.querySelector(".content-formats");
    const formatHeading = document.createElement("div");
    formatHeading.className = "content-step-heading";
    formatHeading.innerHTML =
      '<span aria-hidden="true">1</span><div><h3>Escolha o formato</h3><p>Defina onde o conteúdo será publicado para conferir o enquadramento.</p></div>';
    formats.before(formatHeading);
    const formatIcons = { story: "detail", feed: "ig", reel: "bolt" };
    formats.querySelectorAll("[data-content-format]").forEach((button) => {
      button.insertAdjacentHTML(
        "afterbegin",
        renderIcon(formatIcons[button.dataset.contentFormat]),
      );
    });
    for (const [id, number] of [
      ["contentPreparationHeading", "2"],
      ["contentPreparationScheduleHeading", "4"],
    ]) {
      const heading = document.getElementById(id);
      heading.classList.add("content-numbered-heading");
      heading.dataset.step = number;
    }
    const editorHeading = document.createElement("h3");
    editorHeading.className = "content-numbered-heading";
    editorHeading.dataset.step = "3";
    editorHeading.textContent = "Ajuste o conteúdo e salve";
    document.getElementById("contentDraftForm").prepend(editorHeading);
    host
      .querySelector(".content-preview-heading h3")
      .insertAdjacentHTML("afterbegin", renderIcon("ig"));
    document.getElementById("contentNew").innerHTML = renderIcon("plus") + "Novo rascunho";
    document
      .getElementById("preparationCaptions")
      .insertAdjacentHTML("afterbegin", renderIcon("bolt"));
    const mediaInput = document.getElementById("contentMedia");
    const mediaButton = document.createElement("button");
    mediaButton.type = "button";
    mediaButton.className = "management-button content-media-picker";
    mediaButton.innerHTML = renderIcon("plus") + "Selecionar imagem ou vídeo";
    mediaButton.setAttribute("aria-describedby", "contentMediaHelp contentMediaStatus");
    mediaButton.addEventListener("click", () => mediaInput.click());
    mediaInput.before(mediaButton);
    mediaInput.classList.add("content-native-media");
    mediaInput.tabIndex = -1;
    const reflectMediaAccess = () => {
      mediaButton.disabled = mediaInput.disabled;
    };
    new MutationObserver(reflectMediaAccess).observe(mediaInput, {
      attributes: true,
      attributeFilter: ["disabled"],
    });
    reflectMediaAccess();
    function select(name, focus = false) {
      tabs.forEach((tab) => {
        const active = tab.dataset.contentWorkspaceTab === name;
        tab.setAttribute("aria-selected", String(active));
        tab.tabIndex = active ? 0 : -1;
        document.getElementById(tab.getAttribute("aria-controls")).hidden = !active;
        if (active && focus) tab.focus();
      });
      document.dispatchEvent(
        new CustomEvent("socialmei-content-tab-change", { detail: { tab: name } }),
      );
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => select(tab.dataset.contentWorkspaceTab));
      tab.addEventListener("keydown", (event) => {
        let next =
          event.key === "ArrowRight"
            ? (index + 1) % tabs.length
            : event.key === "ArrowLeft"
              ? (index + tabs.length - 1) % tabs.length
              : event.key === "Home"
                ? 0
                : event.key === "End"
                  ? tabs.length - 1
                  : null;
        if (next !== null) {
          event.preventDefault();
          select(tabs[next].dataset.contentWorkspaceTab, true);
        }
      });
    });
    const status = document.getElementById("preparationStatus");
    host.querySelector(".content-workspace-tabs").before(status);
    const history = document.getElementById("preparationHistory");
    document
      .getElementById("contentAgendaPanel")
      .append(document.getElementById("preparationRefresh").parentElement, history);
    const agendaEmpty = document.createElement("p");
    agendaEmpty.className = "content-library-empty";
    agendaEmpty.textContent =
      "Nenhuma preparação neste filtro. Crie e revise um conteúdo para preparar um teste; nenhuma publicação é automática.";
    history.after(agendaEmpty);
    function filter() {
      const jobs = SocialMEIContentPreparation.jobs(),
        allowed = new Set(
          filterJobs(jobs, {
            status: document.getElementById("contentAgendaStatus").value,
            day: document.getElementById("contentAgendaDay").value,
          }).map((j) => j.id),
        );
      history
        .querySelectorAll("[data-preparation-row]")
        .forEach((row) => (row.hidden = !allowed.has(row.dataset.preparationRow)));
      agendaEmpty.hidden = allowed.size > 0 || (!jobs.length && !!history.textContent.trim());
      document.getElementById("contentAgendaCount").textContent =
        allowed.size + " preparação(ões) na seleção · salvas no negócio; somente simulação.";
    }
    for (const id of ["contentAgendaStatus", "contentAgendaDay"])
      document.getElementById(id).addEventListener("change", filter);
    const home = document.createElement("aside");
    home.className = "content-home-agenda management-note";
    home.hidden = true;
    home.setAttribute("aria-label", "Próximos agendamentos simulados");
    document.querySelector("#clientHomeView .desk-opening")?.append(home);
    function homeAgenda() {
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
        const text = document.createElement("p");
        text.textContent =
          job.title +
          " · " +
          new Date(job.scheduled_for).toLocaleString("pt-BR", { timeZone: job.timezone }) +
          " · " +
          job.timezone;
        home.append(text);
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "management-button";
      button.textContent = "Abrir agenda de testes";
      button.addEventListener("click", () => {
        setView("Divulgação");
        select("agenda");
      });
      home.append(button);
    }
    document.addEventListener("socialmei-preparations-change", () => {
      filter();
      homeAgenda();
    });
    host.addEventListener("click", (event) => {
      if (
        event.target.closest(
          '[data-content-action="edit"],[data-content-action="duplicate"],[data-preparation-action="edit"],#contentNew',
        )
      )
        select("create");
    });
    filter();
    select("create");
  }
  if (typeof document !== "undefined") init();
  const api = { filterJobs };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  return api;
})();
