/* FINANCE */
function ledgerStatus(entry) {
  if (entry.status === "pago") {
    return "pago";
  }
  if (entry.vencimento < todayISO() || entry.status === "atrasado") {
    return "atrasado";
  }
  return "aberto";
}
function financeStatusLabel(status, kind) {
  if (status === "pago") {
    if (kind === "receita") return "Recebido";
    if (kind === "despesa") return "Pago";
    return "Regularizado";
  }
  if (status === "atrasado") return "Atrasado";
  if (status === "aberto") return "Em aberto";
  return status;
}
function financeStatusClass(status) {
  return status === "pago" ? "green" : status === "atrasado" ? "red" : "amber";
}
