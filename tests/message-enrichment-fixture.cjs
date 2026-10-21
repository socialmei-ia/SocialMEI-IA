// Browser-only UI fixture; authorization, signatures and persistence are separately tested on PostgreSQL.
module.exports = () => {
  const workspaces = new Map();
  let sequence = 0;
  const dataFor = (id) => {
    if (!workspaces.has(id))
      workspaces.set(id, { conversations: [], documents: [], operations: new Map() });
    return workspaces.get(id);
  };
  const fixture = async (route, identity) => {
    const request = route.request(),
      path = new URL(request.url()).pathname,
      prefix = "/api/v1/message-enrichment";
    if (!path.startsWith(prefix)) return null;
    if (!identity) return route.fulfill({ status: 401, json: { detail: "Sessão ausente" } });
    const data = dataFor(identity.negocio.id),
      relative = path.slice(prefix.length),
      method = request.method();
    if (method !== "GET" && identity.papel === "viewer")
      return route.fulfill({ status: 403, json: { detail: "Somente leitura" } });
    if (relative === "/capabilities")
      return route.fulfill({
        json: {
          schema_version: 1,
          mode: "stub",
          transport: "none",
          workspace_id: identity.negocio.id,
        },
      });
    if (relative === "/conversations")
      return route.fulfill({
        json: { workspace_id: identity.negocio.id, items: data.conversations },
      });
    if (method === "GET" && relative === "/documents")
      return route.fulfill({ json: { workspace_id: identity.negocio.id, items: data.documents } });
    const body = method === "DELETE" ? null : request.postDataJSON();
    const op = body?.operation_id;
    if (op && data.operations.has(op)) return route.fulfill({ json: data.operations.get(op) });
    let result;
    if (relative === "/synthetic-messages") {
      let row = data.conversations.find(
        (r) =>
          r.channel === body.channel &&
          r.account_ref === body.account_ref &&
          r.contact_ref === body.contact_ref,
      );
      if (!row) {
        row = {
          id: ++sequence,
          channel: body.channel,
          account_ref: body.account_ref,
          contact_ref: body.contact_ref,
          contact_name: body.contact_name,
          revision: 1,
          messages: [],
        };
        data.conversations.push(row);
      }
      const message = {
        id: ++sequence,
        external_message_id: body.external_message_id,
        text: body.text,
        occurred_at: "2026-10-20T12:00:00Z",
        revision: 1,
        enrichment: null,
      };
      row.messages.push(message);
      result = { conversation_id: row.id, message_id: message.id, revision: 1, replayed: false };
    } else if (/\/messages\/\d+\/enrich$/.test(relative)) {
      const id = Number(relative.split("/")[2]),
        message = data.conversations.flatMap((c) => c.messages).find((m) => m.id === id);
      if (!message) return route.fulfill({ status: 404, json: { detail: "Não encontrada" } });
      if (message.revision !== body.expected_revision)
        return route.fulfill({ status: 409, json: { detail: "Versão alterada" } });
      result = {
        id: crypto.randomUUID(),
        message_id: id,
        revision: 1,
        status: "pending_review",
        sentiment: "negative",
        confidence: "medium",
        explanation: "A mensagem expressa insatisfação; confira o contexto.",
        suggested_reply: "Sinto pelo ocorrido. Pode explicar o que aconteceu para avaliarmos?",
        citations: data.documents.map((d) => ({ title: d.title, excerpt: d.content })),
        transport: "none",
      };
      message.enrichment = result;
      message.revision++;
    } else if (relative === "/documents" && method === "POST") {
      result = {
        id: ++sequence,
        title: body.title,
        content: body.content,
        revision: 1,
        expires_at: "2026-11-19T12:00:00Z",
      };
      data.documents.push(result);
    } else if (relative.startsWith("/documents/") && method === "DELETE") {
      data.documents = [];
      for (const message of data.conversations.flatMap((c) => c.messages))
        if (message.enrichment)
          Object.assign(message.enrichment, {
            status: "invalidated",
            suggested_reply: "",
            citations: [],
            revision: message.enrichment.revision + 1,
          });
      result = { deleted: true };
    } else if (/\/jobs\/.+\/review$/.test(relative)) {
      result = data.conversations
        .flatMap((c) => c.messages)
        .map((m) => m.enrichment)
        .find((j) => j?.id === relative.split("/")[2]);
      if (!result) return route.fulfill({ status: 404, json: { detail: "Não encontrado" } });
      if (body.expected_revision !== result.revision || result.status !== "pending_review")
        return route.fulfill({ status: 409, json: { detail: "Revisão alterada" } });
      Object.assign(result, {
        revision: result.revision + 1,
        status: body.decision,
        suggested_reply: body.suggested_reply,
      });
    } else return route.fulfill({ status: 404, json: { detail: "Rota inexistente no teste" } });
    if (op) data.operations.set(op, structuredClone(result));
    return route.fulfill({ json: result });
  };
  fixture.dataFor = dataFor;
  return fixture;
};
