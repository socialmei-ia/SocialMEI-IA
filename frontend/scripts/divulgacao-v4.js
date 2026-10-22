/* Divulgação V4 — progressive creator refinements on the native draft and preparation stores. */
(() => {
  "use strict";
  document.addEventListener("DOMContentLoaded", () => {
    const host = document.getElementById("contentStudioView");
    const form = document.getElementById("contentDraftForm");
    if (!host || !form) return;
    host.classList.add("dv4-enabled");
    const header = host.querySelector(".management-header");
    const ideas = [
      "Mostre o que seu cliente leva para casa",
      "Mostre os bastidores de hoje",
      "Conte o resultado de um serviço",
      "Responda uma dúvida frequente",
      "Apresente um produto ou serviço",
      "Compartilhe uma dica do seu negócio",
      "Agradeça aos clientes da semana",
    ];
    const day = new Date().getDay();
    const idea = ideas[day];
    const ideaBox = document.createElement("div");
    ideaBox.className = "dv4-idea";
    const copy = document.createElement("span");
    const small = document.createElement("small");
    small.textContent = "IDEIA PARA HOJE";
    const strong = document.createElement("strong");
    strong.textContent = idea;
    copy.append(small, strong);
    const use = document.createElement("button");
    use.type = "button";
    use.className = "management-button";
    use.textContent = "Usar ideia";
    use.setAttribute("aria-describedby", "dv4IdeaNote");
    const note = document.createElement("p");
    note.id = "dv4IdeaNote";
    note.className = "dv4-fine";
    note.textContent = "Sugestão de texto local. Nada é gerado ou publicado automaticamente.";
    ideaBox.append(copy, use, note);
    header.after(ideaBox);
    const progress = document.createElement("div");
    progress.className = "dv4-progress";
    progress.setAttribute("aria-label", "Progresso do rascunho");
    progress.innerHTML = `
      <div class="dv4-progress-header">
        <div><span class="dv4-kicker">ESTÚDIO DE CRIAÇÃO</span><strong id="dv4ProgressTitle">Seu conteúdo começa aqui.</strong>
        <p id="dv4NextStep">Escolha o formato e prepare seu texto.</p></div>
        <span id="dv4Percent" class="dv4-percent" aria-hidden="true">0%</span>
      </div>
      <div id="dv4ProgressBar" class="dv4-progress-track" role="progressbar"
           aria-label="Progresso do rascunho" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
        <span id="dv4ProgressFill"></span>
      </div>
      <ul class="dv4-checks" id="dv4Checks"></ul>
    `;
    document.getElementById("contentCreatePanel").prepend(progress);
    const title = document.getElementById("contentTitle");
    const caption = document.getElementById("contentCaption");
    const cta = document.getElementById("contentCta");
    const hashtags = document.getElementById("contentHashtags");
    const live = document.getElementById("contentActionStatus");
    const checks = [
      [
        "Escolheu o formato",
        () => !!host.querySelector('[data-content-format][aria-selected="true"]'),
      ],
      ["Escreveu o título", () => !!title.value.trim()],
      ["Preparou a legenda", () => !!caption.value.trim()],
      ["Incluiu uma chamada", () => !!cta.value.trim()],
      ["Adicionou hashtags", () => !!hashtags.value.trim()],
      [
        "Selecionou uma mídia",
        () => !!document.querySelector("#contentPreviewStage img, #contentPreviewStage video"),
      ],
    ];
    const update = () => {
      const current = checks.map(([label, fn]) => [label, !!fn()]);
      const finished = current.filter(([, ok]) => ok).length;
      const percent = Math.round((finished / checks.length) * 100);
      document.getElementById("dv4Percent").textContent = percent + "%";
      const bar = document.getElementById("dv4ProgressBar");
      bar.setAttribute("aria-valuenow", String(percent));
      document.getElementById("dv4ProgressFill").style.width = percent + "%";
      document.getElementById("dv4ProgressTitle").textContent =
        finished === checks.length
          ? "Pronto para revisão."
          : finished > 2
            ? "Está ficando bom."
            : "Seu conteúdo começa aqui.";
      const next = current.find(([, ok]) => !ok);
      document.getElementById("dv4NextStep").textContent = next
        ? "Você pode continuar com: " + next[0].toLowerCase() + "."
        : "Você pode revisar e salvar seu rascunho. A publicação externa permanece desconectada.";
      const list = document.getElementById("dv4Checks");
      list.replaceChildren();
      for (const [label, done] of current) {
        const item = document.createElement("li");
        item.textContent = label;
        item.className = done ? "is-complete" : "";
        list.append(item);
      }
    };
    use.addEventListener("click", () => {
      if (
        (title.value.trim() || caption.value.trim()) &&
        !window.confirm("Substituir o título e a legenda atuais pela ideia de hoje?")
      )
        return;
      title.value = idea.slice(0, 80);
      caption.value = `${idea}. Conte um pouco sobre seu negócio e mostre ao cliente como você pode ajudar. Fale com a gente para saber mais.`;
      for (const field of [title, caption])
        field.dispatchEvent(new Event("input", { bubbles: true }));
      update();
      live.textContent = "Ideia aplicada ao editor. Revise antes de salvar; nada foi publicado.";
      document.getElementById("contentWorkspace-create")?.click();
      title.focus();
    });
    for (const name of ["input", "change"]) form.addEventListener(name, update);
    host
      .querySelectorAll("[data-content-format]")
      .forEach((tab) => tab.addEventListener("click", () => requestAnimationFrame(update)));
    document.addEventListener("socialmei-content-tab-change", () => requestAnimationFrame(update));
    const mediaStage = document.getElementById("contentPreviewStage");
    if (mediaStage)
      new MutationObserver(update).observe(mediaStage, { childList: true, subtree: false });
    const oldLabel = host.querySelector("#contentStudioTitle + p");
    if (oldLabel)
      oldLabel.textContent =
        "Crie, revise e organize seus conteúdos. Seus canais continuam desconectados até a homologação.";
    update();
  });
})();
