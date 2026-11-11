"""Resolve only persisted, OAuth-bound inbound contacts through Meta's profile API."""
import hashlib

from psycopg.rows import dict_row
from database import connect
from instagram_meta_adapter import ProviderError
from instagram_token_vault import TokenBinding, VaultError


def contact_label(profile, contact_ref):
    if profile.get('username'):
        return '@' + profile['username']
    if profile.get('name'):
        return profile['name']
    return 'Contato do Instagram · ' + hashlib.sha256(contact_ref.encode()).hexdigest()[:6].upper()


def refresh_contacts(runtime, workspace, *, limit=10):
    if type(workspace) is not int or workspace < 1 or not 1 <= limit <= 10 or runtime.status != 'configured':
        raise ValueError('Invalid contact lookup scope')
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT DISTINCT ON (v.id) v.id,v.contact_ref,c.id AS connection_id,c.external_account_id,c.encrypted_token "
            "FROM socialmei.me_conversations v "
            "JOIN socialmei.ig_meta_ingress_events e ON e.workspace_id=v.workspace_id "
            "JOIN socialmei.me_messages m ON m.workspace_id=e.workspace_id AND m.id=e.message_id AND m.conversation_id=v.id "
            "JOIN socialmei.ig_meta_connections c ON c.workspace_id=e.workspace_id AND c.id=e.connection_id "
            "AND c.external_account_id=e.external_account_id "
            "WHERE v.workspace_id=%s AND v.origin='instagram' AND m.origin='instagram' "
            "AND e.kind='message' AND e.status='processed' AND v.account_ref='instagram:' || c.external_account_id "
            "AND c.status='connected' AND c.expires_at>NOW() AND v.contact_name='Contato do Instagram' "
            "ORDER BY v.id,e.received_at DESC LIMIT %s", (workspace, limit),
        ).fetchall()
    updated = available = denied = 0
    for row in rows:
        profile = {}
        try:
            token = runtime.direct.vault.open(row['encrypted_token'], TokenBinding(
                workspace, row['connection_id'], row['external_account_id']))
            profile = runtime.direct.adapter.contact_profile(token, row['contact_ref'].split(':')[1])
            available += bool(profile)
        except (ProviderError, VaultError):
            denied += 1
        label = contact_label(profile, row['contact_ref'])
        with connect() as conn:
            result = conn.execute(
                "UPDATE socialmei.me_conversations SET contact_name=%s,revision=revision+1 "
                "WHERE workspace_id=%s AND id=%s AND origin='instagram' AND account_ref=%s "
                "AND contact_ref=%s AND contact_name='Contato do Instagram'",
                (label, workspace, row['id'], 'instagram:' + row['external_account_id'], row['contact_ref']),
            )
            updated += result.rowcount
    return {'updated': updated, 'official_profile_available': available, 'unavailable': denied}
