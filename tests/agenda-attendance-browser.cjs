const assert = require("node:assert/strict");
const path = require("node:path");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ channel: "chrome" });
  try {
    for (const width of [390, 1280]) {
      const page = await browser.newPage({ viewport: { width, height: 800 } });
      await page.route("**/*", (route) =>
        route.fulfill({
          contentType: "text/html",
          body: '<main class="sm-agenda"></main><dialog></dialog>',
        }),
      );
      await page.goto("http://localhost:8724/#/agenda");
      await page.evaluate(() => {
        window.dlg = () => document.querySelector("dialog");
        window.openForm = (title, _, fields, ok, label) => {
          const form = document.createElement("form");
          const head = document.createElement("h2"),
            button = document.createElement("button");
          head.textContent = title;
          button.textContent = label;
          form.append(head, button);
          window.dlg().replaceChildren(form);
          window.dlg().showModal();
        };
        const rows = [-1, 1].map((sign) => ({
          id: crypto.randomUUID(),
          client_name: "Cliente",
          service_name: sign > 0 ? "Futuro" : "Passado",
          resource_name: "Equipe",
          status: "pending",
          revision: 1,
          attendance: null,
          scheduled_for: new Date(Date.now() + sign * 86400000).toISOString(),
          ends_at: new Date(Date.now() + sign * 86400000 + 1800000).toISOString(),
        }));
        window.attendanceWrites = [];
        window.SocialMEIV22 = {
          remote: true,
          identity: { usuario: { id: 1 }, negocio: { id: 2 }, papel: "owner" },
          request: async (url, method, body) => {
            if (method !== "POST") return { items: structuredClone(rows), truncated: false };
            const row = rows.find(
              (entry) => url === "/agenda/appointments/" + entry.id + "/attendance",
            );
            if (!row || row.revision !== body.expected_revision)
              throw Error("Unexpected appointment operation");
            window.attendanceWrites.push(body);
            row.attendance = body.status;
            row.revision++;
            return { attendance: row.attendance, revision: row.revision };
          },
        };
      });
      await page.addScriptTag({
        path: path.join(__dirname, "../frontend/scripts/v22-appointments.js"),
      });
      for (const [label, result] of [
        ["Confirmar presença", "Presença confirmada"],
        ["Registrar ausência", "Ausência registrada"],
      ]) {
        await page.getByRole("button", { name: label, exact: true }).click();
        assert.equal(
          await page.evaluate(() => window.attendanceWrites.length),
          label.startsWith("Confirmar") ? 0 : 1,
        );
        await page.locator("dialog").getByRole("button", { name: label, exact: true }).click();
        await page.getByText(result, { exact: true }).waitFor();
      }
      const writes = await page.evaluate(() => window.attendanceWrites);
      assert.deepEqual(
        writes.map((row) => row.status),
        ["confirmed", "no_show"],
      );
      assert.notEqual(writes[0].operation_id, writes[1].operation_id);
      await page.close();
    }
    console.log("Attendance confirmation, absence and explicit submit passed at 390px and 1280px");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
