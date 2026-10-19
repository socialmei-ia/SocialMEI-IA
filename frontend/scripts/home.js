/* HOME */
function updatePrivacyButton() {
  const b = $("privacyBtn");
  if (!b) {
    return;
  }
  b.dataset.hidden = String(areMoneyValuesHidden);
  b.textContent = areMoneyValuesHidden ? "Exibir valores" : "Ocultar valores";
  b.setAttribute("aria-pressed", String(areMoneyValuesHidden));
}
function toggleMoney() {
  areMoneyValuesHidden = !areMoneyValuesHidden;
  socialmeiStorageSet(
    "socialmei-hide-money",
    areMoneyValuesHidden ? "1" : "0",
    "a preferência de privacidade",
  );
  renderCurrentView();
}
function showLoading() {
  loading = true;
  $("kp").innerHTML =
    '<div class="sk" style="height:18px;width:160px"></div><div class="sk" style="height:54px;width:240px;margin:14px 0"></div>';
  $("cw").innerHTML = '<div class="sk" style="height:200px"></div>';
  $("refresh").disabled = true;
  $("refresh").innerHTML = /* HTML */ `<span class="spin">${renderIcon("refresh")}</span>`;
}
function hideLoading() {
  loading = false;
  $("refresh").disabled = false;
  $("refresh").innerHTML = renderIcon("refresh");
  renderAll();
}
function getBusinessHour() {
  return Number(
    new Intl.DateTimeFormat("en-US", {
      timeZone: APP_TIMEZONE,
      hour: "numeric",
      hourCycle: "h23",
    }).format(new Date()),
  );
}
function humanGreeting() {
  const hour = getBusinessHour();
  return sessionData.usuario.primeiro
    ? `${hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite"}, ${sessionData.usuario.primeiro}.`
    : "Olá.";
}
function priorityItems() {
  const overdue = businessViewData().financeiro.filter(
    (entry) => ledgerStatus(entry) === "atrasado",
  );
  const pending = businessViewConversations().filter(
    (conversation) =>
      ["aberto", "andamento"].includes(conversation.status) &&
      [...conversation.mensagens].reverse().find((m) => m.de !== "nota")?.de === "cliente",
  );
  const low = businessViewData().produtos.filter(
    (product) => product.tipo === "Produto" && product.estoque <= product.minimo,
  );
  const due = businessViewData().financeiro.filter(
    (entry) => entry.status !== "pago" && entry.vencimento === todayISO(),
  );
  const items = [];
  if (overdue.length) {
    items.push({
      kind: "overdue",
      tone: "urgent",
      title: `Você tem ${plural(overdue.length, "movimentação atrasada", "movimentações atrasadas")}`,
      desc: "Recebimentos e pagamentos que passaram do vencimento.",
      action: "Regularizar",
    });
  }
  if (pending.length) {
    items.push({
      kind: "reply",
      tone: "",
      title: `${plural(pending.length, "cliente está esperando", "clientes estão esperando")} resposta`,
      desc: "Continue as conversas que ficaram em aberto.",
      action: "Atender",
    });
  }
  if (low.length) {
    items.push({
      kind: "stock",
      tone: "warning",
      title: `${plural(low.length, "produto precisa", "produtos precisam")} de reposição`,
      desc: low.map((p) => p.nome).join(" · "),
      action: "Ver estoque",
    });
  }
  if (due.length) {
    items.push({
      kind: "today",
      tone: "warning",
      title: `${plural(due.length, "compromisso vence", "compromissos vencem")} hoje`,
      desc: "Confira o que precisa receber ou pagar.",
      action: "Conferir",
    });
  }
  return items;
}
