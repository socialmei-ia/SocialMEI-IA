"""Enable the private account pilot after database/admin provisioning."""

import argparse
import fcntl
import json
import os
import re
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "deploy/team/private"


def private_write(path, contents):
    temporary = path.with_name(path.name + ".accounts-" + secrets.token_hex(4))
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as file:
            file.write(contents)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def enable():
    with (PRIVATE / ".accounts.lock").open("a") as lock:
        os.fchmod(lock.fileno(), 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Outra ativação de contas está em andamento.") from None
        _enable()


def _enable():
    env = ROOT / ".env.team"
    config_file = PRIVATE / "config.js"
    env_text = env.read_text()
    config_text = config_file.read_text()
    if not (PRIVATE / "users.Caddyfile").read_text().strip():
        raise RuntimeError("Confira a proteção Basic antes de ativar as contas.")
    match = re.search(r"Object\.freeze\(([\s\S]+)\);\s*$", config_text)
    if not match:
        raise RuntimeError("Configuração pública precisa ser conferida.")
    config = json.loads(match[1])
    for module in ["clientes", "produtos", "vendas", "financeiro"]:
        if (
            config.get(module, {}).get("mode") != "remote"
            or config[module].get("apiBaseUrl") != "/api/v1"
        ):
            raise RuntimeError("Os quatro módulos precisam usar a API do mesmo site.")
    check = "from database import connect; c=connect(); print(c.execute(\"SELECT COUNT(*) FROM socialmei.auth_credenciais a JOIN socialmei.workspace_members m ON m.user_id=a.user_id JOIN socialmei.workspaces w ON w.id=m.workspace_id WHERE a.ativo AND a.administrador_plataforma AND w.slug='team' AND m.role='owner'\").fetchone()[0]); c.close()"
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env),
            "-f",
            str(ROOT / "compose.team.yaml"),
            "exec",
            "-T",
            "team-api",
            "python",
            "-c",
            check,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if (
        result.returncode
        or not result.stdout.strip().isdigit()
        or int(result.stdout.strip()) < 1
    ):
        raise RuntimeError(
            "Prepare a migration e a conta administrativa antes de ativar."
        )
    snapshot = PRIVATE / ("accounts-before-" + secrets.token_hex(6))
    snapshot.mkdir(mode=0o700)
    for name, contents in [("env.team", env_text), ("config.js", config_text)]:
        target = snapshot / name
        private_write(target, contents)
    config["auth"] = {"mode": "remote", "apiBaseUrl": "/api/v1"}
    updated_config = (
        "/* PUBLIC CONFIGURATION — no credentials */\nconst SOCIALMEI_CONFIG = Object.freeze("
        + json.dumps(config, ensure_ascii=False, indent=2)
        + ");\n"
    )
    updated_env = (
        re.sub(r"(?m)^TEAM_AUTH_ENABLED=.*$", "TEAM_AUTH_ENABLED=true", env_text)
        if re.search(r"(?m)^TEAM_AUTH_ENABLED=", env_text)
        else env_text.rstrip() + "\nTEAM_AUTH_ENABLED=true\n"
    )
    try:
        # No restart here: apply API/gateway together in the reviewed deployment step.
        private_write(env, updated_env)
        private_write(config_file, updated_config)
    except OSError:
        private_write(env, env_text)
        private_write(config_file, config_text)
        raise
    print(
        "Configuração de contas preparada. Recrie API/gateway; a proteção Basic permanece ativa."
    )
    print("Cópia privada anterior:", snapshot)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["enable"])
    parser.parse_args()
    try:
        enable()
    except (OSError, ValueError, RuntimeError):
        parser.exit(
            1,
            "Ativação não concluída. Confira banco, administrador e configuração privada; nenhum segredo foi exibido.\n",
        )


if __name__ == "__main__":
    main()
