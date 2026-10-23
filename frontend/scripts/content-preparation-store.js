/* Shared preparation is an explicit, authenticated simulation. Never calls a provider. */
const SocialMEIContentPreparation = (() => {
  "use strict";
  const enabled = (config, remote) => config?.mode === "simulation" && remote === true;
  function captionAlternatives({
    topic,
    offering = "",
    business = "",
    objective = "informar",
    tone = "simples",
    style = "native",
  }) {
    const subject = String(topic || "")
      .trim()
      .slice(0, 160);
    if (!subject) throw new Error("Informe o tema da publicação.");
    if (style === "v4") {
      const templates = {
        Profissional: [
          "{t}: conheça nosso serviço de {p}. Qualidade e cuidado em cada detalhe.",
          "Atendimento de {p} com dedicação. Fale com a gente e saiba mais.",
          "{p} feito com atenção. {t} é o que nos move todos os dias.",
        ],
        Próximo: [
          "Oi! Hoje quero falar sobre {t}. Vem conhecer meu {p}, vai ser um prazer te atender.",
          "Quer saber mais sobre {p}? Me chama, a gente conversa sem pressa.",
          "Todo dia é um jeito novo de fazer {p}. Me conta o que você precisa.",
        ],
        Divertido: [
          "Alerta de novidade: {p} chegou para animar o seu dia! {t}",
          "Dizem que {p} muda o astral. Vem testar e conta pra gente!",
          "{t} + {p} = combinação perfeita. Bora?",
        ],
      };
      const endings = {
        Apresentar: "Prazer em conhecer você!",
        Vender: "Condições especiais por tempo limitado.",
        "Divulgar promoção": "Promoção ativa. Garanta a sua.",
        Engajar: "Comente o que você acha!",
      };
      return {
        source: "template_fixture",
        generated_by_ai: false,
        requires_human_verification: true,
        alternatives: (templates[tone] || templates.Profissional).map(
          (template) =>
            template.replace("{t}", subject).replace("{p}", offering.trim().slice(0, 60)) +
            " " +
            (endings[objective] || endings.Apresentar),
        ),
        hashtags: [],
      };
    }
    const about = offering.trim() ? " Sobre: " + offering.trim().slice(0, 160) + "." : "";
    const brand = business.trim() ? " — " + business.trim().slice(0, 120) : "";
    const endings = {
      informar: "Converse com a gente para conferir os detalhes.",
      apresentar: "Quer conhecer melhor? Tire suas dúvidas com a gente.",
      convidar: "Se fizer sentido para você, fale com a gente.",
    };
    const greeting = { simples: "", acolhedor: "Vamos conversar? ", profissional: "Saiba mais: " };
    return {
      source: "template_fixture",
      generated_by_ai: false,
      alternatives: [
        (greeting[tone] || "") +
          subject +
          "." +
          about +
          " " +
          (endings[objective] || endings.informar) +
          brand,
        subject + about + "\nQuer mais informações? Envie sua dúvida." + brand,
        "Vamos falar sobre " + subject + "?" + about + "\nConfira os detalhes com a gente." + brand,
      ],
      hashtags: ["#MeuNegocio", "#Empreendedorismo"],
    };
  }
  function zonedInstant(local, zone) {
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local))
      throw new Error("Confira a data e o horário.");
    const target = local.replace("T", " ");
    const formatter = new Intl.DateTimeFormat("sv-SE", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    });
    const approximate = Date.parse(local + ":00Z");
    if (!Number.isFinite(approximate)) throw new Error("Confira a data.");
    const matches = [];
    for (let offset = -14 * 60; offset <= 14 * 60; offset += 15) {
      const candidate = new Date(approximate + offset * 60000);
      if (formatter.format(candidate) === target) matches.push(candidate.toISOString());
    }
    if (matches.length !== 1)
      throw new Error("Horário inexistente ou ambíguo neste fuso. Escolha outro horário.");
    return matches[0];
  }
  function localTime(instant, zone) {
    return new Intl.DateTimeFormat("sv-SE", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .format(new Date(instant))
      .replace(" ", "T");
  }
  function errorMessage(error) {
    const message = String(error?.message || error || "Não foi possível concluir esta ação.");
    const suffix = " Nenhuma publicação real foi feita.";
    if (error?.status === 401)
      return (
        "Sua sessão expirou ou não está autenticada. Entre novamente antes de continuar." + suffix
      );
    if (error?.status === 403)
      return (
        "Sua conta não tem permissão para esta ação. Confira o acesso com o responsável pelo negócio." +
        suffix
      );
    if (error?.status === 409)
      return (
        "A preparação mudou em outra sessão ou a configuração não permite esta ação. Atualize o histórico e revise antes de tentar novamente." +
        suffix
      );
    if (error?.status === 503)
      return (
        "A preparação compartilhada está temporariamente indisponível. Tente atualizar mais tarde." +
        suffix
      );
    if (error?.status === 404)
      return (
        "A preparação ou o recurso solicitado não está disponível neste negócio. Atualize o histórico." +
        suffix
      );
    if (/Failed to fetch|NetworkError|Load failed/i.test(message))
      return (
        "Não foi possível conectar ao servidor de testes. Confira sua conexão e o endereço HTTPS e tente atualizar." +
        suffix
      );
    if (error?.name === "AbortError")
      return (
        "O servidor demorou a responder. Atualize o histórico antes de repetir a ação." + suffix
      );
    return message;
  }
  const labels = {
    draft: "Rascunho",
    pending_review: "Aguardando revisão",
    scheduled: "Agendado · teste",
    processing: "Processando · teste",
    simulated: "Simulação concluída",
    failed: "Falhou",
    uncertain: "Resultado incerto · revisar",
    cancelled: "Cancelado",
  };
  let publishedJobs = [];
  function publishJobs(items) {
    publishedJobs = items;
    document.dispatchEvent(new Event("socialmei-preparations-change"));
  }
  function init() {
    const parent =
      document.getElementById("contentSharedPreparation") ||
      document.getElementById("contentEditorPanel");
    if (!parent) return;
    const panel = document.createElement("section");
    panel.className = "content-preparation-workflow";
    panel.setAttribute("aria-labelledby", "contentPreparationHeading");
    panel.innerHTML = `<h3 id="contentPreparationHeading">Da ideia à revisão</h3>
      <p>Prepare o texto e acompanhe os testes. Legendas usam um modelo local demonstrativo; IA e geração de imagens ainda não estão conectadas.</p>
      <div class="content-preparation-fields">
        <label>Tema <input id="preparationTopic" maxlength="160" placeholder="O que você quer apresentar?"></label>
        <label>Produto ou serviço informado por você <input id="preparationOffering" maxlength="160" placeholder="Opcional · somente informações confirmadas"></label>
        <label>Objetivo <select id="preparationObjective"><option value="informar">Informar</option><option value="apresentar">Apresentar</option><option value="convidar">Convidar para conversar</option></select></label>
        <label>Tom <select id="preparationTone"><option value="simples">Simples</option><option value="acolhedor">Acolhedor</option><option value="profissional">Profissional</option></select></label>
      </div>
      <button type="button" class="management-button" id="preparationCaptions">Sugerir legendas por modelo local</button>
      <div id="preparationAlternatives" class="content-preparation-alternatives"></div>
      <p>Imagem/vídeo: use o seletor de mídia do editor. Nenhuma imagem é gerada por este modelo.</p>
      <h3 id="contentPreparationScheduleHeading">Preparação compartilhada · teste isolado</h3>
      <p id="preparationMode">Agendamentos exigem sessão autenticada e ativação explícita do modo de testes no servidor. Nada é publicado.</p>
      <div class="content-preparation-fields">
        <label>Conta fictícia <select id="preparationAccount" aria-describedby="preparationMode"></select></label>
        <label>Nome para uma conta de teste <input id="preparationAccountName" maxlength="80"></label>
      </div>
      <button type="button" class="management-button" id="preparationCreateAccount">Criar conta fictícia</button>
      <div class="content-preparation-fields">
        <label>Data e horário do teste <input type="datetime-local" id="preparationWhen"></label>
        <label>Fuso horário <select id="preparationZone"><option value="America/Fortaleza">Fortaleza · America/Fortaleza</option><option value="America/Sao_Paulo">São Paulo · America/Sao_Paulo</option><option value="America/Manaus">Manaus · America/Manaus</option></select></label>
      </div>
      <p id="preparationReviewSummary" aria-live="polite"></p>
      <label class="content-preparation-review"><input type="checkbox" id="preparationReviewed">Revisei a legenda, a mídia e a conta fictícia. Quero somente simular.</label>
      <div class="content-preparation-actions">
        <button type="button" class="management-button" id="preparationSave">Salvar preparação compartilhada</button>
        <button type="button" class="management-button" id="preparationReview">Enviar para revisão</button>
        <button type="button" class="management-button" id="preparationSchedule">Agendar teste</button>
        <button type="button" class="management-button" id="preparationNew">Nova preparação</button>
      </div>
      <p id="preparationStatus" role="status" aria-live="polite"></p>
      <div class="content-preparation-actions"><button type="button" class="management-button" id="preparationRefresh">Atualizar histórico</button><button type="button" class="management-button" id="preparationRun">Processar testes vencidos</button></div>
      <p>O teste persiste somente texto e metadados. A mídia não é enviada ou armazenada. O processamento é manual neste laboratório; não há publicação, cron em produção ou conexão Meta/n8n.</p>
      <ul id="preparationHistory" class="content-preparation-history" aria-label="Histórico de preparações compartilhadas"></ul>`;
    const idea = document.createElement("section");
    idea.className = "content-preparation-workflow content-preparation-idea";
    idea.setAttribute("aria-labelledby", "contentPreparationHeading");
    while (panel.firstChild && panel.firstChild.id !== "contentPreparationScheduleHeading")
      idea.append(panel.firstChild);
    panel.setAttribute("aria-labelledby", "contentPreparationScheduleHeading");
    parent.prepend(idea);
    parent.append(panel);
    const byId = (id) => document.getElementById(id),
      repository = SocialMEIBusinessProfile.browserRepository(),
      request = async (path, method = "GET", data) => {
        const expected = repository.scope(),
          workspace = SocialMEIAuth.current?.negocio?.id;
        const result = await SocialMEIAuth.request("/content/preparation" + path, method, data);
        if (
          !expected ||
          expected !== repository.scope() ||
          result.workspace_id !== workspace ||
          SocialMEIAuth.current?.negocio?.id !== workspace
        )
          throw new Error(
            "A sessão mudou ou a resposta não pertence a este negócio. Atualize os dados antes de continuar.",
          );
        return result;
      },
      scope = () => repository.scope();
    let epoch = 0,
      identity = scope(),
      working = false,
      available = false,
      accounts = [],
      jobs = [],
      active = null,
      intent = null;
    const say = (text) => {
      byId("preparationStatus").textContent = errorMessage(text);
    };
    const configured = () => enabled(SOCIALMEI_CONFIG.contentPreparation, SocialMEIAuth.remote);
    const writable = () =>
      available && ["owner", "admin", "member"].includes(SocialMEIAuth.current?.papel);
    function controls() {
      for (const id of [
        "preparationSave",
        "preparationReview",
        "preparationSchedule",
        "preparationRun",
        "preparationAccount",
        "preparationWhen",
        "preparationZone",
        "preparationReviewed",
      ])
        byId(id).disabled = working || !writable();
      byId("preparationCreateAccount").disabled =
        working || !available || !["owner", "admin"].includes(SocialMEIAuth.current?.papel);
      byId("preparationRefresh").disabled = working || !configured();
      byId("preparationCaptions").disabled = working;
      panel.querySelectorAll("[data-preparation-action]").forEach((b) => {
        b.disabled = working || (!writable() && b.dataset.preparationAction !== "view");
      });
    }
    function resetIdentity() {
      const changed = identity !== scope();
      if (changed) {
        epoch++;
        identity = scope();
        available = false;
        accounts = [];
        jobs = [];
        publishJobs([]);
        active = null;
        intent = null;
        byId("preparationAlternatives").replaceChildren();
        for (const id of [
          "preparationTopic",
          "preparationOffering",
          "preparationWhen",
          "preparationAccountName",
        ])
          byId(id).value = "";
        byId("preparationReviewed").checked = false;
        byId("preparationAccount").replaceChildren();
        byId("preparationHistory").replaceChildren();
        say("A sessão mudou. Confira os dados do negócio atual.");
      }
      return changed;
    }
    function renderHistory() {
      const list = byId("preparationHistory");
      list.replaceChildren();
      if (!jobs.length) {
        const li = document.createElement("li");
        li.textContent = "Nenhuma preparação compartilhada neste negócio.";
        list.append(li);
      }
      for (const job of jobs) {
        const li = document.createElement("li"),
          text = document.createElement("p"),
          actions = document.createElement("div");
        text.textContent =
          (job.title || "Sem título") +
          " · " +
          (labels[job.status] || job.status) +
          (job.scheduled_for
            ? " · " +
              new Date(job.scheduled_for).toLocaleString("pt-BR", { timeZone: job.timezone }) +
              " · " +
              job.timezone
            : "") +
          (job.last_error_code ? " · confira os detalhes antes de repetir" : "");
        li.dataset.preparationRow = job.id;
        li.append(text);
        actions.className = "content-preparation-actions";
        for (const [action, label] of [
          ["view", "Ver detalhes"],
          ...(!["processing", "simulated", "cancelled", "uncertain"].includes(job.status)
            ? [
                ["edit", "Editar"],
                ["cancel", "Cancelar"],
              ]
            : []),
        ]) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "management-button";
          button.textContent = label;
          button.dataset.preparationAction = action;
          button.dataset.preparationId = job.id;
          actions.append(button);
        }
        li.append(actions);
        list.append(li);
      }
      publishJobs(jobs);
      controls();
    }
    async function refresh() {
      resetIdentity();
      if (!configured()) {
        available = false;
        publishJobs([]);
        controls();
        return;
      }
      const seq = ++epoch,
        expected = scope();
      try {
        await SocialMEIAuth.ready;
        if (!SocialMEIAuth.current)
          throw new Error("Entre em uma conta para consultar preparações compartilhadas.");
        const [status, a, j] = await Promise.all([
          request("/status"),
          request("/accounts"),
          request("/jobs"),
        ]);
        if (seq !== epoch || expected !== scope()) return;
        available = status.mode === "simulation";
        accounts = a.items;
        jobs = j.items;
        const selected = byId("preparationAccount").value;
        byId("preparationAccount").replaceChildren();
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "Selecione uma conta fictícia";
        byId("preparationAccount").append(empty);
        for (const account of accounts) {
          const option = document.createElement("option");
          option.value = account.id;
          option.textContent = account.label + " · fictícia";
          byId("preparationAccount").append(option);
        }
        if (accounts.some((a) => a.id === selected)) byId("preparationAccount").value = selected;
        byId("preparationMode").textContent =
          "Teste autenticado e persistido no negócio atual. Sem transporte externo, upload ou publicação.";
        renderHistory();
      } catch (error) {
        if (seq !== epoch || expected !== scope()) return;
        available = false;
        accounts = [];
        jobs = [];
        publishJobs([]);
        byId("preparationAccount").replaceChildren();
        byId("preparationHistory").replaceChildren();
        say(error);
      } finally {
        if (seq === epoch) controls();
      }
    }
    async function action(task) {
      if (working || resetIdentity()) return;
      const expected = scope();
      epoch++;
      working = true;
      controls();
      try {
        await task(expected);
      } catch (error) {
        if (expected === scope())
          say(
            errorMessage(error) +
              (errorMessage(error).includes("Nenhuma publicação real")
                ? ""
                : " Nenhuma publicação real foi feita."),
          );
      } finally {
        working = false;
        if (expected !== scope()) resetIdentity();
        controls();
      }
    }
    byId("preparationCaptions").addEventListener("click", () =>
      action(async (expected) => {
        const input = {
          topic: byId("preparationTopic").value,
          offering: byId("preparationOffering").value,
          objective: byId("preparationObjective").value,
          tone: byId("preparationTone").value,
          business:
            repository.read().profile?.businessName || SocialMEIAuth.current?.negocio?.nome || "",
        };
        const result = available
          ? await request("/captions", "POST", input)
          : captionAlternatives(input);
        if (expected !== scope()) return;
        byId("preparationAlternatives").replaceChildren();
        result.alternatives.forEach((caption, index) => {
          const wrapper = document.createElement("div"),
            text = document.createElement("p"),
            button = document.createElement("button");
          text.textContent = caption;
          button.type = "button";
          button.className = "management-button";
          button.textContent = "Usar alternativa " + (index + 1);
          button.addEventListener("click", () => {
            if (expected !== scope() || resetIdentity()) return;
            byId("contentCaption").value = caption;
            byId("contentHashtags").value = result.hashtags.join(" ");
            byId("contentCaption").dispatchEvent(new Event("input", { bubbles: true }));
            const step = byId("contentCaption").closest("details");
            if (step) step.open = true;
            byId("contentCaption").focus();
            say("Texto aplicado ao editor. Revise e salve; modelo local, sem IA externa.");
          });
          wrapper.append(text, button);
          byId("preparationAlternatives").append(wrapper);
        });
        say(
          "Três sugestões por modelo local demonstrativo. Confira fatos e hashtags antes de usar.",
        );
      }),
    );
    byId("preparationCreateAccount").addEventListener("click", () =>
      action(async (expected) => {
        const result = await request("/accounts", "POST", {
          label: byId("preparationAccountName").value.trim(),
        });
        if (expected !== scope()) return;
        await refresh();
        byId("preparationAccount").value = result.id;
        byId("preparationAccountName").value = "";
        say("Conta fictícia criada. Nenhuma conta Instagram foi conectada.");
      }),
    );
    function snapshot(status) {
      const value = SocialMEIContentStudio.preparationSnapshot();
      if (!value || !scope()?.startsWith("account:"))
        throw new Error("Entre em uma conta válida para compartilhar esta preparação.");
      return {
        title: value.title,
        format: value.format,
        caption: value.caption,
        media: value.media ? [value.media] : [],
        account_id: byId("preparationAccount").value || null,
        status,
        reviewed: byId("preparationReviewed").checked,
        timezone: byId("preparationZone").value,
        scheduled_for:
          status === "scheduled"
            ? zonedInstant(byId("preparationWhen").value, byId("preparationZone").value)
            : null,
      };
    }
    for (const [id, status] of [
      ["preparationSave", "draft"],
      ["preparationReview", "pending_review"],
      ["preparationSchedule", "scheduled"],
    ])
      byId(id).addEventListener("click", () =>
        action(async (expected) => {
          const body = snapshot(status),
            signature = JSON.stringify(body);
          if (!intent || intent.signature !== signature)
            intent = { signature, key: crypto.randomUUID() };
          const result = active
            ? await request("/jobs/" + active.id, "PUT", {
                ...body,
                idempotency_key: active.idempotency_key,
                revision: active.revision,
              })
            : await request("/jobs", "POST", { ...body, idempotency_key: intent.key });
          if (expected !== scope()) return;
          active = result;
          intent = null;
          await refresh();
          say(
            (labels[result.status] || result.status) +
              " salvo no negócio atual. Somente simulação; nada será publicado.",
          );
        }),
      );
    byId("preparationNew").addEventListener("click", () => {
      active = null;
      intent = null;
      byId("preparationReviewed").checked = false;
      say("Próximo salvamento cria uma nova preparação compartilhada. Seu editor foi preservado.");
    });
    byId("preparationRun").addEventListener("click", () =>
      action(async (expected) => {
        const result = await request("/run-due", "POST", {});
        if (expected !== scope()) return;
        await refresh();
        say(
          result.items.length +
            " teste(s) vencido(s) processado(s). Nada foi publicado ou enviado.",
        );
      }),
    );
    byId("preparationRefresh").addEventListener("click", () => {
      if (!working) refresh();
    });
    byId("preparationHistory").addEventListener("click", (event) => {
      const button = event.target.closest("[data-preparation-action]");
      if (!button) return;
      const job = jobs.find((j) => j.id === button.dataset.preparationId);
      if (!job) return;
      action(async (expected) => {
        if (button.dataset.preparationAction === "edit") {
          SocialMEIContentStudio.loadPreparation(job, () => {
            if (expected !== scope()) return;
            active = job;
            intent = null;
            byId("preparationAccount").value = job.account_id || "";
            byId("preparationZone").value = job.timezone;
            byId("preparationWhen").value = job.scheduled_for
              ? localTime(job.scheduled_for, job.timezone)
              : "";
            byId("preparationReviewed").checked = false;
            byId("contentTitle").focus();
            say(
              "Preparação aberta para editar. Revise antes de salvar ou reagendar; a mídia continua sendo somente uma referência.",
            );
          });
        } else if (button.dataset.preparationAction === "cancel") {
          await request("/jobs/" + job.id + "/cancel", "POST", { revision: job.revision });
          if (expected !== scope()) return;
          if (active?.id === job.id) active = null;
          await refresh();
          say("Preparação cancelada. Nenhuma publicação externa foi afetada.");
        } else {
          const result = await request("/jobs/" + job.id);
          if (expected !== scope()) return;
          say(
            (labels[result.status] || result.status) +
              ". " +
              result.attempts +
              " tentativa(s). " +
              (result.last_error_code ? "Código: " + result.last_error_code + ". " : "") +
              "Mídia não armazenada; nenhum envio. Histórico: " +
              result.events.map((e) => labels[e.status] || e.status).join(" → "),
          );
        }
      });
    });
    byId("contentDraftForm").addEventListener("input", () => {
      byId("preparationReviewed").checked = false;
    });
    for (const section of [idea, panel])
      section.addEventListener("change", (event) => {
        if (event.target.id !== "preparationReviewed") byId("preparationReviewed").checked = false;
      });
    document.addEventListener("socialmei-view-change", () => {
      if (currentView === "Divulgação" && !working) refresh();
      else epoch++;
    });
    document.addEventListener("socialmei-data-change", () => {
      const changed = resetIdentity();
      if (changed && currentView === "Divulgação" && !working) refresh();
    });
    function reviewSummary() {
      const format =
        document.querySelector('[data-content-format][aria-selected="true"]')?.textContent.trim() ||
        "Feed";
      const account =
        byId("preparationAccount").selectedOptions[0]?.textContent ||
        "Selecione uma conta fictícia";
      byId("preparationReviewSummary").textContent =
        "Revisão: " +
        format +
        " · " +
        account +
        " · " +
        (byId("preparationWhen").value || "horário não escolhido") +
        " · " +
        byId("preparationZone").value +
        ". Somente simulação.";
    }
    parent.addEventListener("input", reviewSummary);
    parent.addEventListener("change", reviewSummary);
    parent.addEventListener("click", reviewSummary);
    reviewSummary();
    controls();
  }
  const api = Object.freeze({
    enabled,
    errorMessage,
    captionAlternatives,
    zonedInstant,
    jobs: () => publishedJobs.slice(),
  });
  if (typeof document !== "undefined") init();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  return api;
})();
