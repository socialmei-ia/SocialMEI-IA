/* REPORTS */
function reportSaleMatchesConversation(sale, conversation) {
  const client = clientContext(conversation).client;
  if (SocialMEISales.remote) {
    return SocialMEIClients.remote && !!client && SocialMEISales.matchesClient(sale, client);
  }
  return normalizedText(sale.cliente) === normalizedText(client?.nome || conversation.nome);
}
function reportTrend(series, label) {
  if (!series.r.some(Boolean) && !series.d.some(Boolean)) {
    return emptyMarkup(
      "Sem movimentações no período",
      "Escolha outro período para consultar os registros.",
    );
  }
  const sales = series.source === "sales";
  const max = Math.max(...series.r, ...series.d, 1);
  const n = series.r.length;
  const w = 680;
  const h = 240;
  const L = 48;
  const R = 18;
  const T = 24;
  const B = 40;
  const step = (w - L - R) / n;
  let svg = `<svg
          class="report-trend"
          viewBox="0 0 ${w} ${h}"
          role="img"
          aria-label="${escapeHtml(label)}"
        >
          <title>${escapeHtml(label)}</title>
          <desc>
            ${series.labels
              .map((l, i) =>
                sales
                  ? `${escapeHtml(l)}: faturamento ${escapeHtml(money(series.r[i]))}.`
                  : `${escapeHtml(l)}: entrou ${escapeHtml(money(series.r[i]))}, saiu ${escapeHtml(money(series.d[i]))}.`,
              )
              .join(" ")}
          </desc>`;
  for (let i = 0; i < 3; i++) {
    const y = T + ((h - T - B) * i) / 2;
    svg += /* HTML */ `<line
            x1="${L}"
            x2="${w - R}"
            y1="${y}"
            y2="${y}"
            stroke="var(--ln)"
          />`;
  }
  series.r.forEach((v, i) => {
    const x = L + step * i + step / 2;
    for (const [value, offset, color, meaning] of sales
      ? [[v, -7, "var(--br)", "Faturamento"]]
      : [
          [v, -15, "var(--br)", "Entrou"],
          [series.d[i], 2, "var(--chart-5)", "Saiu"],
        ]) {
      const height = (value / max) * (h - T - B);
      svg += /* HTML */ `<rect
              x="${x + offset}"
              y="${h - B - height}"
              width="13"
              height="${Math.max(height, value ? 2 : 0)}"
              rx="1"
              fill="${color}"
              ><title>
                ${escapeHtml(series.labels[i])} · ${meaning}: ${escapeHtml(money(value))}
              </title></rect
            >`;
    }
    svg += /* HTML */ `<text
            x="${x}"
            y="${h - 14}"
            text-anchor="middle"
            fill="var(--mt)"
            font-size="14"
            >${escapeHtml(series.labels[i])}</text
          >`;
  });
  return (
    svg +
    "</svg>" +
    /* HTML */ `<details class="chart-data detail-disclosure">
            <summary>Ver os valores do gráfico</summary>
            <div class="table-wrap" tabindex="0" role="region" aria-label="Valores do gráfico">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th class="numeric">${sales ? "Faturamento" : "Entrou"}</th>
                    ${sales ? "" : '<th class="numeric">Saiu</th><th class="numeric">Saldo</th>'}
                  </tr>
                </thead>
                <tbody>
                  ${series.labels
                    .map(
                      (l, i) => /* HTML */ `<tr>
                          <td>${escapeHtml(l)}</td>
                          <td class="numeric">${money(series.r[i])}</td>
                          ${
                            sales
                              ? ""
                              : /* HTML */ `<td class="numeric">${money(series.d[i])}</td>
                                  <td class="numeric">${money(series.r[i] - series.d[i])}</td>`
                          }
                        </tr>`,
                    )
                    .join("")}
                </tbody>
              </table>
            </div>
          </details>`
  );
}
function exportReportCsv() {
  SocialMEIReportUI.exportCurrent();
}
