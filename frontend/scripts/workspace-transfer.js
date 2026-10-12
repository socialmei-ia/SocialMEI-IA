/* Transferência protegida, sem upload para serviços externos. */
(() => {
  const el = (id) => document.getElementById(id);
  let packet = null,
    preview = null,
    receipt = null,
    busy = false,
    base = "";
  function show(message) {
    el("status").textContent = message;
  }
  function controls() {
    el("packetFile").disabled = busy;
    el("previewButton").disabled = busy || !packet || !base;
    el("confirmButton").disabled =
      busy || !preview || !el("acknowledge").checked || preview.ja_transferido;
  }
  try {
    const config = SOCIALMEI_CONFIG.clientes;
    const url = new URL(config.apiBaseUrl, location.href);
    if (
      config.mode !== "remote" ||
      config.workspaceKey !== "team" ||
      url.origin !== location.origin ||
      url.pathname.replace(/\/$/, "") !== "/api/v1" ||
      url.search ||
      url.hash ||
      url.username ||
      url.password
    )
      throw new Error("Abra esta página no site protegido da equipe.");
    base = url.href.replace(/\/$/, "");
    for (const name of ["produtos", "vendas", "financeiro"]) {
      const other = SOCIALMEI_CONFIG[name];
      if (
        other?.mode !== "remote" ||
        other.workspaceKey !== "team" ||
        new URL(other.apiBaseUrl, location.href).href.replace(/\/$/, "") !== base
      )
        throw new Error("Confira os quatro módulos na mesma API da equipe antes de transferir.");
    }
  } catch (error) {
    base = "";
    show(error.message);
  }
  async function request(path, data) {
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(base + path, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(data),
        cache: "no-store",
        signal: controller.signal,
      });
      const body = await response.json().catch(() => null);
      if (!response.ok)
        throw new Error(
          typeof body?.detail === "string"
            ? body.detail
            : `O servidor recusou a operação (HTTP ${response.status}). Confira o arquivo e faça uma nova prévia.`,
        );
      if (!body) throw new Error("Resposta inválida do servidor.");
      return body;
    } finally {
      clearTimeout(timer);
    }
  }
  async function run(action) {
    if (busy || !base) return;
    busy = true;
    controls();
    try {
      await action();
    } catch (error) {
      preview = null;
      el("preview").hidden = true;
      el("acknowledge").checked = false;
      show(
        error.name === "AbortError"
          ? "A resposta demorou. Preserve o arquivo e faça outra prévia: o servidor recupera o resultado sem duplicar."
          : error.message + " Preserve o mesmo arquivo para conferir ou recuperar a operação.",
      );
    } finally {
      busy = false;
      controls();
    }
  }
  el("packetFile").addEventListener("change", async () => {
    packet = null;
    preview = null;
    receipt = null;
    el("preview").hidden = true;
    el("receiptButton").hidden = true;
    el("acknowledge").checked = false;
    controls();
    const file = el("packetFile").files[0];
    if (!file) return;
    if (file.size > 2_000_000) {
      show("Arquivo excede 2 MB.");
      return;
    }
    try {
      const value = JSON.parse(await file.text());
      if (
        value.formato !== "socialmei-workspace-transfer" ||
        value.versao_formato !== 1 ||
        value.workspace_origem !== "development" ||
        !["clientes", "produtos", "vendas", "financeiro"].every((name) =>
          Array.isArray(value[name]),
        )
      )
        throw new Error(
          "Use o arquivo criado pelo comando data:export, não o backup do navegador.",
        );
      packet = value;
      el("fileInfo").textContent =
        `Fonte: development · origem ${value.origem} · exportação ${value.exportado_em}`;
      show("Arquivo lido no seu navegador. Confira a prévia para consultar o destino.");
    } catch (error) {
      show(error.message);
    }
    controls();
  });
  el("previewButton").addEventListener("click", () =>
    run(async () => {
      show("Conferindo a prévia…");
      preview = await request("/transferencias/preview", packet);
      if (
        preview.workspace_destino !== "team" ||
        preview.origem !== packet.origem ||
        !/^[a-f0-9]{64}$/.test(preview.preview_token)
      )
        throw new Error("Destino ou resposta da prévia inválido.");
      el("destination").textContent =
        `Destino: ${location.origin} · workspace team. Nomes iguais não são mesclados automaticamente.`;
      el("counts").replaceChildren();
      for (const [name, label] of [
        ["clientes", "Clientes"],
        ["produtos", "Catálogo"],
        ["vendas", "Vendas"],
        ["financeiro", "Financeiro"],
      ]) {
        const row = document.createElement("tr");
        for (const text of [label, preview.fonte[name], preview.destino_atual[name]]) {
          const cell = document.createElement("td");
          cell.textContent = text;
          row.append(cell);
        }
        el("counts").append(row);
      }
      el("stockNote").textContent =
        `${preview.vendas_com_baixa_preservada} vendas com baixa de estoque preservada. ${preview.vendas_excluidas} vendas e ${preview.financeiro_excluido} lançamentos excluídos serão mantidos fora das listas.`;
      el("preview").hidden = false;
      el("acknowledge").checked = false;
      if (preview.ja_transferido) {
        receipt = await request("/transferencias/confirmar", {
          pacote: packet,
          preview_token: preview.preview_token,
        });
        el("receiptButton").hidden = false;
        show(
          "Este arquivo já foi transferido. O comprovante foi recuperado sem criar novos registros.",
        );
      } else show("Prévia pronta. Nenhum registro foi transferido ainda.");
    }),
  );
  el("acknowledge").addEventListener("change", controls);
  el("confirmButton").addEventListener("click", () =>
    run(async () => {
      show("Transferindo os quatro módulos em uma única transação…");
      receipt = await request("/transferencias/confirmar", {
        pacote: packet,
        preview_token: preview.preview_token,
      });
      preview = { ...preview, ja_transferido: true };
      el("receiptButton").hidden = false;
      show(
        "Transferência concluída. Baixe o comprovante e recarregue o SocialMEI para consultar os dados do servidor.",
      );
    }),
  );
  el("receiptButton").addEventListener("click", () => {
    if (!receipt) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(receipt, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "socialmei-comprovante-transferencia.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  controls();
})();
