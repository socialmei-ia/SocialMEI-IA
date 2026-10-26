// User-visible access to the original V4 dock and progressive disclosures.
// No application state, permissions, disabled controls or styles are bypassed.
async function revealContentControl(page, selector) {
  const control = page.locator(selector).first();
  await control.waitFor({ state: "attached" });
  const panel = await control.evaluate(
    (el) =>
      el.closest(
        "#contentCreatePanel,#contentDraftsPanel,#contentAgendaPanel,#contentConnectionsPanel",
      )?.id,
  );
  const tabs = {
    contentCreatePanel: "create",
    contentDraftsPanel: "drafts",
    contentAgendaPanel: "agenda",
    contentConnectionsPanel: "connections",
  };
  if (
    panel &&
    ((await page.locator("#" + panel).isHidden()) ||
      (await page.locator("#contentWorkspace-" + tabs[panel]).getAttribute("aria-selected")) !==
        "true")
  ) {
    await page.evaluate(() => document.activeElement?.blur());
    await page.locator("#contentWorkspace-" + tabs[panel]).click();
    await page.locator("#" + panel).waitFor({ state: "visible" });
  }
  for (let depth = 0; depth < 8; depth++) {
    const closed = control.locator("xpath=ancestor::details[not(@open)]").first();
    if (!(await closed.count())) break;
    await closed.locator(":scope > summary").click();
  }
}
async function contentDock(page, name) {
  await page.evaluate(() => document.activeElement?.blur());
  await page.locator("#contentWorkspace-" + name).click();
}
module.exports = { revealContentControl, contentDock };
