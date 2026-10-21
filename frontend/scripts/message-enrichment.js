/* Native Inbox lab. No connector, automatic ingestion, message sending or browser persistence. */
(() => {
  const byId = (id) => document.getElementById(id);
  let updating = false;
  let service,
    scope,
    selectedMessage = new Map(),
    drafts = new Map(),
    formOperation = null;
  function installRows(state) {
    const old = new Map(
      sessionData.conversas.filter((c) => c._enrichmentSynthetic).map((c) => [c._enrichmentId, c]),
    );
    sessionData.conversas = sessionData.conversas.filter((c) => !c._enrichmentSynthetic);
    if (scope !== state.scope) {
      scope = state.scope;
      drafts.clear();
      selectedMessage.clear();
      formOperation = null;
      byId("enrichmentSyntheticForm")?.reset();
      byId("enrichmentDocumentForm")?.reset();
    }
    for (const row of state.rows) {
      const previous = old.get(row.id);
      sessionData.conversas.push({
        id: -row.id,
        _enrichmentSynthetic: true,
        _enrichmentId: row.id,
        _enrichmentScope: state.scope,
        _enrichmentKey: [state.scope, row.channel, row.account_ref, row.contact_ref].join(":"),
        nome: row.contact_name,
        iniciais: initialsFromName(row.contact_name),
        canal: row.channel,
        status: "aberto",
        telefone: "—",
        usuario: "Contato fictício",
        naoLidas: previous?.naoLidas || 0,
        atualizado: "Teste isolado",
        mensagens: row.messages.map((m) => ({
          de: "cliente",
          texto: m.text,
          data: remoteDate(m.occurred_at),
          hora: remoteHour(m.occurred_at),
          remoteId: `synthetic:${state.scope}:${m.id}`,
        })),
      });
    }
    if (currentView === "Caixa Unificada") {
      renderConversationList();
      if (getConversation()?._enrichmentSynthetic) renderThread({ preserveScroll: true });
      else if (activeConversationId < 0 && !getConversation()) {
        enterInboxListMode();
        renderThread();
        for (const id of ["threadName", "threadMeta", "threadAvatar"]) byId(id).replaceChildren();
      }
    }
  }
  function update() {
    if (!service || updating) return;
    updating = true;
    try {
      const state = service.state();
      for (const row of state.rows)
        for (const message of row.messages)
          if (["expired", "invalidated"].includes(message.enrichment?.status))
            drafts.delete(state.scope + ":" + message.enrichment.id);
      const status = byId("enrichmentLabStatus");
      status.textContent =
        (SocialMEIDemoData.enabled()
          ? "Desative os dados de teste gerais para usar o laboratório autenticado. Suas conversas e preferências locais serão preservadas."
          : "") ||
        state.problem ||
        {
          idle: "Abra o laboratório para consultar o modo disponível nesta conta.",
          loading: "Consultando dados deste negócio…",
          disabled: "Análise desativada neste ambiente. Nenhum canal ou workflow foi conectado.",
          unavailable: "Entre em uma conta conectada para usar o laboratório.",
          ready:
            "Demonstração autenticada · mensagens e documentos fictícios. Processamento heurístico local no servidor; sem envio externo.",
        }[state.status] ||
        "Análise indisponível.";
      byId("enrichmentLabForms").hidden = !state.capability || state.capability.mode !== "stub";
      for (const el of document.querySelectorAll(
        "#enrichmentLabForms input, #enrichmentLabForms select, #enrichmentLabForms textarea, #enrichmentLabForms button",
      ))
        el.disabled = state.busy || !state.canWrite || SocialMEIDemoData.enabled();
      for (const el of document.querySelectorAll(
        "#enrichmentDocumentForm input, #enrichmentDocumentForm textarea, #enrichmentDocumentForm button",
      ))
        el.disabled = state.busy || !state.canManage || SocialMEIDemoData.enabled();
      byId("enrichmentRefresh").disabled = state.busy || state.status === "loading";
      const list = byId("enrichmentDocumentList");
      list.replaceChildren();
      for (const doc of state.documents) {
        const line = document.createElement("li"),
          label = document.createElement("span"),
          button = document.createElement("button");
        label.textContent =
          doc.title + " · válido até " + new Date(doc.expires_at).toLocaleDateString("pt-BR");
        button.type = "button";
        button.className = "management-button";
        button.textContent = "Remover";
        button.setAttribute("aria-label", `Remover documento ${doc.title}`);
        button.disabled = !state.canManage || state.busy || SocialMEIDemoData.enabled();
        button.addEventListener("click", () =>
          action(() =>
            service.write(
              "delete:" + doc.id,
              `/documents/${encodeURIComponent(doc.id)}?expected_revision=${doc.revision}`,
              "DELETE",
              undefined,
              state.scope,
            ),
          ),
        );
        line.append(label, button);
        list.append(line);
      }
      installRows(state);
    } finally {
      updating = false;
    }
  }
  async function action(fn) {
    if (SocialMEIDemoData.enabled()) return;
    const focus = document.activeElement?.id;
    const selected = activeConversationId;
    try {
      return await fn();
    } catch (_) {
      byId("enrichmentLabStatus").textContent =
        service.state().problem || "Não foi possível concluir. Seu rascunho foi preservado.";
    } finally {
      if (
        focus &&
        selected === activeConversationId &&
        currentView === "Caixa Unificada" &&
        document.activeElement === document.body
      )
        byId(focus)?.focus({ preventScroll: true });
    }
  }
  function initialize() {
    service = SocialMEIEnrichmentStore.create({
      auth: SocialMEIAuth,
      changed: update,
      verifiedScope: () => SocialMEIBusinessProfile.browserRepository().scope(),
    });
    const lab = byId("enrichmentLab");
    lab.addEventListener("toggle", () => {
      if (lab.open && service.state().status === "idle") service.refresh();
    });
    byId("enrichmentRefresh").addEventListener("click", () => service.refresh());
    byId("enrichmentSyntheticForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget,
        snapshot = new FormData(form),
        state = service.state();
      const input = {
        channel: snapshot.get("channel"),
        account_ref: snapshot.get("account"),
        contact_ref: snapshot.get("contact"),
        contact_name: snapshot.get("name").trim(),
        text: snapshot.get("text").trim(),
      };
      const fingerprint = JSON.stringify(input);
      if (formOperation?.fingerprint !== fingerprint)
        formOperation = { fingerprint, id: "synthetic:" + crypto.randomUUID() };
      input.external_message_id = formOperation.id;
      const result = await action(() =>
        service.write("message", "/synthetic-messages", "POST", input, state.scope),
      );
      if (result && service.state().status === "ready" && state.scope === service.state().scope) {
        formOperation = null;
        byId("enrichmentText").value = "";
        byId("enrichmentLab").open = false;
        await selectConversation(-result.conversation_id);
      }
    });
    byId("enrichmentDocumentForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget),
        state = service.state();
      const result = await action(() =>
        service.write(
          "document",
          "/documents",
          "POST",
          {
            title: data.get("title").trim(),
            mime_type: "text/plain",
            content: data.get("content").trim(),
          },
          state.scope,
        ),
      );
      if (result && service.state().status === "ready" && state.scope === service.state().scope)
        event.target.reset();
    });
    window.addEventListener("storage", (event) => {
      if (event.key === "socialmei-auth-browser-scope" || event.key === null) update();
    });
    document.addEventListener("socialmei-demo-change", () => {
      if (lab.open) update();
    });
    window.SocialMEIMessageEnrichment = {
      render,
      state: () => service.state(),
      refresh: () => service.refresh(),
    };
    update();
  }
  function render(conversation) {
    byId("enrichmentReview")?.remove();
    if (!conversation?._enrichmentSynthetic || !service) return;
    const state = service.state(),
      row = state.rows.find((r) => r.id === conversation._enrichmentId);
    if (!row || state.scope !== conversation._enrichmentScope) return;
    const selected =
      row.messages.find((m) => m.id === selectedMessage.get(row.id)) || row.messages.at(-1);
    if (!selected) return;
    const section = document.createElement("section");
    section.id = "enrichmentReview";
    section.className = "enrichment-review";
    section.setAttribute("aria-label", "Análise e revisão da mensagem fictícia");
    const title = document.createElement("h3");
    title.textContent = "Sugestão da IA — não enviada";
    const note = document.createElement("p");
    note.className = "management-note";
    note.textContent =
      "Teste isolado · a classificação é heurística e pode errar. Revise o contexto; nenhuma aprovação envia uma mensagem.";
    const label = document.createElement("label");
    label.textContent = "Mensagem a analisar";
    const select = document.createElement("select");
    select.id = "enrichmentMessageSelect";
    for (const message of row.messages) {
      const option = document.createElement("option");
      option.value = String(message.id);
      option.textContent = message.text.slice(0, 90);
      option.selected = message.id === selected.id;
      select.append(option);
    }
    select.addEventListener("change", () => {
      selectedMessage.set(row.id, Number(select.value));
      render(conversation);
    });
    label.append(select);
    const analyze = document.createElement("button");
    analyze.type = "button";
    analyze.id = "enrichmentAnalyze";
    analyze.className = "management-button";
    analyze.textContent = "Analisar mensagem fictícia";
    analyze.disabled = state.busy || !state.canWrite || SocialMEIDemoData.enabled();
    analyze.addEventListener("click", () =>
      action(() =>
        service.write(
          "enrich:" + selected.id,
          `/messages/${selected.id}/enrich`,
          "POST",
          { expected_revision: selected.revision },
          state.scope,
        ),
      ),
    );
    section.append(title, note, label, analyze);
    if (state.problem) {
      const warning = document.createElement("p");
      warning.setAttribute("role", "status");
      warning.textContent = state.problem;
      section.append(warning);
    }
    const result = selected.enrichment;
    if (result) {
      const info = document.createElement("p");
      info.id = "enrichmentExplanation";
      const sentiments = {
          positive: "Positivo",
          negative: "Negativo",
          neutral: "Neutro",
          uncertain: "Indefinido",
        },
        confidences = { low: "baixa", medium: "moderada", high: "alta" };
      info.textContent = `${sentiments[result.sentiment] || "Indefinido"} · confiança heurística ${confidences[result.confidence] || "não informada"}. ${result.explanation || "Confira as evidências na conversa."}`;
      const resultState = document.createElement("p");
      resultState.setAttribute("role", "status");
      resultState.textContent =
        {
          pending_review: "Aguardando revisão humana",
          approved: "Rascunho aprovado — não enviado",
          rejected: "Sugestão descartada — não enviada",
          expired: "Sugestão expirada — analise novamente",
          invalidated: "Fonte removida — analise novamente",
          superseded: "Análise substituída — consulte o resultado mais recente",
        }[result.status] || "Resultado em processamento";
      section.append(info, resultState);
      const citations = document.createElement("ul");
      for (const citation of result.citations || []) {
        const li = document.createElement("li");
        li.textContent =
          typeof citation === "string"
            ? citation
            : `${citation.title || "Documento deste negócio"}${citation.excerpt ? ": " + citation.excerpt : ""}`;
        citations.append(li);
      }
      if (citations.childNodes.length) section.append(citations);
      const key = state.scope + ":" + result.id;
      let draft = drafts.get(key);
      if (!draft) {
        draft = { text: result.suggested_reply || "", revision: result.revision };
        drafts.set(key, draft);
      }
      const draftLabel = document.createElement("label");
      draftLabel.textContent = "Rascunho revisável";
      const textarea = document.createElement("textarea");
      textarea.id = "enrichmentReply";
      textarea.rows = 4;
      textarea.maxLength = 4000;
      textarea.value = draft.text;
      textarea.disabled = state.busy || ["expired", "invalidated"].includes(result.status);
      textarea.readOnly =
        !state.canWrite || SocialMEIDemoData.enabled() || result.status !== "pending_review";
      textarea.addEventListener("input", () => {
        draft.text = textarea.value;
      });
      draftLabel.append(textarea);
      section.append(draftLabel);
      if (draft.revision !== result.revision) {
        const conflict = document.createElement("p");
        conflict.textContent =
          "A revisão mudou em outra sessão. Seu rascunho continua aqui; carregue a versão salva antes de revisar novamente.";
        section.append(conflict);
      }
      const controls = document.createElement("div");
      controls.className = "management-inline-actions";
      for (const [decision, text] of [
        ["approved", "Salvar revisão do rascunho"],
        ["rejected", "Descartar sugestão"],
      ]) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "management-button";
        button.textContent = text;
        button.dataset.enrichmentDecision = decision;
        button.id = "enrichment-" + decision;
        button.disabled =
          state.busy ||
          !state.canWrite ||
          SocialMEIDemoData.enabled() ||
          result.status !== "pending_review" ||
          draft.revision !== result.revision;
        button.addEventListener("click", async () => {
          const saved = await action(() =>
            service.write(
              "review:" + result.id,
              `/jobs/${encodeURIComponent(result.id)}/review`,
              "PATCH",
              {
                schema_version: 1,
                expected_revision: draft.revision,
                decision,
                suggested_reply: draft.text,
              },
              state.scope,
            ),
          );
          if (
            saved &&
            service.state().status === "ready" &&
            state.scope === service.state().scope
          ) {
            drafts.delete(key);
            render(conversation);
          }
        });
        controls.append(button);
      }
      const load = document.createElement("button");
      load.type = "button";
      load.className = "management-button";
      load.textContent = "Carregar revisão salva e descartar meu rascunho";
      load.disabled = state.busy;
      load.addEventListener("click", async () => {
        const refreshed = await service.refresh();
        if (refreshed && state.scope === service.state().scope) {
          drafts.delete(key);
          render(getConversation());
        }
      });
      controls.append(load);
      section.append(controls);
    } else {
      const empty = document.createElement("p");
      empty.textContent =
        "Esta mensagem ainda não foi analisada. Nenhuma mensagem real foi recebida ou enviada.";
      section.append(empty);
    }
    byId("messages").append(section);
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  else initialize();
})();
