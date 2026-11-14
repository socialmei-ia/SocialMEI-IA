#!/usr/bin/env python3
"""Prepare NEW private Brevo settings only. No network, sends or service changes.

Run prepare interactively on the approved computer/server. Credentials are never
accepted as arguments, printed, interpolated by a shell or written in Git.
"""
import argparse
import base64
import csv
import getpass
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import warnings
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FIXED = {'SOCIALMEI_BREVO_HOST': 'smtp-relay.brevo.com', 'SOCIALMEI_BREVO_PORT': '587',
         'SOCIALMEI_BREVO_FROM': 'servermeiiafacepe@gmail.com',
         'SOCIALMEI_IDENTITY_MODE': 'disabled', 'SOCIALMEI_RECOVERY_MODE': 'disabled'}
KEYS = set(FIXED) | {'SOCIALMEI_BREVO_USER', 'SOCIALMEI_BREVO_PASSWORD'}
SPEC = importlib.util.spec_from_file_location('brevo_release_gate', ROOT / 'tools/release040-preflight.py')
release_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_gate)


def require(ok):
    if not ok:
        raise ValueError('private_brevo_precondition_failed')


def plain_path(path):
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)()
                and not getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def target(path, suffixes=('.env',)):
    path = Path(os.path.abspath(path.expanduser()))
    plain_path(path)
    resolved = path.resolve()
    require(path.suffix in suffixes and ROOT not in path.parents and path != ROOT)
    require(ROOT.resolve() not in resolved.parents and resolved != ROOT.resolve())
    require(not any((item / '.git').exists() for item in (*path.parents, *resolved.parents)))
    return path


def sid():
    value = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True,
                           text=True, timeout=10, check=True).stdout
    identity = next(csv.reader(io.StringIO(value)))[1]
    require(re.fullmatch(r'S-1-[0-9-]+', identity) is not None)
    return identity


def windows_private(path, *, directory, apply):
    identity = sid()
    if apply:
        grant = '*' + identity + (':(OI)(CI)F' if directory else ':F')
        for command in (['icacls', str(path), '/setowner', '*' + identity],
                        ['icacls', str(path), '/inheritance:r', '/grant:r', grant],
                        ['icacls', str(path), '/remove:g', '*S-1-5-18', '*S-1-5-32-544']):
            subprocess.run(command, capture_output=True, check=True, timeout=10)
    script = """
$a=Get-Acl -LiteralPath $env:SOCIALMEI_PRIVATE_TARGET
$s=$env:SOCIALMEI_PRIVATE_SID
$r=@($a.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]))
if($a.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -ne $s){exit 1}
if(-not $a.AreAccessRulesProtected -or $r.Count -eq 0){exit 1}
if(@($r|Where-Object {$_.IdentityReference.Value -ne $s -or $_.AccessControlType -ne 'Allow'}).Count){exit 1}
exit 0
"""
    encoded = base64.b64encode(script.encode('utf-16le')).decode()
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                   env={**os.environ, 'SOCIALMEI_PRIVATE_TARGET': str(path),
                        'SOCIALMEI_PRIVATE_SID': identity}, capture_output=True, check=True, timeout=10)


def private(path, *, directory=False, apply=False):
    plain_path(path)
    require(path.is_dir() if directory else path.is_file())
    if os.name == 'nt':
        windows_private(path, directory=directory, apply=apply)
    else:
        value = path.stat()
        require(value.st_uid == os.getuid() and stat.S_IMODE(value.st_mode) & 0o077 == 0)


def content(user, password):
    for value in (user, password):
        require(isinstance(value, str) and 0 < len(value) <= 4096 and value == value.strip()
                and all(32 <= ord(character) <= 126 for character in value))
    # Compose --env-file double quotes and escaped dollars. Never shell-source this file.
    data = {**FIXED, 'SOCIALMEI_BREVO_USER': user, 'SOCIALMEI_BREVO_PASSWORD': password}
    return ''.join(key + '=' + json.dumps(value).replace('$', '$$') + '\n' for key, value in data.items())


def parse_content(value):
    data = {}
    for line in value.splitlines():
        key, separator, encoded = line.partition('=')
        require(separator and key in KEYS and key not in data)
        decoded = json.loads(encoded)
        require(isinstance(decoded, str))
        data[key] = decoded.replace('$$', '$')
    require(set(data) == KEYS and all(data.get(key) == value for key, value in FIXED.items()))
    content(data['SOCIALMEI_BREVO_USER'], data['SOCIALMEI_BREVO_PASSWORD'])
    return data


