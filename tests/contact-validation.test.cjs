const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const vm = require("node:vm");
const context = { window: {}, document: { addEventListener() {} } };
vm.runInNewContext(fs.readFileSync("frontend/scripts/contact-validation.js", "utf8"), context);
const contacts = context.window.SocialMEIContacts;

test("Contact validation keeps countries and identifiers separate", () => {
  for (const input of [
    "11987654321",
    "11999999999",
    "(11) 3333-3333",
    "(81) 3456-7890",
    "+55 (81) 98765-4321",
    "+1 415 555 2671",
  ]) {
    assert.equal(contacts.phone(input, true).valid, true, input);
  }
  for (const input of [
    "32132132131",
    "abc11987654321",
    "@maria",
    "00123456789",
    "119876543210",
    "+551198765432100",
    "１１９８７６５４３２１",
  ]) {
    assert.equal(contacts.phone(input, true).valid, false, input);
  }
  assert.equal(contacts.phone("11987654321").value, "(11) 98765-4321");
  assert.equal(contacts.phone("+55 (81) 98765-4321").international, "+5581987654321");
  assert.equal(contacts.phone("", true).valid, false);
  assert.equal(contacts.phone("", false).valid, true);
  for (const input of ["@maria.loja", "loja_81", "@12345"])
    assert.equal(contacts.instagram(input).valid, true);
  for (const input of [
    "11987654321",
    "11999999999",
    "(11) 3333-3333",
    "(81) 98765-4321",
    "https://instagram.com/maria",
    "@maria loja",
    "@maria..loja",
    "@maria.",
  ]) {
    assert.equal(contacts.instagram(input).valid, false, input);
  }
});
