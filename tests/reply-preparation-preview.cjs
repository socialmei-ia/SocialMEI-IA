const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");

module.exports = async (owner, foreign, origin, headers) => {
  assert.equal(origin, "https://127.0.0.1:8443");
  assert.deepEqual(await (await owner.request.get(origin + "/__preview")).json(), {
    environment: "local-disposable-preview",
    transport: "none",
  });
  const base = origin + "/api/v1/message-enrichment";
  const post = async (url, data) => {
    const response = await owner.request.post(url, { headers, data });
    assert.equal(response.status(), 200, await response.text());
    return response.json();
  };
  const conversations = [];
  for (const channel of ["whatsapp", "instagram"]) {
    const message = {
      schema_version: 1,
      operation_id: randomUUID(),
      channel,
      account_ref: "synthetic:reply-preview",
      contact_ref: "synthetic:same-contact-ref",
      contact_name: "Ana fictícia",
      external_message_id: "same-external-message",
      text: "Preciso de orientação sobre meu pedido.",
      occurred_at: "2026-10-21T10:00:00-03:00",
    };
    const incoming = await post(base + "/synthetic-messages", message);
    conversations.push(incoming.conversation_id);
    const replay = await post(base + "/synthetic-messages", {
      ...message,
      occurred_at: "2026-10-21T13:00:00Z",
    });
    assert.equal(replay.message_id, incoming.message_id);
    assert.equal(replay.replayed, true);
    const previous = await post(base + "/synthetic-messages", {
      ...message,
      operation_id: randomUUID(),
      external_message_id: "earlier-message",
      occurred_at: "2026-10-21T12:00:00Z",
    });
    const job = await post(base + `/messages/${incoming.message_id}/enrich`, {
      schema_version: 1,
      operation_id: randomUUID(),
      expected_revision: 1,
    });
    const draft = "Revisei sua mensagem e vou conferir os detalhes antes de responder.";
    const response = await owner.request.patch(base + `/jobs/${job.id}/review`, {
      headers,
      data: {
        schema_version: 1,
        expected_revision: job.revision,
        decision: channel === "whatsapp" ? "approved" : "rejected",
        suggested_reply: draft,
      },
    });
    assert.equal(response.status(), 200, await response.text());
    const reviewed = await response.json();
    assert.equal(reviewed.suggested_reply, draft);
    assert.equal(reviewed.transport, "none");
    assert.equal(reviewed.status, channel === "whatsapp" ? "approved" : "rejected");
    assert.equal(
      (
        await foreign.request.get(base + `/conversations/${incoming.conversation_id}/enrichments`)
      ).status(),
      404,
    );
    const data = await (await owner.request.get(base + "/conversations")).json();
    const row = data.items.find((item) => item.id === incoming.conversation_id);
    assert.deepEqual(
      row.messages.map((item) => item.id),
      [previous.message_id, incoming.message_id],
    );
    assert.equal(row.messages.at(-1).enrichment.suggested_reply, draft);
  }
  assert.notEqual(conversations[0], conversations[1]);
  assert.deepEqual((await (await foreign.request.get(base + "/conversations")).json()).items, []);
  return {
    channels: ["whatsapp", "instagram"],
    stableIdentity: true,
    canonicalReplay: true,
    sourceTimeOrder: true,
    humanReviewAndDiscard: true,
    crossWorkspaceRead: 404,
    transport: "none",
  };
};
