(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIPriorityScenario = api;
})(globalThis, function () {
  const referenceTime = "2026-10-16T12:00:00Z";
  const msg = (id, text, at, author = "customer") => ({ id, text, at, author });
  const customers = [
    {
      id: "ana",
      name: "Ana Ribeiro",
      interest: "Perfume 212 VIP",
      messages: [
        msg("a1", "Bom dia!", "2026-10-16T11:10:00Z"),
        msg(
          "a2",
          "Quanto custa o 212 VIP? Tem pronta entrega? Consegue entregar hoje?",
          "2026-10-16T11:40:00Z",
        ),
      ],
    },
    {
      id: "bruno",
      name: "Bruno Costa",
      interest: "Troca de tela",
      messages: [
        msg(
          "b1",
          "Pode fazer um orçamento para troca de tela? Preciso hoje.",
          "2026-10-16T11:30:00Z",
        ),
      ],
    },
    {
      id: "camila",
      name: "Camila Santos",
      interest: "Camisas",
      messages: [
        msg("c1", "Olá!", "2026-10-16T10:00:00Z"),
        msg("c2", "Tudo bem?", "2026-10-16T10:01:00Z"),
        msg("c3", "Achei a loja bonita.", "2026-10-16T10:02:00Z"),
        msg("c4", "Obrigada por responder.", "2026-10-16T10:03:00Z"),
        msg("c5", "Quanto custa a camisa?", "2026-10-16T11:50:00Z"),
      ],
    },
    {
      id: "diego",
      name: "Diego Lima",
      interest: "Perfumes · decisão a esclarecer",
      messages: [
        msg(
          "d1",
          "Quero comprar o Malbec, mas não quero comprar agora. Está muito caro.",
          "2026-10-16T11:55:00Z",
        ),
      ],
    },
    {
      id: "fernanda",
      name: "Fernanda Alves",
      interest: "Kit de sabonetes",
      messages: [
        msg("f1", "Quero comprar 2 kits de sabonetes.", "2026-10-16T09:00:00Z"),
        msg("f2", "Não quero comprar mais. Desisti.", "2026-10-16T11:45:00Z"),
      ],
    },
    {
      id: "eduardo",
      name: "Eduardo Souza",
      interest: "Compra relatada como concluída",
      messages: [
        msg("e1", "Quero comprar o perfume.", "2026-10-16T09:00:00Z"),
        msg("e2", "Já comprei. Finalizei a compra, obrigado!", "2026-10-16T11:20:00Z"),
      ],
    },
    {
      id: "gabriela",
      name: "Gabriela Melo",
      interest: "Atendimento de pedido anterior",
      messages: [
        msg("g1", "Quero comprar o perfume.", "2026-10-15T09:00:00Z"),
        msg(
          "g2",
          "Minha entrega não chegou. Preciso de suporte, é urgente.",
          "2026-10-16T11:58:00Z",
        ),
      ],
    },
    {
      id: "helena",
      name: "Helena Rocha",
      interest: "Perfume · retomar contexto",
      messages: [
        msg("h1", "Quero comprar o 212 VIP hoje.", "2026-10-12T10:00:00Z"),
        msg("h2", "Olá!", "2026-10-16T11:59:00Z"),
      ],
    },
  ];
  return { referenceTime, customers };
});
