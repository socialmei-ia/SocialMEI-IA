/* APPEARANCE */
function effectiveTheme() {
  return window.SocialMEIThemes.current().base;
}
function updateThemeButton() {
  const themes = window.SocialMEIThemes;
  const dark = effectiveTheme() === "dark";
  $("themeBtn").innerHTML = renderIcon(themes.active === "auto" ? "cfg" : dark ? "moon" : "sun");
  const name = themes.active === "auto" ? "Automático" : themes.current().name;
  $("themeBtn").setAttribute("aria-label", "Escolher tema: " + name);
  $("themeBtn").title = "Tema: " + name;
}
function setTheme(theme) {
  applyAppTheme(theme);
}
function renderAppearance() {
  const host = $("settingsPanel");
  if (!host) {
    return;
  }
  const active = THEMES.active;
  host.innerHTML = /* HTML */ `<div class="theme-settings-head">
            <div>
              <h3 class="section-title">Aparência</h3>
              <p class="section-sub">Sua identidade, em cada detalhe do SocialMEI.</p>
            </div>
            <button class="btn pr" type="button" data-theme-create>+ Criar tema</button>
          </div>
          <div class="theme-grid">
            ${["light", "dark"]
              .map((id) => {
                const t = THEMES.official[id];
                return /* HTML */ `<article class="theme-card ${active === id ? "is-active" : ""}">
                  ${themeMini(t)}
                  <div class="theme-card-heading">
                    <b>${t.name}</b><span class="theme-official">Oficial</span>
                  </div>
                  <p class="theme-help">
                    ${id === "light" ? "Leve, neutro e organizado." : "Marinho, carvão e leitura confortável."}
                  </p>
                  <div class="theme-card-actions">
                    <button
                      class="btn ${active === id ? "" : "pr"}"
                      type="button"
                      data-theme-apply="${id}"
                      aria-pressed="${active === id}"
                    >
                      ${active === id ? "✓ Ativo" : "Aplicar"}</button
                    ><button class="btn" type="button" data-theme-base="${id}"
                      >Usar como base</button
                    >
                  </div>
                </article>`;
              })
              .join("")}
            <article class="theme-card ${active === "auto" ? "is-active" : ""}">
              <div class="theme-auto-preview">
                ${themeMini(THEMES.official.light)}${themeMini(THEMES.official.dark)}
              </div>
              <div class="theme-card-heading"><b>Automático</b></div>
              <p class="theme-help">Seguir sistema · claro ou escuro.</p>
              <div class="theme-card-actions">
                <button
                  class="btn ${active === "auto" ? "" : "pr"}"
                  type="button"
                  data-theme-apply="auto"
                  aria-pressed="${active === "auto"}"
                >
                  ${active === "auto" ? "✓ Ativo" : "Aplicar"}
                </button>
              </div>
            </article>
            <article class="theme-card">
              ${themeMini(THEMES.current())}
              <div class="theme-card-heading"><b>Personalizado</b></div>
              <p class="theme-help">Crie sua própria identidade com duas cores.</p>
              <div class="theme-card-actions">
                <button class="btn" type="button" data-theme-create>Personalizar tema</button>
              </div>
            </article>
          </div>
          <section class="theme-personal">
            <div class="theme-section-head">
              <div>
                <h3 class="section-title">Meus temas</h3>
                <p class="section-sub">Salvos neste navegador · ${THEMES.themes.length}/40</p>
              </div>
              <button class="btn" type="button" data-theme-import>Importar JSON</button>
            </div>
            <div class="theme-grid">
              ${THEMES.themes
                .map(
                  (
                    t,
                  ) => /* HTML */ `<article class="theme-card ${active === t.id ? "is-active" : ""}">
                      ${themeMini(t)}
                      <div class="theme-card-heading">
                        <b>${escapeHtml(t.name)}</b
                        >${active === t.id ? '<span class="pill info">✓ Ativo</span>' : ""}
                      </div>
                      <p class="theme-help">${t.base === "dark" ? "Escuro" : "Claro"}</p>
                      <div class="theme-swatch-line">
                        <i class="theme-swatch" style="--swatch:${t.primary}"></i> ${t.primary}<i
                          class="theme-swatch"
                          style="--swatch:${t.accent}"
                        ></i>
                        ${t.accent}
                      </div>
                      <div class="theme-card-actions">
                        ${[
                          ["apply", "Aplicar"],
                          ["edit", "Editar"],
                          ["duplicate", "Duplicar"],
                          ["export", "Exportar"],
                          ["delete", "Excluir"],
                        ]
                          .map(
                            ([a, l]) => /* HTML */ `<button
                                class="btn ${a === "apply" ? "pr" : a === "delete" ? "theme-danger-btn" : ""}"
                                type="button"
                                data-theme-${a}="${t.id}"
                                ${a === "apply" ? `aria-pressed="${active === t.id}"` : ""}
                              >
                                ${l}
                              </button>`,
                          )
                          .join("")}
                      </div>
                    </article>`,
                )
                .join("")}
            </div>
            ${THEMES.themes.length ? "" : '<div class="theme-empty">Seu primeiro tema começa com duas cores. Use “Criar tema” ou importe um JSON.</div>'}
          </section>
          <div class="setting-row" style="margin-top:18px">
            <div><b>Privacidade financeira</b><small>Ocultar valores monetários</small></div>
            <button
              class="switch"
              id="settingsPrivacy"
              aria-label="Ocultar valores monetários"
              aria-pressed="${areMoneyValuesHidden}"
            ></button>
          </div>
          <p class="theme-help">
            Temas oficiais são protegidos. Use “Usar como base” para criar uma cópia editável.
          </p>`;
  finishSettingsPanel();
}
function renderThemeMenu() {
  const host = $("themeMenu");
  if (!host) {
    return;
  }
  const choices = [
    ["light", "SocialMEI Claro", "sun"],
    ["dark", "SocialMEI Escuro", "moon"],
    ["auto", "Automático · seguir sistema", "cfg"],
  ];
  host.innerHTML =
    choices
      .map(
        ([id, name, icon]) => /* HTML */ `<button
                  class="theme-menu-option"
                  role="menuitemradio"
                  aria-checked="${THEMES.active === id}"
                  data-theme-apply="${id}"
                >
                  <span class="theme-menu-label">${renderIcon(icon)}<span>${name}</span></span
                  ><span>${THEMES.active === id ? "✓" : ""}</span>
                </button>`,
      )
      .join("") +
    (THEMES.themes.length
      ? '<div class="mnu-sep"></div>' +
        THEMES.themes
          .map(
            (t) => /* HTML */ `<button
                      class="theme-menu-option"
                      role="menuitemradio"
                      aria-checked="${THEMES.active === t.id}"
                      data-theme-apply="${t.id}"
                    >
                      <span class="theme-menu-label"
                        ><i class="theme-swatch" style="--swatch:${t.primary}"></i
                        ><span>${escapeHtml(t.name)}</span></span
                      ><span>${THEMES.active === t.id ? "✓" : ""}</span>
                    </button>`,
          )
          .join("")
      : "") +
    '<div class="mnu-sep"></div><button role="menuitem" type="button" data-theme-config>' +
    renderIcon("cfg") +
    "Configurar aparência</button>";
}
function applyAppTheme(id) {
  const t = THEMES.themes.find((x) => x.id === id);
  if (t && THEMES.checks(t).some((x) => !x.pass)) {
    openThemeStudio(t);
    toast("Revise o contraste", "Corrija as combinações indicadas antes de aplicar este tema.");
    return;
  }
  const saved = THEMES.select(id);
  updateThemeButton();
  renderThemeMenu();
  requestAnimationFrame(renderDashboardChart);
  if (currentView === "Configurações" && selectedSettingsTab === "aparencia") {
    renderAppearance();
  }
  if (!document.body.classList.contains("experience-app")) {
    return;
  }
  if (!saved) {
    toast("Tema aplicado nesta sessão", "O navegador não permitiu salvar a preferência.");
  } else {
    toast("Tema aplicado", THEMES.current().name);
  }
}
function renderThemeControls() {
  const d = themeDraft;
  const t = THEMES.build(d);
  $("themeStudioControls").innerHTML = /* HTML */ ` <div class="theme-control">
            <label for="themeName">Nome do tema</label
            ><input
              class="form-control"
              id="themeName"
              maxlength="60"
              value="${escapeHtml(d.name)}"
              required
            />
          </div>
          <div class="theme-control">
            <label for="themeBase">Base</label
            ><select class="form-control" id="themeBase">
              <option value="light" ${d.base === "light" ? "selected" : ""}>Claro</option>
              <option value="dark" ${d.base === "dark" ? "selected" : ""}>Escuro</option>
            </select>
          </div>
          ${colorControl("primary", "Cor principal", d.primary)}${colorControl("accent", "Cor de destaque", d.accent)}
          <div class="theme-control">
            <label for="themeIntensity"
              >Intensidade da identidade
              <output id="themeIntensityValue">${d.intensity}%</output></label
            ><input id="themeIntensity" type="range" min="0" max="100" value="${d.intensity}" />
            <div class="theme-range-labels"><span>Sutil</span><span>Marcante</span></div>
          </div>
          <div class="theme-control">
            <label>Sugestões de paletas</label>
            <div class="theme-presets">
              ${THEME_PRESETS.map(
                (
                  p,
                  i,
                ) => /* HTML */ `<button class="theme-preset" type="button" data-theme-preset="${i}">
                    <span class="theme-preset-colors"
                      ><i class="theme-swatch" style="--swatch:${p.primary}"></i
                      ><i class="theme-swatch" style="--swatch:${p.accent}"></i
                      ><i class="theme-swatch" style="--swatch:${t.surface}"></i></span
                    >${p.name}
                  </button>`,
              ).join("")}
            </div>
          </div>
          <p class="theme-tip" id="themeTip">
            Use o destaque com moderação. Sua cor principal será preservada; os tons de texto são
            gerados para facilitar a leitura.
          </p>
          <details class="theme-advanced" id="themeAdvanced">
            <summary>Configurações avançadas</summary>
            <div class="theme-advanced-grid">
              ${THEME_ADVANCED.map(([k, label]) => colorControl(k, label, t[k], true)).join("")}
            </div>
            <p class="theme-help" style="margin-top:10px">
              Ajustes finos opcionais. O contraste será verificado antes de salvar.
            </p>
          </details>
          <label class="theme-status-choice"
            ><input
              id="themeRecommendedStatus"
              type="checkbox"
              ${d.recommendedStatus !== false ? "checked" : ""}
            />Usar cores de status recomendadas</label
          >
          <div
            class="theme-status-fields"
            id="themeStatusFields"
            ${d.recommendedStatus !== false ? "hidden" : ""}
          >
            <p class="theme-studio-alert">
              ⚠ Alterar cores de status pode dificultar a identificação de informações importantes.
            </p>
            <div class="theme-advanced-grid">
              ${THEME_STATUS.map(([k, l]) => colorControl(k, l, t[k], true)).join("")}
            </div>
          </div>`;
}
function openThemeStudio(theme = null, asCopy = false) {
  const current = theme || THEMES.current();
  themeDraft = JSON.parse(JSON.stringify(current));
  if (!theme || asCopy) {
    delete themeDraft.id;
    themeDraft.name = theme ? theme.name + " (cópia)" : "Meu tema";
    themeDraft.name = themeDraft.name.slice(0, 60);
  }
  themeHexErrors.clear();
  selectedThemePreviewTab = "dashboard";
  $("themeStudioTitle").textContent = themeDraft.id ? "Editar tema" : "Personalizar tema";
  renderThemeControls();
  renderThemePreview();
  openModal("themeStudio");
}
function renderThemePreview() {
  const tab = selectedThemePreviewTab;
  $("themePreviewTabs").innerHTML = [
    ["dashboard", "Início"],
    ["inbox", "Caixa Unificada"],
    ["components", "Componentes"],
  ]
    .map(
      ([id, name]) => /* HTML */ `<button
                role="tab"
                id="theme-preview-tab-${id}"
                aria-selected="${tab === id}"
                aria-controls="themePreview"
                tabindex="${tab === id ? "0" : "-1"}"
                type="button"
                data-theme-preview-tab="${id}"
              >
                ${name}
              </button>`,
    )
    .join("");
  const host = $("themePreview");
  host.setAttribute("aria-labelledby", "theme-preview-tab-" + tab);
  if (tab === "dashboard") {
    host.innerHTML = /* HTML */ `<div class="theme-preview-frame">
            <aside class="theme-preview-nav">
              <strong>SocialMEI</strong><span>Visão Geral</span><span>Financeiro</span
              ><span>Clientes</span><span>Atendimento</span>
            </aside>
            <div class="theme-preview-main">
              <div class="theme-preview-header">
                <b>Seu negócio hoje</b
                ><i class="theme-swatch" style="--swatch:var(--brand-accent)"></i>
              </div>
              <div class="theme-preview-kpi">
                <span class="muted">Faturamento</span><b>R$ 12.480</b
                ><span class="text-success">✓ Dados de exemplo</span>
                <div class="theme-preview-chart" role="img" aria-label="Prévia do gráfico">
                  ${[38, 60, 46, 76, 62, 92].map((h) => /* HTML */ `<i style="--bar-height:${h}%"></i>`).join("")}
                </div>
              </div>
              <table class="theme-preview-table">
                <thead>
                  <tr>
                    <th>Cliente</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Maria Silva</td>
                    <td><span class="pill green">Pago</span></td>
                  </tr>
                  <tr>
                    <td>Juliana Prado</td>
                    <td><span class="pill amber">Pendente</span></td>
                  </tr>
                </tbody>
              </table>
              <div class="theme-preview-footer">
                <button type="button" class="btn pr">Nova venda</button
                ><button type="button" class="btn">Ver relatório</button>
              </div>
            </div>
          </div>`;
  } else if (tab === "inbox") {
    host.innerHTML = /* HTML */ `<div class="theme-preview-inbox">
            <aside class="theme-preview-convs">
              <b>Conversas</b>
              <div class="theme-preview-conv">
                <b>Maria Silva</b><small>Vi no Instagram</small
                ><span class="unread" style="margin-top:6px">2</span>
              </div>
              <p class="muted" style="margin-top:14px">Juliana Prado</p>
            </aside>
            <div class="theme-preview-chat">
              <div class="theme-preview-header">
                <b>Maria Silva</b><span class="pill green">Conectado</span>
              </div>
              <div class="msg in">Oi! Vocês têm essa camisa?<small>13:46</small></div>
              <div class="msg out">Temos sim. Posso ajudar com o tamanho?<small>13:47</small></div>
              <div>
                <span class="details-tag" style="background:var(--bs);color:var(--bi)"
                  >Novo cliente</span
                >
              </div>
              <div class="msg note">Separar tamanho M.</div>
              <div class="theme-preview-compose">
                <input placeholder="Digite uma mensagem…" aria-label="Mensagem de prévia" /><button
                  class="btn pr ib"
                  type="button"
                  aria-label="Enviar na prévia"
                >
                  ${renderIcon("send")}
                </button>
              </div>
            </div>
          </div>`;
  } else {
    host.innerHTML = /* HTML */ `<div class="theme-preview-components">
            <div class="theme-preview-component-row">
              <button class="btn pr" type="button">Salvar</button
              ><button class="btn" type="button">Cancelar</button
              ><button class="btn" type="button" disabled>Indisponível</button>
            </div>
            <div class="theme-preview-component-row">
              <input
                class="form-control"
                placeholder="Nome do cliente"
                aria-label="Nome do cliente na prévia"
              /><select class="form-control" aria-label="Opção da prévia">
                <option>Todos os clientes</option>
                <option>Ativos</option>
                <option>Novos</option>
              </select>
            </div>
            <div class="theme-preview-component-row">
              <span class="pill" style="color:var(--bi);background:var(--bs)">Selecionado</span
              ><span class="pill amber">⚠ Atenção</span><span class="pill green">✓ Sucesso</span
              ><span class="pill red">× Erro</span><span class="pill info">ⓘ Informação</span>
            </div>
            <div class="theme-preview-component-row">
              <button
                class="switch"
                type="button"
                data-theme-demo-toggle
                aria-label="Alternar controle da prévia"
                aria-pressed="true"
              ></button
              ><span>Notificações</span>
            </div>
            <div class="theme-preview-notification">
              <i class="theme-swatch" style="--swatch:var(--brand-accent)"></i>Nova notificação<span
                class="pill"
                style="margin-left:auto;background:var(--brand-accent);color:var(--on-accent)"
                >Novo</span
              >
            </div>
            <details>
              <summary
                style="padding:8px;border:1px solid var(--ln);border-radius:7px;cursor:pointer"
              >
                Mais opções ▾
              </summary>
              <div
                style="padding:10px;background:var(--sf);border:1px solid var(--ln);margin-top:4px;color:var(--bi)"
              >
                Detalhes do tema e seleção
              </div>
            </details>
          </div>`;
  }
  refreshThemePreview();
}
function refreshThemePreview() {
  if (!themeDraft) {
    return;
  }
  THEMES.applyTokens($("themePreview"), themeDraft);
  const list = THEMES.checks(themeDraft);
  const fails = list.filter((x) => !x.pass);
  const primary = list.find((x) => x.label === "Texto / botão principal");
  const accent = list.find((x) => x.label === "Texto / destaque");
  const validName = themeDraft.name.trim().length > 0 && themeDraft.name.length <= 60;
  $("themeQuality").innerHTML = /* HTML */ `<h4>Qualidade do tema</h4>
          <p class="theme-help">Contraste WCAG · mínimo de 4,5:1 para texto normal.</p>
          <ul class="theme-quality-list">
            <li>
              <span>Contraste</span
              ><b class="${fails.length ? "text-danger" : "text-success"}"
                >${fails.length ? "⚠ Revisar" : "✓ Bom"}</b
              >
            </li>
            <li>
              <span>Legibilidade</span
              ><b>${fails.length ? "⚠ " + fails.length + " ajuste(s)" : "✓ Boa"}</b>
            </li>
            <li><span>Texto sobre principal</span><b>${primary.pass ? "✓ AA" : "⚠ Atenção"}</b></li>
            <li><span>Destaque</span><b>${accent.pass ? "✓ AA" : "⚠ Atenção"}</b></li>
          </ul>
          <details class="theme-quality-details">
            <summary>Ver ${list.length} combinações verificadas</summary>
            <table>
              <tbody>
                ${list
                  .map(
                    (x) => /* HTML */ `<tr>
                        <td>${x.label}</td>
                        <td>${x.pass ? "✓ AA" : "⚠ Falha"} · ${x.ratio.toFixed(2)}:1</td>
                      </tr>`,
                  )
                  .join("")}
              </tbody>
            </table>
          </details>`;
  const alert = $("themeStudioAlert");
  alert.hidden = !fails.length && !themeHexErrors.size && validName;
  alert.textContent = themeHexErrors.size
    ? "⚠ Use HEX no formato #RRGGBB. A prévia mantém a última cor válida."
    : !validName
      ? "⚠ Dê um nome ao tema."
      : fails.length
        ? "⚠ Essa combinação pode dificultar a leitura. Corrija o contraste para salvar."
        : "";
  $("themeAutoFix").hidden = !fails.length;
  $("themeSave").disabled = $("themeSaveApply").disabled =
    !!fails.length || !!themeHexErrors.size || !validName;
}
function syncThemeColorControls() {
  const t = THEMES.build(themeDraft);
  document.querySelectorAll("#themeStudio [data-theme-color]").forEach((element) => {
    const key = element.dataset.themeColor;
    element.value = element.dataset.themeAdvanced === "true" ? t[key] : themeDraft[key];
    element.removeAttribute("aria-invalid");
  });
}
function saveThemeDraft(apply = false) {
  if (!themeDraft) {
    return;
  }
  if (themeHexErrors.size || THEMES.checks(themeDraft).some((x) => !x.pass)) {
    toast("Revise as cores e o contraste");
    return;
  }
  try {
    const saved = THEMES.save(themeDraft);
    if (apply) {
      applyAppTheme(saved.id);
    } else if (THEMES.active === saved.id) {
      updateThemeButton();
      requestAnimationFrame(renderDashboardChart);
    }
    closeModal("themeStudio");
    themeDraft = null;
    renderThemeMenu();
    if (currentView === "Configurações" && selectedSettingsTab === "aparencia") {
      renderAppearance();
    }
    toast(apply ? "Tema salvo e aplicado" : "Tema salvo", saved.name);
  } catch (error) {
    toast("Não foi possível salvar", error.message);
  }
}
function exportTheme(theme) {
  const data = {
    version: 1,
    name: theme.name,
    base: theme.base,
    primary: theme.primary,
    accent: theme.accent,
    intensity: theme.intensity,
    recommendedStatus: theme.recommendedStatus,
    overrides: theme.overrides,
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download =
    "socialmei-tema-" +
    theme.name
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .slice(0, 60) +
    ".json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("Tema exportado", "Arquivo JSON pronto para importar.");
}
async function importThemeFile(file) {
  if (!file) {
    return;
  }
  try {
    if (file.size > 16384) {
      throw Error("O JSON deve ter no máximo 16 KB.");
    }
    const raw = await file.text();
    if (new TextEncoder().encode(raw).length > 16384) {
      throw Error("O JSON deve ter no máximo 16 KB.");
    }
    const t = THEMES.validate(JSON.parse(raw));
    openThemeStudio(t, true);
    themeDraft.name = t.name;
    renderThemeControls();
    refreshThemePreview();
    toast("Tema importado para revisão", "Use Salvar para adicioná-lo aos seus temas.");
  } catch (error) {
    toast(
      "Importação inválida",
      error instanceof SyntaxError ? "O arquivo não contém JSON válido." : error.message,
    );
  } finally {
    $("themeImportInput").value = "";
  }
}
