"""Apply the external Python runner to the audited legacy n8n stack."""

import argparse
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import tarfile
import time

ROOT = Path("/home/ubuntu/socialmei")
BACKUP = None
PRIVATE = Path("/home/ubuntu/.config/socialmei/n8n-python")
RUNNER = "n8nio/runners:2.40.5@sha256:de290741c2c747a9af5c1490168b687db276149ec1a8bc06336877d213eb97d2"
changed = False


def run(*args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True)
    if result.returncode:
        raise RuntimeError(
            "Comando não concluído: " + args[0] + ". Detalhes privados não exibidos."
        )
    return result.stdout


def inspect(name):
    return json.loads(run("docker", "inspect", name))[0]


def environment(container):
    return dict(
        item.split("=", 1) for item in container["Config"]["Env"] if "=" in item
    )


def containers():
    ids = run("docker", "ps", "-aq").decode().split()
    data = json.loads(run("docker", "inspect", *ids))
    return {c["Name"]: (c["Id"], c["Image"], c["State"]["StartedAt"]) for c in data}


def main():
    global changed
    os.umask(0o077)
    run("sha256sum", "--check", str(BACKUP / "SHA256SUMS"))
    saved = json.loads((BACKUP / "runtime-n8n.json").read_text())[0]
    current = inspect("socialmei-n8n")
    assert (
        current["Id"] == saved["Id"] and current["Image"] == saved["Image"]
    ), "O n8n mudou desde o backup."
    assert current["State"]["Running"], "O n8n não está em execução."
    assert (
        run("docker", "exec", "socialmei-n8n", "n8n", "--version").decode().strip()
        == "2.40.5"
    ), "Versão diferente de 2.40.5."
    assert current["Config"]["Labels"][
        "com.docker.compose.project.config_files"
    ] == str(ROOT / "compose.yaml"), "Compose diferente do conferido."
    assert set(current["NetworkSettings"]["Networks"]) == {
        "socialmei_default"
    }, "A rede mudou."
    assert (
        len(current["Mounts"]) == 1
        and current["Mounts"][0].get("Name") == "socialmei_n8n_data"
    ), "Volumes diferentes."
    with tarfile.open(BACKUP / "configuracao.tar.gz") as archive:
        for name in ("compose.yaml", "compose.override.yaml", "Caddyfile", ".env"):
            assert archive.extractfile(name).read() == (ROOT / name).read_bytes(), (
                "Arquivo mudou desde o backup: " + name
            )
    before = {
        line.split("|")[0]: tuple(line.split("|")[1:])
        for line in (BACKUP / "containers-before.txt").read_text().splitlines()
    }
    assert (
        containers() == before
    ), "Containers mudaram desde o backup; revisar antes de aplicar."
    assert (
        "/socialmei-python-runners" not in before
    ), "Já existe executor com esse nome."
    compose = [
        "docker",
        "compose",
        "-p",
        "socialmei",
        "--project-directory",
        str(ROOT),
        "-f",
        str(ROOT / "compose.yaml"),
    ]
    base = json.loads(run(*compose, "config", "--format", "json"))
    assert "python-runners" not in base["services"], "Já existe serviço de executor."
    original_env = environment(current)
    for key, value in base["services"]["n8n"].get("environment", {}).items():
        expected = None if value is None else str(value)
        assert original_env.get(key) == expected, (
            "Configuração diverge do runtime em " + key
        )
    inspect(RUNNER)
    token = secrets.token_hex(32)
    runner_env = {
        "N8N_RUNNERS_MODE": "external",
        "N8N_RUNNERS_BROKER_LISTEN_ADDRESS": "0.0.0.0",
        "N8N_RUNNERS_AUTH_TOKEN": token,
        "N8N_NATIVE_PYTHON_RUNNER": "true",
    }
    override = {
        "services": {
            "n8n": {
                "image": current["Image"],
                "pull_policy": "never",
                "environment": runner_env,
                "networks": ["default", "python_runners"],
            },
            "python-runners": {
                "container_name": "socialmei-python-runners",
                "image": RUNNER,
                "pull_policy": "never",
                "restart": "unless-stopped",
                "environment": {
                    "N8N_RUNNERS_TASK_BROKER_URI": "http://n8n:5679",
                    "N8N_RUNNERS_AUTH_TOKEN": token,
                },
                "networks": ["python_runners"],
                "depends_on": ["n8n"],
            },
        },
        "networks": {"python_runners": {"internal": True}},
    }
    PRIVATE.mkdir(parents=True, mode=0o700, exist_ok=False)
    override_file = PRIVATE / "compose.python-runners.json"
    with override_file.open("x") as target:
        json.dump(override, target, indent=2)
    (BACKUP / "compose.python-runners.snapshot.json").write_bytes(
        override_file.read_bytes()
    )
    rollback_file = BACKUP / "compose.rollback.json"
    with rollback_file.open("x") as target:
        json.dump(
            {
                "services": {
                    "n8n": {
                        "image": current["Image"],
                        "pull_policy": "never",
                        "environment": original_env,
                        "networks": ["default"],
                    }
                }
            },
            target,
        )
    rollback = compose + [
        "-f",
        str(rollback_file),
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "--pull",
        "never",
        "n8n",
    ]
    (BACKUP / "rollback.sh").write_text(
        "#!/bin/bash\nset -e\n" + shlex.join(rollback) + "\n"
    )
    operation = compose + ["-f", str(override_file)]
    run(*operation, "config", "--quiet")
    resolved = json.loads(run(*operation, "config", "--format", "json"))
    old = dict(base["services"]["n8n"])
    new = dict(resolved["services"]["n8n"])
    old_env = old.pop("environment", {})
    new_env = new.pop("environment", {})
    assert {key: value for key, value in new_env.items() if key not in runner_env} == {
        key: value for key, value in old_env.items() if key not in runner_env
    }, "Ambiente adicional alterado."
    for field in ("image", "pull_policy", "networks"):
        old.pop(field, None)
        new.pop(field, None)
    assert old == new, "O Compose alteraria outras opções do n8n."
    assert not resolved["services"]["python-runners"].get(
        "ports"
    ), "Executor não pode publicar portas."
    assert containers() == before, "Containers mudaram durante a preparação."
    print(
        "Configuração validada. Recriando somente o n8n com a mesma imagem e o mesmo volume...",
        flush=True,
    )
    changed = True
    run(*operation, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "n8n")
    run(
        *operation,
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "--pull",
        "never",
        "python-runners"
    )
    healthy = False
    for attempt in range(30):
        check = subprocess.run(
            [
                "docker",
                "exec",
                "socialmei-n8n",
                "node",
                "-e",
                'fetch("http://127.0.0.1:5678/healthz").then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))',
            ],
            capture_output=True,
        )
        if check.returncode == 0:
            healthy = True
            break
        time.sleep(2)
    assert healthy, "O n8n ainda não respondeu à conferência de saúde."
    after = containers()
    for name, value in before.items():
        if name != "/socialmei-n8n":
            assert after.get(name) == value, "Outro container mudou: " + name
    assert set(after) - set(before) == {
        "/socialmei-python-runners"
    }, "Container adicional inesperado."
    updated = inspect("socialmei-n8n")
    assert (
        updated["Image"] == saved["Image"] and updated["Mounts"] == saved["Mounts"]
    ), "Imagem ou volume não corresponde ao original."
    assert environment(updated) == {
        **original_env,
        **runner_env,
    }, "Ambiente final diferente do previsto."
    assert inspect("socialmei-python-runners")["State"][
        "Running"
    ], "Executor não está em execução."
    (BACKUP / "aplicado.json").write_text(
        json.dumps(
            {"n8n": updated["Id"], "executor": after["/socialmei-python-runners"][0]}
        )
    )
    print("APLICAÇÃO CONFERIDA: n8n saudável e executor iniciado.")
    print(
        "Imagem, volume e variáveis originais preservados; demais containers sem reinício."
    )
    print("Configuração ativa e token guardados privadamente em:", PRIVATE)
    print("Backup e recuperação guardados em:", BACKUP)
    print(
        "Nenhum restore ou migration solicitado; nenhum workflow acionado manualmente. Falta testar um nó Python no painel."
    )


def cli():
    global BACKUP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Autoriza a recriação somente do n8n e o início do executor.",
    )
    args = parser.parse_args()
    if not args.apply:
        parser.error("Informe --apply apenas para executar a aplicação autorizada.")
    try:
        BACKUP = args.backup.resolve(strict=True)
        assert BACKUP.parent == Path(
            "/home/ubuntu/socialmei-backups"
        ), "Pasta fora do diretório de backups conferido."
        assert BACKUP.name.startswith("n8n-python-"), "Nome de backup não reconhecido."
        assert (
            BACKUP.stat().st_uid == os.geteuid()
        ), "O backup pertence a outro usuário."
        assert (
            BACKUP.stat().st_mode & 0o077 == 0
        ), "O diretório de backup precisa ser privado."
        main()
    except (AssertionError, RuntimeError, OSError, KeyError, ValueError) as error:
        print("ETAPA INTERROMPIDA:", error)
        print(
            "A troca de serviços foi iniciada."
            if changed
            else "Nenhum serviço foi reiniciado por este bloco."
        )
        print(
            "Envie esta saída. Não repita o bloco nem execute rollback sem orientação."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
