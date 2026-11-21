"""Read-only supervision of persisted Direct work; never builds a provider runtime."""
from psycopg.rows import dict_row
from database import connect


def pending(workspace, start):
    if type(workspace) is not int or workspace <= 0 or start.tzinfo is None:
        raise ValueError('Invalid observer scope')
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute("SET LOCAL statement_timeout='5s'")
        row = conn.execute(
            "SELECT count(*) AS pending_count,max(m.id) AS latest_pending_message_id "
            "FROM socialmei.me_messages m JOIN socialmei.ig_meta_ingress_events e "
            "ON e.workspace_id=m.workspace_id AND e.message_id=m.id "
            "JOIN socialmei.ig_meta_connections c ON c.workspace_id=e.workspace_id AND c.id=e.connection_id "
            "AND c.external_account_id=e.external_account_id "
            "WHERE m.workspace_id=%s AND m.origin='instagram' AND e.kind='message' AND e.status='processed' "
            "AND e.received_at>=%s AND m.occurred_at>=%s "
            "AND NOT EXISTS (SELECT 1 FROM socialmei.ig_menu_replies r "
            "WHERE r.workspace_id=m.workspace_id AND r.source_message_id=m.id)",
            (workspace, start, start)).fetchone()
    return dict(row)


def checkpoint(previous, workspace, start, counts):
    if previous is not None and (
            previous.get('workspace_id') != workspace or previous.get('mode') != 'observe'
            or previous.get('start') != start.isoformat() or previous.get('status') != 'running'):
        raise RuntimeError('Observer checkpoint requires review')
    return {'workspace_id': workspace, 'mode': 'observe', 'start': start.isoformat(),
            'status': 'running', 'in_flight': False, 'send_enabled': False,
            'pending_count': counts['pending_count'],
            'latest_pending_message_id': counts['latest_pending_message_id']}
