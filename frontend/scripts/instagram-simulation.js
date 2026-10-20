/* Instagram simulation uses only authenticated same-origin API; never uploads media. */
const SocialMEIInstagramSimulation = (() => {
  "use strict";
  const enabled = (config) => config?.mode === "simulation";
  function payloadOf(snapshot, accountId, idempotencyKey, scheduledFor = null) {
    if (!snapshot?.media || !["feed", "story", "reel"].includes(snapshot.format))
      throw new Error("Selecione uma mídia válida no editor antes de simular.");
    return {
      account_id: accountId,
      idempotency_key: idempotencyKey,
      format: snapshot.format,
      caption: snapshot.caption,
      media: [snapshot.media],
      scheduled_for: scheduledFor,
    };
  }
  function init() {
    const byId = (id) => document.getElementById(id);
    const panel = byId("instagramSimulationPanel");
    if (!panel || !enabled(SOCIALMEI_CONFIG.instagramSimulation) || !SocialMEIAuth.remote)
      return;
    panel.hidden = false;
    const account = byId("instagramSimulationAccount"),
      name = byId("instagramSimulationName"),
      create = byId("instagramSimulationCreate"),
      schedule = byId("instagramSimulationSchedule"),
      submit = byId("instagramSimulationSubmit"),
      status = byId("instagramSimulationStatus"),
      history = byId("instagramSimulationHistory");
    let accounts = [],
      intent = null,
      working = false,
      version = 0;
    const message = (text) => {
      status.textContent = text;
    };
    const request = (path, method = "GET", data) =>
      SocialMEIAuth.request("/instagram/simulation" + path, method, data);
    function renderAccounts() {
      account.replaceChildren();
      for (const item of accounts) {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = item.label + " · fictícia";
        account.append(option);
      }
      submit.disabled = working || !accounts.length;
      create.disabled = working || !["owner", "admin"].includes(SocialMEIAuth.current?.papel);
    }
    function showHistory(items) {
      history.replaceChildren();
      for (const item of items) {
        const p = document.createElement("p");
        p.textContent =
          item.format.toUpperCase() +
          " · SIMULADO · " +
          new Date(item.created_at).toLocaleString("pt-BR") +
          (item.scheduled_for
            ? " · horário escolhido: " + new Date(item.scheduled_for).toLocaleString("pt-BR")
            : "");
        history.append(p);
      }
    }
    async function load() {
      const seq = ++version;
      await SocialMEIAuth.ready;
      if (!SocialMEIAuth.current) {
        message("Entre em uma conta real do SocialMEI para acessar o teste isolado.");
        return;
      }
      try {
        const [a, p] = await Promise.all([request("/accounts"), request("/publications")]);
        if (seq !== version || !SocialMEIAuth.current) return;
        accounts = a.items;
        renderAccounts();
        showHistory(p.items);
        message("Simulação habilitada. Nenhum dado é transmitido ao Instagram.");
      } catch (error) {
        if (seq !== version) return;
        accounts = [];
        renderAccounts();
        message(error.message);
      }
    }
    create.addEventListener("click", async () => {
      if (working || !name.value.trim()) return message("Informe um nome fictício.");
      working = true;
      renderAccounts();
      try {
        const added = await request("/accounts", "POST", { label: name.value.trim() });
        await load();
        account.value = added.id;
        name.value = "";
        message("Conta fictícia criada. Nenhuma conta Instagram foi conectada.");
      } catch (error) {
        message(error.message);
      } finally {
        working = false;
        renderAccounts();
      }
    });
    submit.addEventListener("click", async () => {
      if (working || !accounts.some((item) => item.id === account.value)) return;
      const snapshot = SocialMEIContentStudio.simulationSnapshot();
      if (!snapshot || !snapshot.scope.startsWith("account:"))
        return message("Entre na conta correta e selecione novamente uma mídia no editor.");
      let when = null;
      if (schedule.value) {
        const date = new Date(schedule.value);
        if (!Number.isFinite(date.getTime())) return message("Confira o horário.");
        when = date.toISOString();
      }
      const fingerprint = JSON.stringify([snapshot, account.value, when]);
      if (!intent || intent.fingerprint !== fingerprint)
        intent = { fingerprint, key: crypto.randomUUID() };
      let body;
      try {
        body = payloadOf(snapshot, account.value, intent.key, when);
      } catch (error) {
        return message(error.message);
      }
      working = true;
      renderAccounts();
      try {
        const result = await request("/publications", "POST", body);
        if (SocialMEIBusinessProfile.browserRepository().scope() !== snapshot.scope)
          return message("A sessão mudou. Confira as simulações na conta atual.");
        message(
          "Simulação " +
            result.id +
            " registrada. Nenhum arquivo foi enviado e nada foi publicado.",
        );
        const items = await request("/publications");
        showHistory(items.items);
      } catch (error) {
        message(error.message + " Se houver dúvida, repetir usa a mesma chave.");
      } finally {
        working = false;
        renderAccounts();
      }
    });
    document.addEventListener("socialmei-view-change", () => {
      if (currentView === "Divulgação") load();
      else version++;
    });
    document.addEventListener("socialmei-data-change", () => {
      intent = null;
      version++;
      if (currentView === "Divulgação") load();
    });
    load();
  }
  if (typeof document !== "undefined") init();
  const api = Object.freeze({ enabled, payloadOf });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  return api;
})();
