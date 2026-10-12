"""Manutenção da equipe: backups, diagnóstico e n8n sem publicar segredos."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "deploy/team/private"
BACKUPS = Path.home() / "socialmei-backups"
MARKER = "# SOCIALMEI_TEAM_BACKUP"


def run(args, **kwargs):
    result = subprocess.run(args, check=False, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError("Comando não concluído: " + " ".join(args[:3]))
    return result.stdout


def compose(*args):
    return [
        "docker",
        "compose",
        "--env-file",
        str(ROOT / ".env.team"),
        "-f",
        str(ROOT / "compose.team.yaml"),
        *args,
    ]


def environment():
    values = {}
    for line in (ROOT / ".env.team").read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            values[key.strip()] = value.strip().strip("\"'")
    host = values.get("SOCIALMEI_TEAM_HOST", "")
    if (
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", host)
        or "." not in host
    ):
        raise RuntimeError("Hostname da equipe inválido.")
    return values


def private_write(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(data)


def backup():
    environment()
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (BACKUPS / ".team-backup.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Outro backup da equipe já está em andamento.") from None
        folder = BACKUPS / (
            "team-auto-"
            + datetime.now().strftime("%Y%m%d-%H%M%S")
            + "-"
            + secrets.token_hex(3)
        )
        folder.mkdir(mode=0o700)
        dump = folder / "equipe.dump.partial"
        try:
            with dump.open("wb") as file:
                result = subprocess.run(
                    compose(
                        "exec",
                        "-T",
                        "team-postgres",
                        "pg_dump",
                        "-U",
                        "socialmei_team",
                        "-d",
                        "socialmei_team",
                        "-Fc",
                    ),
                    check=False,
                    stdout=file,
                    stderr=subprocess.PIPE,
                )
            if result.returncode or not dump.stat().st_size:
                raise RuntimeError(
                    "Dump da equipe falhou; nenhum backup foi marcado como concluído."
                )
            with dump.open("rb") as file:
                index = run(
                    compose("exec", "-T", "team-postgres", "pg_restore", "--list"),
                    stdin=file,
                )
            (folder / "conteudo.txt").write_bytes(index)
            with tarfile.open(
                folder / "configuracao.tar.gz.partial", "w:gz"
            ) as archive:
                archive.add(ROOT / ".env.team", arcname=".env.team")
                archive.add(PRIVATE, arcname="deploy/team/private")
            dump.rename(folder / "equipe.dump")
            (folder / "configuracao.tar.gz.partial").rename(
                folder / "configuracao.tar.gz"
            )
            receipt = {
                "formato": "socialmei-team-backup",
                "workspace": "team",
                "criado_em": datetime.now().astimezone().isoformat(),
                "sha256": {},
            }
            for path in folder.iterdir():
                if path.is_file():
                    with path.open("rb") as file:
                        receipt["sha256"][path.name] = hashlib.file_digest(
                            file, "sha256"
                        ).hexdigest()
            private_write(
                folder / "concluido.json", json.dumps(receipt, indent=2) + "\n"
            )
            print("Backup da equipe concluído e índice conferido:", folder)
            return folder
        except Exception:
            for path in folder.glob("*.partial"):
                path.unlink()
            raise


def schedule(enabled=True):
    environment()
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    previous = subprocess.run(
        ["crontab", "-l"], check=False, capture_output=True, text=True
    )
    if previous.returncode not in {0, 1} or (
        previous.returncode == 1 and "no crontab" not in previous.stderr.lower()
    ):
        raise RuntimeError("Não foi possível consultar o crontab do usuário.")
    lines = [
        line
        for line in previous.stdout.splitlines()
        if not line.rstrip().endswith(MARKER)
    ]
    if enabled:
        command = shlex.join(
            [sys.executable, str(ROOT / "tools/team-maintenance.py"), "backup"]
        )
        job = (
            "umask 077; "
            + command
            + " >> "
            + shlex.quote(str(BACKUPS / "team-backup.log"))
            + " 2>&1"
        )
        lines.append("30 2 * * * " + job.replace("%", "\\%") + " " + MARKER)
    updated = "\n".join(lines) + "\n"
    if updated == previous.stdout:
        print("Agendamento já está atualizado.")
        return
    private_write(
        BACKUPS / ("crontab-antes-" + secrets.token_hex(4) + ".txt"), previous.stdout
    )
    run(["crontab", "-"], input=updated.encode())
    print(
        "Backup diário às 02:30 no horário do servidor."
        if enabled
        else "Somente o agendamento da equipe foi removido."
    )


def prepare_n8n():
    values = environment()
    token = values.get("TEAM_N8N_READ_TOKEN")
    state_file = PRIVATE / "n8n-installation.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else None
    if state and any(
        not re.fullmatch(r"[A-Za-z0-9_-]{16}", str(state.get(k, "")))
        for k in ["credential_id", "workflow_id"]
    ):
        raise RuntimeError(
            "Identidades da integração inválidas; nenhum objeto foi importado."
        )
    if (
        state
        and state.get("instalado")
        and (
            not token
            or hashlib.sha256(token.encode()).hexdigest() != state.get("token_sha256")
        )
    ):
        raise RuntimeError(
            "Credencial técnica mudou depois da importação. Pare e revise a conexão."
        )
    if token and not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
        raise RuntimeError(
            "Credencial técnica existente inválida; não foi substituída."
        )
    if not token:
        token = secrets.token_urlsafe(48)
        env_file = ROOT / ".env.team"
        previous = env_file.read_text()
        if re.search(r"(?m)^TEAM_N8N_READ_TOKEN=", previous):
            previous = re.sub(
                r"(?m)^TEAM_N8N_READ_TOKEN=.*$",
                "TEAM_N8N_READ_TOKEN=" + token,
                previous,
            )
        else:
            previous = previous.rstrip() + "\nTEAM_N8N_READ_TOKEN=" + token + "\n"
        private_write(env_file, previous)
    if state:
        if state.get("instalado"):
            print("Integração já importada. Fluxo existente não foi sobrescrito.")
            return state
    else:
        state = {
            "credential_id": secrets.token_urlsafe(12),
            "workflow_id": secrets.token_urlsafe(12),
            "instalado": False,
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        }
        private_write(state_file, json.dumps(state))
    workflow = json.loads(
        (ROOT / "n8n-workflows/equipe/01-conferir-conexao.json").read_text()
    )
    workflow["id"] = state["workflow_id"]
    request = next(
        n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"
    )
    request["parameters"]["url"] = (
        "https://" + values["SOCIALMEI_TEAM_HOST"] + "/api/v1/integracoes/resumo"
    )
    request["credentials"] = {
        "httpHeaderAuth": {
            "id": state["credential_id"],
            "name": "SocialMEI equipe — leitura",
        }
    }
    credential = [
        {
            "id": state["credential_id"],
            "name": "SocialMEI equipe — leitura",
            "type": "httpHeaderAuth",
            "data": {"name": "Authorization", "value": "Bearer " + token},
        }
    ]
    private_write(PRIVATE / "n8n-credentials.json", json.dumps(credential))
    private_write(PRIVATE / "n8n-workflow.json", json.dumps(workflow))
    print("Integração preparada em arquivos privados. Nenhum segredo foi exibido.")
    return state


def connection():
    values = environment()
    token = values.get("TEAM_N8N_READ_TOKEN", "")
    if not token:
        raise RuntimeError("Prepare a integração primeiro.")
    request = Request(
        "https://" + values["SOCIALMEI_TEAM_HOST"] + "/api/v1/integracoes/resumo",
        headers={"Authorization": "Bearer " + token},
    )
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if payload.get("workspace") != "team" or payload.get("acesso") != "leitura":
        raise RuntimeError("Destino da integração não corresponde à equipe.")
    print(json.dumps(payload, ensure_ascii=False))
    return payload


def import_n8n():
    state = prepare_n8n()
    connection()
    if state.get("instalado"):
        return
    labels = json.loads(
        run(
            [
                "docker",
                "inspect",
                "socialmei-n8n",
                "--format",
                "{{json .Config.Labels}}",
            ]
        )
    )
    if (
        labels.get("com.docker.compose.project") != "socialmei"
        or labels.get("com.docker.compose.service") != "n8n"
    ):
        raise RuntimeError("Container n8n diferente da instalação esperada.")
    actual_env = dict(
        item.split("=", 1)
        for item in json.loads(
            run(
                [
                    "docker",
                    "inspect",
                    "socialmei-n8n",
                    "--format",
                    "{{json .Config.Env}}",
                ]
            )
        )
        if "=" in item
    )
    database_name = actual_env.get("DB_POSTGRESDB_DATABASE", "")
    if (
        actual_env.get("DB_TYPE") != "postgresdb"
        or actual_env.get("DB_POSTGRESDB_HOST") != "postgres"
        or not database_name
    ):
        raise RuntimeError(
            "Conexão PostgreSQL do n8n diferente da instalação esperada."
        )
    labels = json.loads(
        run(
            [
                "docker",
                "inspect",
                "socialmei-postgres",
                "--format",
                "{{json .Config.Labels}}",
            ]
        )
    )
    if (
        labels.get("com.docker.compose.project") != "socialmei"
        or labels.get("com.docker.compose.service") != "postgres"
    ):
        raise RuntimeError("Banco n8n diferente da instalação esperada.")
    old_root = ROOT.parent / "socialmei"
    if not (old_root / ".env").is_file():
        raise RuntimeError("Configuração do n8n não encontrada para backup.")
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder = BACKUPS / ("n8n-antes-importacao-" + secrets.token_hex(4))
    folder.mkdir(mode=0o700)
    if actual_env.get("N8N_ENCRYPTION_KEY"):
        private_write(
            folder / "n8n-encryption-key.txt", actual_env["N8N_ENCRYPTION_KEY"] + "\n"
        )
    else:
        key_config = run(
            ["docker", "exec", "socialmei-n8n", "cat", "/home/node/.n8n/config"]
        )
        if not json.loads(key_config).get("encryptionKey"):
            raise RuntimeError(
                "Chave de recuperação do n8n ausente. Importação interrompida."
            )
        private_write(folder / "n8n-config.json", key_config.decode())
    backup_file = folder / "postgres.dump"
    with backup_file.open("wb") as file:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "socialmei-postgres",
                "sh",
                "-c",
                'exec pg_dump -U "$POSTGRES_USER" -d "$1" -Fc',
                "sh",
                database_name,
            ],
            check=False,
            stdout=file,
            stderr=subprocess.PIPE,
        )
    if result.returncode or not backup_file.stat().st_size:
        backup_file.unlink(missing_ok=True)
        raise RuntimeError("Backup do banco n8n falhou. Nenhum fluxo foi importado.")
    with backup_file.open("rb") as file:
        run(
            ["docker", "exec", "-i", "socialmei-postgres", "pg_restore", "--list"],
            stdin=file,
        )
    with tarfile.open(folder / "configuracao.tar.gz", "w:gz") as archive:
        for name in [".env", "compose.yaml", "compose.override.yaml", "Caddyfile"]:
            if (old_root / name).is_file():
                archive.add(old_root / name, arcname=name)
    temp = "/tmp/socialmei-read-" + secrets.token_hex(8)
    run(["docker", "exec", "socialmei-n8n", "mkdir", "-m", "700", temp])
    try:
        for filename, command in [
            ("n8n-credentials.json", "import:credentials"),
            ("n8n-workflow.json", "import:workflow"),
        ]:
            remote = temp + "/" + filename
            run(
                [
                    "docker",
                    "exec",
                    "-i",
                    "socialmei-n8n",
                    "sh",
                    "-c",
                    'umask 077; cat > "$1"',
                    "sh",
                    remote,
                ],
                input=(PRIVATE / filename).read_bytes(),
            )
            run(
                ["docker", "exec", "socialmei-n8n", "n8n", command, "--input=" + remote]
            )
        state["instalado"] = True
        private_write(PRIVATE / "n8n-installation.json", json.dumps(state))
        (PRIVATE / "n8n-credentials.json").unlink()
        print(
            "Credencial e fluxo de conferência importados. Fluxo inativo, sem mensagens ou alterações no CRM."
        )
    finally:
        run(["docker", "exec", "socialmei-n8n", "rm", "-rf", temp])


def doctor():
    environment()
    run(compose("config", "--quiet"))
    print(run(compose("ps", "--all")).decode())
    script = "import json; from shared_data import database_health_payload; print(json.dumps(database_health_payload()))"
    print(
        run(compose("exec", "-T", "team-api", "python", "-c", script)).decode().strip()
    )
    if environment().get("TEAM_N8N_READ_TOKEN"):
        connection()
    print("Diagnóstico concluído sem alterar registros.")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "doctor",
            "backup",
            "enable-backup",
            "disable-backup",
            "prepare-n8n",
            "check-n8n",
            "import-n8n",
        ],
    )
    command = parser.parse_args().command
    actions = {
        "doctor": doctor,
        "backup": backup,
        "enable-backup": schedule,
        "disable-backup": lambda: schedule(False),
        "prepare-n8n": prepare_n8n,
        "check-n8n": connection,
        "import-n8n": import_n8n,
    }
    try:
        with (PRIVATE / ".maintenance.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Outra manutenção já está em andamento.") from None
            actions[command]()
    except (
        RuntimeError,
        OSError,
        ValueError,
        tarfile.TarError,
        subprocess.SubprocessError,
    ) as error:
        # No command output, environment values or credential bodies in failures.
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(
            "Manutenção não concluída: " + detail + ". Segredos não foram exibidos.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
