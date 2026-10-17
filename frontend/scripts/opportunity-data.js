(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIOpportunityData = api;
})(globalThis, function () {
  "use strict";
  function demoCustomers(snapshot, conversations) {
    return snapshot
      .filter((original) =>
        conversations.some(
          (current) =>
            current.id === original.id &&
            current.nome === original.nome &&
            current.canal === original.canal &&
            !current.mensagens.some((message) => message.remoteId),
        ),
      )
      .map((conversation) => ({
        id: `demo-${conversation.id}`,
        name: conversation.nome,
        conversationId: conversation.id,
        messages: conversation.mensagens.flatMap((message, index) =>
          message.de === "cliente" && typeof message.texto === "string" && message.texto.trim()
            ? [{ id: `message-${index}`, author: "customer", text: message.texto, at: null }]
            : [],
        ),
      }))
      .filter((customer) => customer.messages.length);
  }
  function read({ enabled, remote, snapshot, conversations }) {
    // The legacy connector groups by name/channel; it cannot identify commercial clients safely.
    if (remote || !enabled) return [];
    return demoCustomers(snapshot, conversations);
  }
  function linkedClient(conversation, clients, remote) {
    if (remote || conversation?.clientId == null) return null;
    return clients.find((client) => client.id === conversation.clientId) || null;
  }
  return Object.freeze({ read, linkedClient });
});
