"""Prepare local server-only credentials; never prints plaintext passwords."""

import argparse
import getpass
import json
import os
import re
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "deploy/team/private"
ENV = ROOT / ".env.team"
USER_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,39}")


def validate_host(host):
    host = host.lower().strip()
    parts = host.split(".")
    if len(host) > 253 or len(parts) < 2 or not any(c.isalpha() for c in host):
        raise ValueError(
            "Informe somente um hostname público, sem https, porta ou caminho."
        )
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p) for p in parts):
        raise ValueError("Hostname inválido.")
    return host


def hash_password(password):
    if (
        not 12 <= len(password)
        or len(password.encode()) > 72
        or "\n" in password
        or "\r" in password
    ):
        raise ValueError(
            "Use pelo menos 12 caracteres, no máximo 72 bytes, sem quebras de linha."
        )
    result = subprocess.run(
        ["docker", "run", "--rm", "-i", "caddy:2-alpine", "caddy", "hash-password"],
        input=password + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    hashed = result.stdout.strip()
    if result.returncode or not re.fullmatch(
        r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}", hashed
    ):
        raise RuntimeError("Não foi possível gerar o hash com Docker/Caddy.")
    return hashed


def write_private(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(content)
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def ask_user():
    user = input("Usuário individual (ex.: mike): ").strip()
    if not USER_PATTERN.fullmatch(user):
        raise ValueError(
            "Usuário inválido; use letras, números, ponto, hífen ou sublinhado."
        )
    password = getpass.getpass("Senha individual (não será exibida): ")
    if password != getpass.getpass("Repita a senha: "):
        raise ValueError("Senhas diferentes.")
    return user, hash_password(password)


def users():
    file = PRIVATE / "users.Caddyfile"
    if not file.is_file():
        raise RuntimeError("Execute init primeiro no servidor.")
    return dict(line.split() for line in file.read_text().splitlines() if line.strip())


def init(host):
    host = validate_host(host)
    if ENV.exists() or PRIVATE.exists():
        raise RuntimeError(
            "Configuração já existe; init não sobrescreve banco nem credenciais."
        )
    existing = ROOT / ".env"
    if existing.exists():
        for line in existing.read_text().splitlines():
            key, separator, value = line.partition("=")
            if (
                separator
                and key.strip()
                in {"N8N_HOST", "PGADMIN_HOST", "WAHA_HOST", "PYTHON_API_HOST"}
                and value.strip().strip("\"'").lower() == host
            ):
                raise ValueError("Use um hostname diferente dos serviços existentes.")
    user, hashed = ask_user()
    write_private(PRIVATE / "users.Caddyfile", f"{user} {hashed}\n")
    write_private(
        ENV,
        f"SOCIALMEI_TEAM_HOST={host}\nTEAM_POSTGRES_PASSWORD={secrets.token_urlsafe(36)}\n",
    )
    source = {"mode": "remote", "apiBaseUrl": "/api/v1", "workspaceKey": "team"}
    config = {
        "n8nMessagesUrl": None,
        "n8nAuthHeader": None,
        **{key: source for key in ["clientes", "produtos", "vendas", "financeiro"]},
    }
    write_private(
        PRIVATE / "config.js",
        "/* PUBLIC CONFIGURATION — no credentials */\nconst SOCIALMEI_CONFIG = Object.freeze("
        + json.dumps(config, ensure_ascii=False, indent=2)
        + ");\n",
    )
    write_private(
        PRIVATE / "site.Caddyfile",
        f"{host} {{\n    reverse_proxy socialmei-team-gateway:80\n}}\n",
    )
    print("Configuração preparada. Nenhum serviço foi publicado ou reiniciado.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init").add_argument("--host", required=True)
    commands.add_parser("add-user")
    commands.add_parser("remove-user").add_argument("username")
    args = parser.parse_args()
    try:
        if args.command == "init":
            init(args.host)
        else:
            accounts = users()
            if args.command == "add-user":
                user, hashed = ask_user()
                accounts[user] = hashed
            else:
                if args.username not in accounts:
                    raise ValueError("Usuário não encontrado.")
                if len(accounts) == 1:
                    raise ValueError(
                        "Não remova o último usuário; deixe a entrada HTTPS desativada para bloquear todos."
                    )
                del accounts[args.username]
            write_private(
                PRIVATE / "users.Caddyfile",
                "".join(
                    f"{user} {hashed}\n" for user, hashed in sorted(accounts.items())
                ),
            )
            print("Usuários atualizados. Valide e recarregue somente o team-gateway.")
    except (ValueError, RuntimeError, OSError):
        parser.exit(
            1,
            "Configuração não concluída. Confira hostname, usuário, senha e Docker; arquivos existentes são preservados.\n",
        )


if __name__ == "__main__":
    main()
