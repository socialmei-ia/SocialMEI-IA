(function () {
  const scenario = window.SocialMEITapiocaScenario;
  const host = document.getElementById("tour-inbox");
  const node = (tag, text) => {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    return element;
  };
  scenario.customers.forEach((customer, index) => {
    const conversation = node("details");
    conversation.className = "tour-conversation";
    conversation.dataset.customerId = customer.id;
    conversation.open = index === 0;
    const summary = node("summary");
    summary.append(node("strong", customer.name), node("span", customer.interest));
    const timeline = node("div");
    timeline.className = "timeline";
    customer.messages.forEach((message) => {
      const time = node(
        "time",
        new Intl.DateTimeFormat("pt-BR", {
          timeZone: "America/Fortaleza",
          day: "2-digit",
          month: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        }).format(new Date(message.at)) + " · Fortaleza",
      );
      time.dateTime = message.at;
      timeline.append(time, node("blockquote", message.text));
    });
    const link = node("a", "Analisar a mensagem de " + customer.name.split(" ")[0]);
    link.className = "tour-next";
    const url = new URL(window.SocialMEITapiocaLink("opportunities/index.html#intent-form"));
    url.searchParams.set("client", customer.id);
    link.href = url.href;
    // Theme changes update the destination without changing the client's identity.
    new MutationObserver(() => {
      const next = new URL(link.href);
      next.searchParams.set("theme", document.documentElement.dataset.theme);
      link.href = next.href;
    }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    conversation.append(summary, timeline, link);
    host.append(conversation);
  });
})();
