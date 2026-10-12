"""Private terminal account provisioning and recovery; never accepts passwords as flags."""

import argparse
import getpass
import sys

import psycopg
from account_auth import hash_password, normalize_email
from fastapi import HTTPException

from database import connect


def ask_password():
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Use um terminal interativo para informar a senha sem exibi-la."
        )
    password = getpass.getpass("Senha (12 a 128 caracteres, não será exibida): ")
    if password != getpass.getpass("Repita a senha: "):
        raise ValueError("Senhas diferentes.")
    return hash_password(password)


def create_admin(address, name, hashed):
    address = normalize_email(address)
    if not name.strip() or len(name) > 160:
        raise ValueError("Nome inválido.")
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(72426002)")
        if conn.execute(
            "SELECT 1 FROM socialmei.auth_credenciais WHERE administrador_plataforma LIMIT 1"
        ).fetchone():
            raise RuntimeError(
                "Administrador já configurado. Use recuperação, não recrie a conta."
            )
        if conn.execute(
            "SELECT 1 FROM socialmei.users WHERE LOWER(BTRIM(email))=%s", (address,)
        ).fetchone():
            raise RuntimeError(
                "E-mail já cadastrado. Não foi promovido automaticamente."
            )
        workspace = conn.execute(
            "SELECT id FROM socialmei.workspaces WHERE slug='team'"
        ).fetchone()
        if not workspace:
            raise RuntimeError(
                "Workspace team ausente; confira a instalação antes de continuar."
            )
        user_id = conn.execute(
            "INSERT INTO socialmei.users (email,nome) VALUES (%s,%s) RETURNING id",
            (address, name.strip()),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO socialmei.auth_credenciais (user_id,senha_hash,administrador_plataforma) VALUES (%s,%s,true)",
            (user_id, hashed),
        )
        conn.execute(
            "INSERT INTO socialmei.workspace_members (workspace_id,user_id,role) VALUES (%s,%s,'owner')",
            (workspace[0], user_id),
        )
        conn.execute(
            "INSERT INTO socialmei.auth_auditoria (user_id,acao) VALUES (%s,'admin_criado')",
            (user_id,),
        )
    return user_id


def reset_password(address, hashed):
    address = normalize_email(address)
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(72426002)")
        user = conn.execute(
            "SELECT u.id FROM socialmei.users u JOIN socialmei.auth_credenciais c ON c.user_id=u.id WHERE LOWER(BTRIM(u.email))=%s FOR UPDATE OF c",
            (address,),
        ).fetchone()
        if not user:
            raise RuntimeError("Conta não encontrada.")
        conn.execute(
            "UPDATE socialmei.auth_credenciais SET senha_hash=%s,senha_alterada_em=NOW() WHERE user_id=%s",
            (hashed, user[0]),
        )
        conn.execute(
            "UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE user_id=%s AND revogada_em IS NULL",
            (user[0],),
        )
        conn.execute(
            "INSERT INTO socialmei.auth_auditoria (alvo_user_id,acao) VALUES (%s,'senha_recuperada_cli')",
            (user[0],),
        )


def enable_user(address):
    address = normalize_email(address)
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(72426002)")
        row = conn.execute(
            "SELECT u.id FROM socialmei.users u JOIN socialmei.auth_credenciais c ON c.user_id=u.id WHERE LOWER(BTRIM(u.email))=%s FOR UPDATE OF c",
            (address,),
        ).fetchone()
        if not row:
            raise RuntimeError("Conta não encontrada.")
        conn.execute(
            "UPDATE socialmei.auth_credenciais SET ativo=true WHERE user_id=%s",
            (row[0],),
        )
        # Previously revoked sessions remain revoked, requiring a new login.
        conn.execute(
            "INSERT INTO socialmei.auth_auditoria (alvo_user_id,acao) VALUES (%s,'conta_reativada_cli')",
            (row[0],),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["create-admin", "reset-password", "enable-user"]
    )
    args = parser.parse_args()
    try:
        if not sys.stdin.isatty():
            raise RuntimeError("Use um terminal interativo para administrar contas.")
        address = normalize_email(input("E-mail da conta: "))
        if args.command == "enable-user":
            enable_user(address)
            print("Conta reativada. É necessário entrar novamente.")
            return
        name = input("Seu nome: ").strip() if args.command == "create-admin" else ""
        hashed = ask_password()
        if args.command == "create-admin":
            create_admin(address, name, hashed)
            print("Administrador criado e vinculado ao workspace team existente.")
        else:
            reset_password(address, hashed)
            print("Senha redefinida; todas as sessões dessa conta foram revogadas.")
    except (RuntimeError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    except psycopg.Error:
        parser.exit(
            1,
            "Operação não concluída. Confira banco/migrations; nenhuma senha foi exibida.\n",
        )
    except HTTPException:
        parser.exit(1, "Operação temporariamente indisponível. Tente novamente.\n")


if __name__ == "__main__":
    main()
