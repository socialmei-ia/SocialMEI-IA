import { spawnSync } from "node:child_process";

function check(label, command, args) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    shell: process.platform === "win32",
  });

  const ok = !result.error && result.status === 0;
  const detail = ok
    ? (result.stdout || result.stderr || "").trim().split(/\r?\n/)[0]
    : result.error?.message || (result.stderr || result.stdout || "").trim().split(/\r?\n/)[0];

  console.log(`${ok ? "✅" : "❌"} ${label}${detail ? ` — ${detail}` : ""}`);
  return ok;
}

console.log("\nSocialMEI — diagnóstico do computador\n");

const git = check("Git", "git", ["--version"]);
const node = check("Node.js", process.execPath, ["--version"]);
const docker = check("Docker", "docker", ["--version"]);
const compose = check("Docker Compose", "docker", ["compose", "version"]);
const daemon = check("Docker Engine ativo", "docker", ["info", "--format", "{{.ServerVersion}}"]);

console.log("\nArquivos do projeto");
const files = [
  "compose.dev.yaml",
  ".env.development.example",
  "frontend/socialmei-app.html",
  "python-service/Dockerfile",
];

let filesOk = true;
for (const file of files) {
  const result = spawnSync(
    process.execPath,
    ["-e", `require("fs").accessSync(${JSON.stringify(file)})`],
    { encoding: "utf8" },
  );
  const ok = result.status === 0;
  filesOk &&= ok;
  console.log(`${ok ? "✅" : "❌"} ${file}`);
}

console.log("\nResultado");
if (git && node && docker && compose && daemon && filesOk) {
  console.log("✅ Este computador está pronto para rodar o ambiente local.");
  console.log("\nExecute:");
  console.log("  npm run setup");
  console.log("  npm run dev");
  console.log("  npm run status");
  process.exit(0);
}

console.log("❌ Ainda falta preparar algum item acima.");
console.log(
  "Se Docker Engine estiver vermelho, abra o Docker Desktop e espere ele ficar pronto.",
);
process.exit(1);
