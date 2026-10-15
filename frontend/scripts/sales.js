/* SALES */
function saleStatusClass(status) {
  return (
    {
      Pago: "green",
      Cancelado: "red",
      Pendente: "amber",
      Rascunho: "draft",
    }[status] || "draft"
  );
}
function updateSaleReview() {
  const sale = $("createType").value === "venda";
  $("saleReview").hidden = !sale;
  $("createSubmit").textContent = sale
    ? "Registrar venda"
    : {
        cliente: "Salvar cliente",
        produto: "Salvar item",
        receita: "Salvar entrada",
        despesa: "Salvar saída",
      }[$("createType").value] || "Salvar";
  if (!sale) {
    return;
  }
  const quantity = Number($("f_quantidade")?.value) || 0;
  const price = Number($("f_preco")?.value) || 0;
  const discount = Number($("f_desconto")?.value) || 0;
  const total = Math.max(0, quantity * price - discount);
  $("saleReview").innerHTML = /* HTML */ `<span>Confira antes de registrar</span
          ><b>${formatCurrency(total)}</b>
          <p>
            ${quantity} ×
            ${formatCurrency(price)}${discount ? " · desconto " + formatCurrency(discount) : ""}
          </p>
          <p class="table-help">
            A venda será registrada como pendente. Quando receber, marque como paga nos detalhes da
            venda.
          </p>`;
  if ($("f_desconto")) {
    $("f_desconto").setCustomValidity(
      discount > quantity * price ? "O desconto não pode ser maior que o valor da venda." : "",
    );
  }
  if (SocialMEISales.remote) {
    $("saleReview").querySelector(".table-help").textContent =
      "Registrar a venda baixa o estoque na mesma operação. Marcar como paga não cria um lançamento financeiro.";
  }
}
