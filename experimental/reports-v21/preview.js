/* Load the native document without duplicating markup, calculations or stores. */
(async () => {
  const root = new URL("../../", location.href);
  const preview = new URL("experimental/reports-v21/", root);
  try {
    const response = await fetch(new URL("frontend/socialmei-app.html", root));
    if (!response.ok) throw Error("Não foi possível ler a aplicação local.");
    let html = await response.text();
    if (html.split('<script src="config.js"></script>').length !== 2)
      throw Error("A configuração nativa mudou. Prévia bloqueada por segurança.");
    html = html.replace(
      "<head>",
      `<head><base href="${new URL("frontend/", root).href}"><script src="${preview}sandbox.js"></script>`,
    );
    html = html.replace(
      '<script src="config.js"></script>',
      `<script src="${preview}config.js"></script>`,
    );
    html = html.replace("</body>", `<script src="${preview}experience.js"></script></body>`);
    html = html.replace(
      "</head>",
      `<link rel="icon" href="${new URL("frontend/assets/brand-icon.png", root)}"><link rel="stylesheet" href="${preview}preview.css"></head>`,
    );
    document.open();
    document.write(html);
    document.close();
  } catch (error) {
    document.getElementById("previewLoading").textContent =
      error.message + " Abra esta pasta por um servidor HTTP na raiz do repositório.";
  }
})();