def prepare(path, *, hidden=None):
    require(sys.stdin.isatty() and sys.stderr.isatty())
    path = target(path)
    require(not path.exists() and path.parent.parent.is_dir())
    if not path.parent.exists():
        path.parent.mkdir(mode=0o700)
        private(path.parent, directory=True, apply=True)
    else:
        # Never change an existing directory's permissions or credentials.
        private(path.parent, directory=True)
    reader = hidden or getpass.getpass
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        user = reader('Login SMTP Brevo (oculto): ')
        password = reader('Chave SMTP Brevo (oculta): ')
        confirm = reader('Confirme a chave SMTP (oculta): ')
    require(password == confirm)
    value = content(user, password)
    temporary = path.with_name('.brevo-' + secrets.token_hex(12) + '.partial')
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            private(temporary, apply=True)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        # Atomic no-clobber publication: never replace a file created concurrently.
        os.link(temporary, path)
        private(path)
        if os.name != 'nt':
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {'private_config_created': True, 'smtp_port': 587, 'tls': 'STARTTLS',
            'modes_disabled': True, 'sent': False, 'services_changed': False}


def audit_model(data, model):
    require(isinstance(model, dict))
    services = model.get('services', {})
    host = services.get('team-gateway', {}).get('environment', {}).get('SOCIALMEI_TEAM_HOST', '')
    require(isinstance(host, str))
    primary = urlsplit('https://' + host)
    require(primary.hostname and primary.netloc == host and not primary.username and not primary.password
            and not primary.path and not primary.query and not primary.fragment)
    origin = 'https://' + host
    database = None
    for name in ('team-api', 'team-recovery-worker', 'team-identity-worker'):
        service = services.get(name, {})
        values = service.get('environment', {})
        for field in ('HOST', 'PORT', 'USER', 'PASSWORD', 'FROM'):
            # Serialized Compose output escapes literal dollars for reuse.
            expected = data['SOCIALMEI_BREVO_' + field].replace('$', '$$')
            require(values.get('SOCIALMEI_SMTP_' + field) == expected)
        require(values.get('SOCIALMEI_IDENTITY_MODE') == 'disabled'
                and values.get('SOCIALMEI_RECOVERY_MODE') == 'disabled'
                and values.get('SOCIALMEI_AUTH_ENABLED') == 'true'
                and values.get('SOCIALMEI_AUTH_ORIGIN') == origin)
        connection = release_gate.database_identity(values)
        if database is None:
            database = connection
        require(connection == database)
        if name != 'team-api':
            require(service.get('profiles'))
    require(services['team-api']['environment'].get('SOCIALMEI_PUBLIC_BOOKING_ENABLED') == 'false')
    return {'three_consumers_match_private_config': True, 'same_database_configuration': True,
            'primary_origin_matches_gateway': True, 'delivery_disabled': True, 'sent': False}


def inspect(path, compose_json=None):
    path = target(path)
    private(path.parent, directory=True)
    private(path)
    require(path.stat().st_size < 16384)
    data = parse_content(path.read_text(encoding='utf-8'))
    result = {'private_config_valid': True, 'provider': 'Brevo', 'port': 587,
            'tls': 'STARTTLS', 'modes_disabled': True, 'sent': False,
            'application_activated': False}
    if compose_json is not None:
        compose_json = target(compose_json, ('.json',))
        private(compose_json.parent, directory=True)
        private(compose_json)
        require(compose_json.stat().st_size < 8 * 1024**2)
        result.update(audit_model(data, json.loads(compose_json.read_text(encoding='utf-8-sig'))))
    return result


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Argumentos inválidos; credenciais devem ser digitadas somente no prompt oculto.\n')


def main(argv=None):
    parser = PrivateParser(description=__doc__)
    parser.add_argument('stage', choices=('plan', 'prepare', 'inspect'), nargs='?', default='plan')
    parser.add_argument('--file', type=Path)
    parser.add_argument('--compose-json', type=Path, help='Protected rendered config; inspect only, never print this file')
    args = parser.parse_args(argv)
    try:
        if args.stage == 'plan':
            result = {'mode': 'plan', 'credentials_required_via_hidden_terminal_only': True,
                      'network_calls': False, 'workers_enabled': False,
                      'compose_override': 'compose.team-brevo.yaml', 'compose_minimum': '2.24.4'}
        else:
            require(args.file is not None)
            require(args.stage == 'inspect' or args.compose_json is None)
            result = prepare(args.file) if args.stage == 'prepare' else inspect(args.file, args.compose_json)
        print(json.dumps(result))
    except (Exception, KeyboardInterrupt):
        raise SystemExit('Brevo privado não preparado; verifique terminal, caminho novo e permissões. Nenhum envio autorizado.') from None


if __name__ == '__main__':
    main()
