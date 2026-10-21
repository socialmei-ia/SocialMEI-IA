/* Local publication planning. Never schedules or submits to n8n/Meta. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIPublicationPlan = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const KEY = "socialmei-publication-plans-v1:";
  const LIMIT = 30;
  const FORMATS = ["feed", "story", "reel"];
  function validPlan(value, now = Date.now()) {
    if (!value || !FORMATS.includes(value.format)) throw new Error("Escolha Feed, Story ou Reel.");
    if (typeof value.title !== "string" || !value.title.trim() || value.title.length > 80)
      throw new Error("Informe um título com até 80 caracteres.");
    if (typeof value.caption !== "string" || value.caption.length > 2200)
      throw new Error("Confira o tamanho da legenda.");
    if (typeof value.when !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value.when))
      throw new Error("Informe a data e a hora desejadas.");
    const stamp = new Date(value.when).getTime();
    if (!Number.isFinite(stamp) || stamp <= now + 60000)
      throw new Error("Escolha um horário futuro com pelo menos 1 minuto de antecedência.");
    if (stamp > now + 60 * 86400000) throw new Error("Planeje datas dentro dos próximos 60 dias.");
    return {
      format: value.format,
      title: value.title.trim(),
      caption: value.caption,
      when: value.when,
      mediaName: typeof value.mediaName === "string" ? value.mediaName.slice(0, 120) : "",
    };
  }
  function createRepository(storage, scope, clock = () => Date.now()) {
    function key() {
      const id = scope();
      if (!id || typeof id !== "string") throw new Error("Entre no seu negócio antes de planejar.");
      return KEY + id;
    }
    function read() {
      const source = storage.getItem(key());
      if (!source) return [];
      let items;
      try {
        items = JSON.parse(source);
      } catch (_) {
        throw new Error("Não foi possível ler o planejamento. Nenhum dado foi substituído.");
      }
      if (
        !Array.isArray(items) ||
        items.length > LIMIT ||
        items.some(
          (item) =>
            !item ||
            typeof item.id !== "string" ||
            typeof item.title !== "string" ||
            typeof item.when !== "string" ||
            !FORMATS.includes(item.format),
        )
      )
        throw new Error("Planejamento incompatível. Nenhum dado foi substituído.");
      return items;
    }
    function write(items) {
      storage.setItem(key(), JSON.stringify(items));
    }
    function add(input) {
      const plan = validPlan(input, clock());
      const items = read();
      if (items.length >= LIMIT) throw new Error("Limite de 30 planejamentos neste navegador.");
      const result = {
        ...plan,
        id: "plan-" + crypto.randomUUID(),
        createdAt: new Date(clock()).toISOString(),
      };
      write([...items, result]);
      return result;
    }
    function remove(id) {
      const items = read();
      const next = items.filter((item) => item.id !== id);
      if (next.length === items.length) throw new Error("Planejamento não encontrado.");
      write(next);
    }
    return { read, add, remove };
  }
  function init() {
    const section = document.getElementById("publicationPlanning");
    if (!section) return;
    const byId = (id) => document.getElementById(id);
    const profile = SocialMEIBusinessProfile.browserRepository();
    const repository = createRepository(localStorage, () => profile.scope());
    let previousScope = null;
    function setStatus(text) {
      byId("publicationPlanningStatus").textContent = text;
    }
    function render() {
      const list = byId("publicationPlanningList");
      list.replaceChildren();
      const current = profile.scope();
      if (current !== previousScope) {
        previousScope = current;
        byId("publicationPlanningForm").reset();
        setStatus("");
      }
      let items;
      try {
        items = repository.read().sort((a, b) => a.when.localeCompare(b.when));
      } catch (error) {
        setStatus(error.message);
        return;
      }
      byId("publicationPlanningCount").textContent = items.length + " de 30 planejamentos locais";
      if (!items.length) {
        const empty = document.createElement("p");
        empty.textContent = "Nenhuma publicação planejada neste navegador.";
        list.append(empty);
      }
      for (const item of items) {
        const row = document.createElement("li");
        const detail = document.createElement("span");
        const format = { feed: "Feed", story: "Story", reel: "Reel" }[item.format];
        const date = new Date(item.when);
        detail.textContent =
          item.title +
          " · " +
          format +
          " · " +
          (Number.isNaN(date.getTime()) ? item.when : date.toLocaleString("pt-BR")) +
          " · Somente planejamento";
        const control = document.createElement("button");
        control.type = "button";
        control.className = "management-button";
        control.textContent = "Remover";
        control.setAttribute("aria-label", "Remover planejamento " + item.title);
        control.addEventListener("click", () => {
          if (profile.scope() !== current) return render();
          try {
            repository.remove(item.id);
            setStatus("Planejamento removido. Nenhuma publicação externa foi afetada.");
            render();
          } catch (error) {
            setStatus(error.message);
          }
        });
        row.append(detail, control);
        list.append(row);
      }
    }
    byId("publicationPlanningForm").addEventListener("submit", (event) => {
      event.preventDefault();
      try {
        const state = SocialMEIContentStudio.simulationSnapshot();
        const title = byId("contentTitle").value.trim();
        const caption = SocialMEIContentDrafts.caption({
          title,
          caption: byId("contentCaption").value,
          cta: byId("contentCta").value,
          hashtags: byId("contentHashtags").value,
          format:
            document.querySelector('[data-content-format][aria-selected="true"]')?.dataset
              .contentFormat || "feed",
        });
        const format =
          document.querySelector('[data-content-format][aria-selected="true"]')?.dataset
            .contentFormat || "feed";
        repository.add({
          title,
          caption,
          format,
          when: byId("publicationPlanningWhen").value,
          mediaName: state?.media?.name || "",
        });
        byId("publicationPlanningForm").reset();
        setStatus("Data salva para seu planejamento local. Nada foi agendado no n8n ou publicado.");
        render();
      } catch (error) {
        setStatus(error.message);
      }
    });
    document.addEventListener("socialmei-view-change", () => {
      if (typeof currentView !== "undefined" && currentView === "Divulgação") render();
    });
    document.addEventListener("socialmei-data-change", () => {
      if (profile.scope() !== previousScope) render();
    });
    window.addEventListener("storage", (event) => {
      if (event.key === null || (previousScope && event.key === KEY + previousScope)) render();
    });
    render();
  }
  if (typeof document !== "undefined") {
    if (document.readyState === "loading")
      document.addEventListener("DOMContentLoaded", init, { once: true });
    else init();
  }
  return { createRepository, validPlan, LIMIT };
});
