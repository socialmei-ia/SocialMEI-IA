/* Public preparation only: no credentials, transport, OAuth or provider calls. */
const SocialMEIIntegrationSetup = (() => {
  "use strict";
  const key = (identity) => (identity ? identity.usuario.id + ":" + identity.negocio.id : null);
  function repository({ identity, request }) {
    let value = null,
      owner = null,
      epoch = 0;
    const snapshot = () => (owner === key(identity()) ? value : null);
    async function perform(method, body) {
      const expected = key(identity()),
        workspace = identity()?.negocio.id,
        seq = ++epoch;
      if (!expected) throw new Error("Entre em uma sessão válida.");
      const result = await request("/integrations/setup", method, body);
      if (seq !== epoch || key(identity()) !== expected)
        throw new Error("A sessão mudou. Atualize antes de continuar.");
      if (result.workspace_id !== workspace) throw new Error("Resposta de outro negócio recusada.");
      value = { ...result, connected: false, transport: "none" };
      owner = expected;
      return value;
    }
    return {
      snapshot,
      reset() {
        epoch++;
        value = null;
        owner = null;
      },
      read: () => perform("GET"),
      async save(input) {
        if (!["owner", "admin"].includes(identity()?.papel))
          throw new Error("Sem permissão para salvar a preparação.");
        if (!snapshot()) throw new Error("Atualize a preparação antes de salvar.");
        const allowed = [
          "username",
          "account_type",
          "meta_app_status",
          "test_participants",
          "reply_mode",
        ];
        if (Object.keys(input).some((k) => !allowed.includes(k)))
          throw new Error("Informe somente dados públicos de preparação.");
        if (input.reply_mode && input.reply_mode !== "review")
          throw new Error("As respostas exigem revisão.");
        const username = String(input.username || "")
          .trim()
          .replace(/^@/, "");
        if (username && !/^[a-zA-Z0-9._]{1,30}$/.test(username))
          throw new Error("Confira o usuário público do Instagram.");
        if (
          !["unknown", "business", "creator"].includes(input.account_type || "unknown") ||
          !["unknown", "exists", "not_created"].includes(input.meta_app_status || "unknown")
        )
          throw new Error("Confira os dados da conta.");
        return perform("PUT", {
          expected_revision: value.revision,
          instagram: {
            username,
            account_type: input.account_type || "unknown",
            meta_app_status: input.meta_app_status || "unknown",
            test_participants: input.test_participants || [],
            reply_mode: "review",
          },
        });
      },
    };
  }
  function init() {
    const host = document.getElementById("integrationSetupPanel");
    if (!host) return;
    const auth = SocialMEIAuth,
      store = repository({
        identity: () => auth.current,
        request: (...args) => auth.request(...args),
      });
    let identity = key(auth.current),
      busy = false,
      loaded = false;
    host.innerHTML = `<h3>Conexões · preparar Instagram</h3><p>Não conectado. Preencha somente informações públicas informadas por você. Esses dados não comprovam acesso à conta; nenhuma senha ou token é solicitado.</p><form id="integrationSetupForm" class="content-preparation-fields"><label>Usuário público do Instagram <input id="integrationUsername" maxlength="30" autocomplete="off" placeholder="@seunegocio"></label><label>Tipo de conta informado <select id="integrationAccountType"><option value="unknown">Ainda não sei</option><option value="business">Comercial</option><option value="creator">Criador</option></select></label><label>Aplicativo Meta informado <select id="integrationMetaStatus"><option value="unknown">Ainda não sei</option><option value="exists">Já existe</option><option value="not_created">Ainda não foi criado</option></select></label><label>Participantes de teste (usuários públicos, um por linha) <textarea id="integrationParticipants" maxlength="2000" rows="3"></textarea></label><p>Respostas sempre passam por revisão. OAuth, recebimento, envio e publicação não estão conectados.</p><button class="management-button" type="submit" id="integrationSetupSave">Salvar preparação no negócio</button></form><button class="management-button" type="button" id="integrationSetupRefresh">Atualizar preparação</button><p id="integrationSetupStatus" role="status" aria-live="polite"></p><ul id="integrationSetupBlockers"></ul><p>WhatsApp: pendente de número e homologação; ativação indisponível. Geração de imagens e legendas via n8n: serviços ainda não confirmados.</p>`;
    const el = (id) => document.getElementById(id),
      say = (t) => (el("integrationSetupStatus").textContent = t);
    function controls() {
      const writable = loaded && ["owner", "admin"].includes(auth.current?.papel);
      host
        .querySelectorAll("input,select,textarea")
        .forEach((n) => (n.disabled = busy || !writable));
      el("integrationSetupSave").disabled = busy || !writable;
      el("integrationSetupRefresh").disabled = busy || !auth.remote || !auth.current;
    }
    function reset() {
      if (identity === key(auth.current)) return false;
      identity = key(auth.current);
      store.reset();
      loaded = false;
      el("integrationSetupForm").reset();
      el("integrationSetupBlockers").replaceChildren();
      say("A sessão mudou. Atualize a preparação do negócio atual.");
      controls();
      return true;
    }
    function render(data) {
      const ig = data.instagram || {};
      el("integrationUsername").value = ig.username || "";
      el("integrationAccountType").value = ig.account_type || "unknown";
      el("integrationMetaStatus").value = ig.meta_app_status || "unknown";
      el("integrationParticipants").value = (ig.test_participants || []).join("\n");
      const list = el("integrationSetupBlockers");
      list.replaceChildren();
      for (const blocker of data.readiness?.blockers || []) {
        const item = document.createElement("li");
        item.textContent = String(blocker);
        list.append(item);
      }
    }
    async function run(save) {
      reset();
      if (busy) return;
      const expected = identity;
      busy = true;
      controls();
      try {
        if (!auth.remote || !auth.current)
          throw new Error("Preparação compartilhada exige uma conta autenticada.");
        const data = save
          ? await store.save({
              username: el("integrationUsername").value,
              account_type: el("integrationAccountType").value,
              meta_app_status: el("integrationMetaStatus").value,
              test_participants: el("integrationParticipants")
                .value.split(/\n/)
                .map((s) => s.trim())
                .filter(Boolean),
              reply_mode: "review",
            })
          : await store.read();
        if (expected !== key(auth.current)) return;
        loaded = true;
        render(data);
        say(
          (save ? "Preparação salva no negócio. " : "Preparação consultada. ") +
            "Não conectado · sem envio ou publicação. Dados informados por você, sem verificação de acesso.",
        );
      } catch (error) {
        if (expected === key(auth.current))
          say(
            SocialMEIContentPreparation.errorMessage(error) +
              " Seus campos foram preservados; nenhuma cópia local foi criada.",
          );
      } finally {
        busy = false;
        reset();
        controls();
      }
    }
    el("integrationSetupForm").addEventListener("submit", (e) => {
      e.preventDefault();
      run(true);
    });
    el("integrationSetupRefresh").addEventListener("click", () => run(false));
    document.addEventListener("socialmei-view-change", () => {
      reset();
      if (
        currentView === "Divulgação" &&
        !loaded &&
        !document.getElementById("contentConnectionsPanel").hidden
      )
        run(false);
    });
    document.addEventListener("socialmei-content-tab-change", (event) => {
      if (event.detail.tab === "connections" && !loaded) run(false);
    });
    document.addEventListener("socialmei-data-change", () => {
      reset();
      controls();
    });
    controls();
  }
  if (typeof document !== "undefined") init();
  const api = { repository };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  return api;
})();
