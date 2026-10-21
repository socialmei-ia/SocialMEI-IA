/* Account settings use an authenticated, revisioned source; legacy local data is retained. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIProfileSync = api.browser(root);
})(typeof globalThis === "object" ? globalThis : this, function () {
  const copy = (value) => JSON.parse(JSON.stringify(value));
  const defaults = () => ({
    theme: "auto",
    notificationsEnabled: true,
    notifications: {
      message: true,
      payment: true,
      pending: true,
      routine: true,
      channel: "app",
      quietFrom: "",
      quietTo: "",
    },
  });
  function create({
    auth,
    local,
    storage,
    normalize,
    changed = () => {},
    applyPreferences = () => {},
  }) {
    let owner = null,
      profile = null,
      preferences = defaults(),
      profileRevision = null,
      preferencesRevision = null,
      profileState = "loading",
      preferencesState = "loading",
      pending = null,
      pendingRevision = null,
      problem = "",
      profileEpoch = 0,
      preferencesEpoch = 0;
    const remote = auth.remote;
    const scope = () => local.scope();
    function bind() {
      const next = scope();
      if (next !== owner) {
        owner = next;
        profile = null;
        preferences = defaults();
        profileRevision = preferencesRevision = pendingRevision = null;
        pending = null;
        problem = "";
        profileState = preferencesState = "loading";
        profileEpoch++;
        preferencesEpoch++;
      }
      return next;
    }
    function state() {
      bind();
      return {
        remote,
        scope: owner,
        profile: copy(profile),
        preferences: copy(preferences),
        profileRevision,
        preferencesRevision,
        profileState,
        preferencesState,
        pending: copy(pending),
        problem,
        canEdit: ["owner", "admin"].includes(auth.current?.papel),
      };
    }
    const legacyKey = (id) => "socialmei-profile-sync-legacy-v1:" + encodeURIComponent(id);
    function captureLegacy() {
      if (!owner) return false;
      try {
        const rawSnapshot = storage.getItem(legacyKey(owner));
        if (rawSnapshot !== null) {
          const snapshot = JSON.parse(rawSnapshot);
          return snapshot?.scope === owner && snapshot.version === 1 && !!snapshot.preferences;
        }
        const raw = JSON.parse(storage.getItem("socialmei-app-data-v2") || "null");
        const theme =
          storage.getItem("socialmei-active-theme") || storage.getItem("socialmei-theme");
        const value = defaults();
        if (["light", "dark", "auto"].includes(theme)) value.theme = theme;
        value.notificationsEnabled = raw?.prefs?.notificacoes !== false;
        const n = raw?.prefs?.notifications || {};
        for (const key of ["message", "payment", "pending", "routine"])
          value.notifications[key] = n[key] !== false;
        if (
          /^([01]\d|2[0-3]):[0-5]\d$/.test(n.quietFrom || "") &&
          /^([01]\d|2[0-3]):[0-5]\d$/.test(n.quietTo || "")
        ) {
          value.notifications.quietFrom = n.quietFrom;
          value.notifications.quietTo = n.quietTo;
        }
        storage.setItem(
          legacyKey(owner),
          JSON.stringify({
            scope: owner,
            version: 1,
            available: !!(
              raw?.prefs?.notifications ||
              typeof raw?.prefs?.notificacoes === "boolean" ||
              theme
            ),
            preferences: value,
          }),
        );
        return true;
      } catch (_) {
        return false;
      }
    }
    function legacyPreferences() {
      bind();
      try {
        const saved = JSON.parse(storage.getItem(legacyKey(owner)) || "null");
        return saved?.scope === owner && saved?.version === 1 && saved.available
          ? copy(saved.preferences)
          : null;
      } catch (_) {
        return null;
      }
    }
    function validate(packet, kind) {
      if (
        packet?.schema_version !== 1 ||
        !Number.isSafeInteger(packet.revision) ||
        packet.revision < 0
      )
        throw Error("A sincronização ainda não está disponível neste servidor.");
      if (kind === "profile") {
        if (
          packet.profile !== null &&
          (!packet.profile?.completed ||
            !packet.profile.businessName ||
            !Array.isArray(packet.profile.offers))
        )
          throw Error("O servidor retornou um perfil incompatível.");
      } else if (
        !packet.preferences ||
        !["light", "dark", "auto"].includes(packet.preferences.theme) ||
        typeof packet.preferences.notificationsEnabled !== "boolean" ||
        !packet.preferences.notifications
      )
        throw Error("O servidor retornou preferências incompatíveis.");
      return packet;
    }
    const path = (kind) => (kind === "profile" ? "/workspace-profile" : "/auth/preferences");
    async function load(kind) {
      const id = bind();
      if (!remote || !id || !auth.current) return false;
      const preserved = captureLegacy();
      if (kind === "preferences" && !preserved) {
        preferencesState = "error";
        problem =
          "O navegador não conseguiu preservar as preferências anteriores. Confira o espaço e a permissão de armazenamento e tente atualizar novamente.";
        changed();
        return false;
      }
      const epoch = kind === "profile" ? ++profileEpoch : ++preferencesEpoch;
      if (kind === "profile") profileState = "loading";
      else preferencesState = "loading";
      changed();
      try {
        const packet = validate(await auth.request(path(kind)), kind);
        if (scope() !== id || epoch !== (kind === "profile" ? profileEpoch : preferencesEpoch))
          return false;
        if (kind === "profile") {
          profile = packet.profile === null ? null : normalize(packet.profile);
          profileRevision = packet.revision;
          profileState = "ready";
        } else {
          preferences = copy(packet.preferences);
          preferencesRevision = packet.revision;
          preferencesState = "ready";
          pending = null;
          pendingRevision = null;
          applyPreferences(copy(preferences));
        }
        problem = "";
        changed();
        return true;
      } catch (error) {
        if (scope() !== id || epoch !== (kind === "profile" ? profileEpoch : preferencesEpoch))
          return false;
        if (kind === "profile") profileState = "error";
        else preferencesState = "error";
        problem =
          error.status === 401
            ? "Sua sessão terminou. Entre novamente; as alterações não foram enviadas."
            : error.message;
        changed();
        return false;
      }
    }
    async function save(kind, value, expectedScope, revision) {
      const id = bind();
      if (!id || expectedScope !== id || !auth.current)
        throw Error("A sessão mudou. Confira a conta antes de salvar.");
      if (kind === "profile" && !["owner", "admin"].includes(auth.current.papel))
        throw Error("Somente o responsável ou administrador pode alterar o perfil do negócio.");
      if (!Number.isSafeInteger(revision))
        throw Error("Carregue os dados salvos antes de enviar alterações.");
      if ((kind === "profile" ? profileState : preferencesState) === "saving")
        throw Error("Aguarde o salvamento em andamento.");
      const epoch = kind === "profile" ? ++profileEpoch : ++preferencesEpoch;
      if (kind === "profile") profileState = "saving";
      else {
        preferencesState = "saving";
        pending = copy(value);
        pendingRevision = revision;
      }
      changed();
      try {
        const packet = validate(
          await auth.request(path(kind), "PATCH", {
            schema_version: 1,
            expected_revision: revision,
            [kind === "profile" ? "profile" : "preferences"]: value,
          }),
          kind,
        );
        if (scope() !== id || epoch !== (kind === "profile" ? profileEpoch : preferencesEpoch))
          throw Error("A sessão mudou. Confira os dados na conta atual.");
        if (kind === "profile") {
          profile = normalize(packet.profile);
          profileRevision = packet.revision;
          profileState = "ready";
        } else {
          preferences = copy(packet.preferences);
          preferencesRevision = packet.revision;
          preferencesState = "ready";
          pending = null;
          pendingRevision = null;
          applyPreferences(copy(preferences));
        }
        problem = "";
        changed();
        return true;
      } catch (error) {
        if (scope() === id && epoch === (kind === "profile" ? profileEpoch : preferencesEpoch)) {
          const next = error.status === 409 ? "conflict" : "error";
          if (kind === "profile") profileState = next;
          else preferencesState = next;
          problem =
            error.status === 409
              ? "Outra sessão alterou estes dados. Suas alterações continuam aqui. Confira a versão salva antes de decidir."
              : error.message;
          changed();
        }
        throw error;
      }
    }
    const repo = {
      scope,
      read() {
        if (!remote) return local.read();
        const s = state();
        return {
          status: s.profile ? "saved" : s.profileState === "ready" ? "empty" : "unavailable",
          profile: s.profile,
          revision: s.profileRevision,
        };
      },
      save(value, expectedScope = scope(), revision = state().profileRevision) {
        if (!remote) return local.save(value, expectedScope);
        return save("profile", normalize(value), expectedScope, revision);
      },
    };
    return {
      remote,
      state,
      repository: () => repo,
      legacyProfile: () => local.read().profile,
      legacyPreferences,
      refresh: (kind) => (kind ? load(kind) : Promise.all([load("profile"), load("preferences")])),
      updatePreferences(patch, expectedRevision, expectedScope = scope()) {
        bind();
        const base = pending || preferences;
        const value = {
          ...copy(base),
          ...patch,
          notifications: { ...base.notifications, ...patch.notifications },
        };
        return save(
          "preferences",
          value,
          expectedScope,
          expectedRevision ?? pendingRevision ?? preferencesRevision,
        );
      },
      retryPreferences() {
        bind();
        if (!pending) return false;
        return save("preferences", copy(pending), scope(), pendingRevision);
      },
    };
  }
  function browser(root) {
    const model = root.SocialMEIBusinessProfile;
    const local = model.browserRepository();
    let service;
    const refreshUI = () => {
      if (document.readyState === "loading") return;
      service.decorate();
      document.dispatchEvent(new CustomEvent("socialmei-business-profile-change"));
    };
    service = create({
      auth: root.SocialMEIAuth,
      local,
      storage: localStorage,
      normalize: model.normalize,
      changed: refreshUI,
      applyPreferences(value) {
        appData.prefs.notificacoes = value.notificationsEnabled;
        appData.prefs.notifications = copy(value.notifications);
        if (!root.SocialMEIThemes.active.startsWith("custom-"))
          root.SocialMEIThemes.select(value.theme, { persist: false });
        updateThemeButton();
      },
    });
    const original = model.browserRepository;
    model.browserRepository = () => (service.remote ? service.repository() : original());
    const statusText = () => {
      const s = service.state();
      if (s.profileState === "saving" || s.preferencesState === "saving")
        return "Salvando na conta…";
      if ([s.profileState, s.preferencesState].includes("conflict")) return s.problem;
      if ([s.profileState, s.preferencesState].includes("error"))
        return (
          "Não foi possível sincronizar. " +
          s.problem +
          " Os dados locais anteriores foram preservados."
        );
      if ([s.profileState, s.preferencesState].includes("loading"))
        return "Carregando perfil e preferências da conta…";
      return "Perfil compartilhado com o negócio; tema e avisos separados por usuário e negócio. Disponíveis em outros dispositivos após recarregar.";
    };
    service.statusText = statusText;
    service.decorate = () => {
      if (!service.remote) return;
      const host = document.getElementById("settingsPanel");
      if (!host || currentView !== "Configurações") return;
      let panel = document.getElementById("profileSyncPanel");
      if (!panel) {
        panel = document.createElement("section");
        panel.id = "profileSyncPanel";
        panel.className = "management-card profile-sync-panel";
        host.prepend(panel);
      }
      const s = service.state();
      // Do not replace focused controls or an expanded import review during status updates.
      let status = panel.querySelector('[role="status"]');
      if (!status) {
        panel.innerHTML =
          '<p role="status" aria-live="polite" data-profile-sync-status></p><div class="management-inline-actions"><button type="button" class="management-button" data-sync-refresh>Atualizar dados salvos</button><button type="button" class="management-button" data-sync-retry hidden>Tentar salvar preferências</button><button type="button" class="management-button" data-sync-use-preferences hidden>Carregar preferências salvas e descartar alterações</button></div><details class="context-help" data-sync-import-review hidden><summary>Revisar preferências antigas deste navegador</summary><p data-sync-import-summary></p><button type="button" class="management-button" data-sync-import-preferences>Importar preferências revisadas</button><button type="button" class="management-button" data-sync-import-cancel>Cancelar</button></details><p class="management-note">Temas personalizados, rascunhos, canais e arquivos continuam locais. A sincronização de preferências não ativa notificações externas.</p>';
        status = panel.querySelector('[role="status"]');
      }
      status.id = "profileSyncStatus";
      status.textContent =
        statusText() +
        (s.canEdit
          ? ""
          : " Você pode consultar o perfil; somente responsáveis e administradores podem alterá-lo. Suas preferências pessoais continuam editáveis.");
      panel.querySelector("[data-sync-retry]").hidden =
        !s.pending || s.preferencesState === "conflict";
      panel.querySelector("[data-sync-use-preferences]").hidden = s.preferencesState !== "conflict";
      const legacy = service.legacyPreferences();
      panel.querySelector("[data-sync-import-review]").hidden =
        !legacy || s.preferencesRevision === null;
      if (legacy)
        panel.querySelector("[data-sync-import-summary]").textContent =
          `Tema: ${legacy.theme === "auto" ? "automático" : legacy.theme === "dark" ? "escuro" : "claro"}. Avisos ${legacy.notificationsEnabled ? "ligados" : "desligados"}. Horário silencioso: ${legacy.notifications.quietFrom || "não definido"}${legacy.notifications.quietTo ? " a " + legacy.notifications.quietTo : ""}. Importar substitui suas preferências salvas, após esta confirmação. A cópia antiga será mantida.`;
      const editing = host.querySelector("[data-business-profile-edit]");
      if (editing) {
        editing.disabled = !s.canEdit || s.profileRevision === null;
        editing.setAttribute("aria-describedby", "profileSyncStatus");
      }
      const importProfile = host.querySelector("[data-sync-import-profile]");
      if (importProfile) importProfile.disabled = !s.canEdit || s.profileRevision === null;
    };
    document.addEventListener("click", async (event) => {
      const control = event.target.closest(
        "[data-sync-refresh],[data-sync-retry],[data-sync-use-preferences],[data-sync-import-preferences],[data-sync-import-cancel]",
      );
      if (!control || !service.remote) return;
      control.disabled = true;
      try {
        if (control.hasAttribute("data-sync-refresh")) await service.refresh("profile");
        else if (control.hasAttribute("data-sync-retry")) await service.retryPreferences();
        else if (control.hasAttribute("data-sync-use-preferences"))
          await service.refresh("preferences");
        else if (control.hasAttribute("data-sync-import-cancel"))
          control.closest("details").open = false;
        else {
          await service.updatePreferences(service.legacyPreferences());
          control.closest("details").open = false;
        }
        if (
          control.hasAttribute("data-sync-refresh") &&
          service.state().preferencesState !== "conflict" &&
          !service.state().pending
        )
          await service.refresh("preferences");
        if (
          currentView === "Configurações" &&
          (selectedSettingsTab === "perfil" || control.hasAttribute("data-sync-use-preferences"))
        )
          renderSettings();
      } catch (error) {
        toast("Preferências não salvas", service.state().problem || error.message);
      } finally {
        control.disabled = false;
        service.decorate();
      }
    });
    service.ready = service.remote
      ? new Promise((resolve) =>
          document.addEventListener(
            "DOMContentLoaded",
            async () => {
              await root.SocialMEIAuth.ready;
              if (root.SocialMEIAuth.current) await service.refresh();
              resolve();
            },
            { once: true },
          ),
        )
      : Promise.resolve();
    return service;
  }
  return { create, defaults, browser };
});
