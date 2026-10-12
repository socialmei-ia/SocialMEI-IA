import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { homedir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const directory = process.env.SOCIALMEI_TRANSFER_DIR || join(homedir(), "SocialMEI-Transferencia");
const identityFile = join(directory, "origem.json");
const outputFile = join(directory, "socialmei-transferencia-notebook.json");
try {
  if (existsSync(outputFile))
    throw new Error(
      `O arquivo ${outputFile} já existe. Preserve-o e use esse mesmo arquivo na transferência.`,
    );
  if (!existsSync(".env.development")) throw new Error("Configure o ambiente local primeiro.");
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  if (!existsSync(identityFile))
    writeFileSync(
      identityFile,
      JSON.stringify({ origem: randomUUID(), workspace: "development" }),
      { flag: "wx", mode: 0o600 },
    );
  const identity = JSON.parse(readFileSync(identityFile, "utf8"));
  if (
    !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(identity.origem) ||
    identity.workspace !== "development"
  )
    throw new Error(
      "Identidade de exportação inválida; preserve o arquivo e confira antes de continuar.",
    );
  const result = spawnSync(
    "docker",
    [
      "compose",
      "--env-file",
      ".env.development",
      "-f",
      "compose.dev.yaml",
      "exec",
      "-T",
      "python-api",
      "python",
      "workspace_export.py",
      identity.origem,
    ],
    { encoding: "utf8", maxBuffer: 4_000_000 },
  );
  if (result.error || result.status !== 0)
    throw new Error(
      "Não foi possível exportar. Atualize a API com npm.cmd run dev e confira as migrations antes de repetir.",
    );
  const packet = JSON.parse(result.stdout);
  if (packet.formato !== "socialmei-workspace-transfer" || packet.origem !== identity.origem)
    throw new Error("Resposta de exportação inválida.");
  const encoded = JSON.stringify(packet);
  if (Buffer.byteLength(encoded) > 2_000_000)
    throw new Error("Arquivo excede 2 MB. Nenhum arquivo de dados foi sobrescrito.");
  writeFileSync(outputFile, encoded, { flag: "wx", mode: 0o600 });
  console.log(
    `Criado ${outputFile}. Guarde-o no notebook e envie somente pela página protegida de transferência.`,
  );
  for (const name of ["clientes", "produtos", "vendas", "financeiro"])
    console.log(`${name}: ${packet[name].length}`);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
