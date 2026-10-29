/* Inbox sources are scoped by the existing account session; never persisted locally. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIEnrichmentStore = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const identityKey = (identity) =>
    identity?.usuario?.id && identity?.negocio?.id
      ? `account:${identity.usuario.id}:workspace:${identity.negocio.id}`
      : null;
  function create({ auth, changed = () => {}, verifiedScope = () => identityKey(auth.current) }) {
    let scope = null,
      epoch = 0,
      rows = [],
      documents = [],
      capability = null,
      status = "idle",
      problem = "",
      busy = false;
    const pending = new Map();
    function bind() {
      const next =
        auth.remote && verifiedScope() === identityKey(auth.current)
          ? identityKey(auth.current)
          : null;
      if (scope !== next) {
        scope = next;
        epoch++;
        rows = [];
        documents = [];
        capability = null;
        pending.clear();
        busy = false;
        status = "idle";
        problem = "";
      }
      return scope;
    }
    function state() {
      bind();
      return clone({
        scope,
        rows,
        documents,
        capability,
        status,
        problem,
        busy,
        canWrite: ["owner", "admin", "member"].includes(auth.current?.papel),
        canManage: ["owner", "admin"].includes(auth.current?.papel),
      });
    }
    function validScope(id) {
      if (!id || id !== bind())
        throw new Error("A sessão mudou. Abra novamente a análise neste negócio.");
    }
    function validOrigin(row) {
      if (row.origin === "instagram" || row.origin === "waha")
        return (
          (row.origin === "instagram"
            ? capability?.instagram_inbox === true &&
              row.channel === "instagram" &&
              /^instagram:[0-9]{1,40}$/.test(row.account_ref) &&
              /^instagram:[0-9]{1,40}$/.test(row.contact_ref)
            : capability?.waha_inbox === true &&
              row.channel === "whatsapp" &&
              /^waha:[0-9]{1,40}@c\.us$/.test(row.account_ref) &&
              /^waha:(?:[0-9]{1,40}@c\.us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)$/.test(
                row.contact_ref,
              )) &&
          Array.isArray(row.messages) &&
          row.messages.every(
            (m) =>
              typeof m.external_message_id === "string" &&
              /^[!-~]{1,1024}$/.test(m.external_message_id) &&
              typeof m.occurred_at === "string" &&
              Number.isFinite(Date.parse(m.occurred_at)),
          )
        );
      return (
        (row.origin === undefined || row.origin === "synthetic") &&
        /^synthetic:[A-Za-z0-9_.:-]{1,100}$/.test(row.account_ref) &&
        /^synthetic:[A-Za-z0-9_.:-]{1,100}$/.test(row.contact_ref)
      );
    }
    function validProviderAnalysis(value) {
      return (
        value == null ||
        (typeof value === "object" &&
          ["positive", "negative", "neutral", "uncertain"].includes(value.sentiment) &&
          ["low", "medium", "high"].includes(value.confidence) &&
          typeof value.explanation === "string" &&
          value.explanation.length <= 500 &&
          value.source === "automation")
      );
    }
    function validateRows(items) {
      if (
        !Array.isArray(items) ||
        items.some(
          (r) =>
            !Number.isSafeInteger(r.id) ||
            r.id < 1 ||
            !["whatsapp", "instagram"].includes(r.channel) ||
            !validOrigin(r) ||
            typeof r.contact_name !== "string" ||
            !Array.isArray(r.messages) ||
            r.messages.some(
              (m) =>
                !Number.isSafeInteger(m.id) ||
                typeof m.text !== "string" ||
                !validProviderAnalysis(m.provider_analysis),
            ),
        )
      )
        throw new Error("A API retornou conversas incompatíveis. Nenhum dado foi importado.");
      return items;
    }
    async function refresh() {
      const id = bind(),
        workspace = auth.current?.negocio.id,
        seq = ++epoch;
      if (!id) {
        status = "unavailable";
        problem =
          "Entre em uma conta conectada para usar a análise isolada. Conversas locais permanecem disponíveis.";
        changed();
        return;
      }
      status = "loading";
      problem = "";
      changed();
      try {
        const cap = await auth.request("/message-enrichment/capabilities");
        validScope(id);
        if (seq !== epoch) return;
        if (
          cap.workspace_id !== workspace ||
          cap.schema_version !== 1 ||
          cap.transport !== "none" ||
          !["disabled", "stub"].includes(cap.mode) ||
          (cap.instagram_inbox !== undefined && typeof cap.instagram_inbox !== "boolean") ||
          (cap.waha_inbox !== undefined && typeof cap.waha_inbox !== "boolean")
        )
          throw new Error("Contrato de análise indisponível.");
        capability = cap;
        if (cap.mode === "disabled" && cap.instagram_inbox !== true && cap.waha_inbox !== true) {
          rows = [];
          documents = [];
          status = "disabled";
          changed();
          return;
        }
        const [conversations, docs] = await Promise.all([
          auth.request("/message-enrichment/conversations"),
          cap.mode === "stub"
            ? auth.request("/message-enrichment/documents")
            : Promise.resolve({ workspace_id: workspace, items: [] }),
        ]);
        validScope(id);
        if (seq !== epoch) return;
        if (conversations.workspace_id !== workspace || docs.workspace_id !== workspace) {
          rows = [];
          documents = [];
          capability = null;
          throw new Error(
            "A identidade da resposta mudou. Entre novamente antes de consultar os dados.",
          );
        }
        const next = validateRows(conversations.items);
        if (!Array.isArray(docs.items)) throw new Error("Contrato de documentos indisponível.");
        rows = clone(next);
        documents = clone(docs.items);
        status = "ready";
      } catch (error) {
        if (id !== bind() || seq !== epoch) return;
        status = "error";
        problem = error.message || "Confira a conexão e tente novamente.";
      }
      changed();
      return status === "ready";
    }
    async function write(key, path, method, input, expectedScope) {
      const id = bind();
      validScope(expectedScope);
      if (busy) throw new Error("Aguarde a operação atual terminar.");
      if (capability?.mode !== "stub" || (status !== "ready" && status !== "error"))
        throw new Error("Carregue a análise antes de alterar os dados.");
      const manage = path.startsWith("/documents");
      if (!(manage ? state().canManage : state().canWrite))
        throw new Error("Sua conta possui acesso somente leitura a esta ação.");
      const fingerprint = JSON.stringify(input);
      let body = input;
      if (method === "POST") {
        const previous = pending.get(key);
        body =
          previous?.fingerprint === fingerprint
            ? previous.body
            : { schema_version: 1, ...input, operation_id: crypto.randomUUID() };
        pending.set(key, { fingerprint, body });
      }
      busy = true;
      problem = "";
      changed();
      try {
        const result = await auth.request("/message-enrichment" + path, method, body);
        validScope(id);
        const refreshed = await refresh();
        if (refreshed) pending.delete(key);
        validScope(id);
        return result;
      } catch (error) {
        if (id === bind()) {
          problem =
            error.status === 409
              ? "Outra sessão alterou estes dados. Seu rascunho foi preservado. Confira a versão salva antes de decidir."
              : "Não foi possível confirmar a operação. Seu texto continua nesta tela. Confira a conexão e tente novamente.";
          changed();
        }
        throw error;
      } finally {
        if (id === bind()) {
          busy = false;
          changed();
        }
      }
    }
    return { state, refresh, write, identityKey };
  }
  return { create, identityKey };
});
