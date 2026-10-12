const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const root = path.resolve(__dirname, "..");
test(
  "export preserves its identity and refuses to overwrite an existing snapshot",
  { skip: process.platform === "win32" },
  () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "socialmei-export-"));
    try {
      fs.writeFileSync(path.join(directory, ".env.development"), "# CI fixture\n");
      const fake = path.join(directory, "docker");
      fs.writeFileSync(
        fake,
        `#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps({'formato':'socialmei-workspace-transfer','origem':sys.argv[-1],'clientes':[{'id':1}],'produtos':[],'vendas':[],'financeiro':[]}))\n`,
        { mode: 0o700 },
      );
      const env = {
        ...process.env,
        SOCIALMEI_TRANSFER_DIR: path.join(directory, "private"),
        PATH: directory + path.delimiter + process.env.PATH,
      };
      const run = () =>
        spawnSync(process.execPath, [path.join(root, "tools/export-workspace.mjs")], {
          cwd: directory,
          env,
          encoding: "utf8",
        });
      assert.equal(run().status, 0);
      const identity = fs.readFileSync(path.join(directory, "private/origem.json"), "utf8");
      const snapshot = fs.readFileSync(
        path.join(directory, "private/socialmei-transferencia-notebook.json"),
        "utf8",
      );
      assert.equal(JSON.parse(snapshot).origem, JSON.parse(identity).origem);
      assert.equal(run().status, 1);
      assert.equal(
        fs.readFileSync(
          path.join(directory, "private/socialmei-transferencia-notebook.json"),
          "utf8",
        ),
        snapshot,
      );
      assert.equal(fs.readFileSync(path.join(directory, "private/origem.json"), "utf8"), identity);
    } finally {
      fs.rmSync(directory, { recursive: true, force: true });
    }
  },
);
test(
  "failed Docker export leaves no data file and retains the same retry identity",
  { skip: process.platform === "win32" },
  () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "socialmei-export-failure-"));
    try {
      fs.writeFileSync(path.join(directory, ".env.development"), "# CI fixture\n");
      fs.writeFileSync(path.join(directory, "docker"), "#!/bin/sh\nexit 1\n", { mode: 0o700 });
      const args = {
        cwd: directory,
        env: {
          ...process.env,
          SOCIALMEI_TRANSFER_DIR: path.join(directory, "private"),
          PATH: directory + path.delimiter + process.env.PATH,
        },
        encoding: "utf8",
      };
      assert.equal(
        spawnSync(process.execPath, [path.join(root, "tools/export-workspace.mjs")], args).status,
        1,
      );
      const identity = fs.readFileSync(path.join(directory, "private/origem.json"), "utf8");
      assert.equal(
        spawnSync(process.execPath, [path.join(root, "tools/export-workspace.mjs")], args).status,
        1,
      );
      assert.equal(fs.readFileSync(path.join(directory, "private/origem.json"), "utf8"), identity);
      assert(!fs.existsSync(path.join(directory, "private/socialmei-transferencia-notebook.json")));
    } finally {
      fs.rmSync(directory, { recursive: true, force: true });
    }
  },
);
