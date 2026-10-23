// Exercise the newly explicit secondary analysis entry through its visible disclosure.
async function openOpportunityAnalysis(page) {
  const disclosure = page.locator("#opportunityMessageAnalysis");
  if ((await disclosure.count()) && !(await disclosure.evaluate((el) => el.open)))
    await disclosure.locator(":scope > summary").click();
}
module.exports = { openOpportunityAnalysis };
