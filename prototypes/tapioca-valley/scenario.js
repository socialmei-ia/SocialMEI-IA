(function () {
  "use strict";
  const source = window.SocialMEIPriorityScenario;
  const active = new URLSearchParams(location.search).get("tour") === "tapioca-valley";
  window.SocialMEITapiocaScenario = {
    active,
    business: "Perfumaria Aurora · negócio fictício",
    referenceTime: source.referenceTime,
    customers: source.customers.filter((customer) =>
      ["ana", "diego", "gabriela"].includes(customer.id),
    ),
  };
})();
