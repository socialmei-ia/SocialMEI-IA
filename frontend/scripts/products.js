/* PRODUCTS */
function isCatalogAmount(value) {
  const text = String(value).trim();
  const number = Number(text);
  if (!text || !Number.isFinite(number) || number < 0 || number > 9999999999999.99) return false;
  const match = /^\+?(\d*)(?:\.(\d*))?(?:e([+-]?\d+))?$/i.exec(text);
  if (!match) return false;
  let coefficient = BigInt(match[1] + (match[2] || ""));
  if (coefficient === 0n) return true;
  let scale = (match[2] || "").length - Number(match[3] || 0);
  while (scale > 2 && coefficient % 10n === 0n) {
    coefficient /= 10n;
    scale--;
  }
  return scale <= 2;
}
function updateCatalogMoneyValidity(form) {
  if (document.getElementById("createType")?.value !== "produto") return;
  for (const name of ["preco", "custo"]) {
    const input = form.querySelector(`[name="${name}"]`);
    if (!input) continue;
    const value = name === "custo" && !input.value.trim() ? "0" : input.value;
    input.setCustomValidity(
      isCatalogAmount(value)
        ? ""
        : "Informe um valor de R$ 0,00 a R$ 9.999.999.999.999,99, com até duas casas decimais. O valor não será arredondado.",
    );
  }
}
function toggleProductInventory() {
  const service = $("f_tipo")?.value === "Serviço";
  for (const id of ["f_estoque", "f_minimo"]) {
    const element = $(id);
    if (element) {
      element.closest(".form-group").hidden = service;
      element.disabled = service;
    }
  }
}
