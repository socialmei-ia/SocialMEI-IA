"""Instagram Direct booking choices using confirmed reply history; no schema change or sender."""
import base64
import hashlib
import json
import zlib
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

import channel_booking as booking
import channel_booking_flow as flow

MARKER = '\n\nRef. agendamento: '
MAX_OUTPUT_BYTES = 1000
MAX_DECODED_BYTES = 7000
REPLY_TTL = timedelta(minutes=10)
CHOICE_IDS = {'1', '2', '3', '6', '7'}
STEPS = {'services', 'resources', 'days', 'slots', 'review_ref', 'confirm_ref'}


def _offer_details(offer):
    fields = ('service_id', 'resource_id', 'service_name', 'resource_name',
              'duration_minutes', 'price', 'scheduled_for', 'ends_at')
    raw = json.dumps({field: offer.get(field) for field in fields},
                     sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _snapshot_target(target, selected):
    if target.get('route') != 'booking':
        return None
    step = target.get('step')
    if step not in {'review', 'confirm'}:
        return {key: value for key, value in target.items() if key != 'route'}
    # Signed offer tokens are never embedded in customer-visible text.
    # We persist the exact slot reference and regenerate its signature on
    # the next confirmed inbound message, after checking availability again.
    expected = 'slots' if step == 'review' else 'review'
    if selected.get('step') != expected:
        raise ValueError('Booking offer has no originating slot page')
    offer = target['offer'] if step == 'review' else selected['offer']
    snapshot = {
        'step': 'review_ref' if step == 'review' else 'confirm_ref',
        'service_id': offer['service_id'],
        'resource_id': offer['resource_id'],
        'day': selected['day'],
        'page': selected.get('page', 0),
        'scheduled_for': offer['scheduled_for'],
    }
    if step == 'confirm':
        snapshot['details'] = _offer_details(offer)
    return snapshot


def render(result, selected):
    """Format a menu with a compact, visible reference for subsequent choices.

    The reference is read back exclusively from this application's confirmed
    outbound row, never from a customer-supplied message.
    """
    choices = result.get('choices', [])
    lines = [result['text']]
    pointers = []
    for item in choices:
        lines.append(str(item['id']) + ' - ' + item['title'])
        if item['id'] in CHOICE_IDS:
            target = _snapshot_target(item.get('target', {}), selected)
            if target is not None:
                pointers.append([item['id'], target])
    text = '\n'.join(lines)
    if pointers:
        raw = json.dumps(pointers, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        packed = base64.urlsafe_b64encode(zlib.compress(raw, level=9)).decode('ascii').rstrip('=')
        text += MARKER + packed
    if (not text.strip() or len(text.encode('utf-8')) > MAX_OUTPUT_BYTES
            or any(ord(char) < 32 and char not in '\n\r\t' for char in text)):
        raise ValueError('Booking reply cannot fit the Instagram message contract')
    return text


def public_text(text):
    """Strip only our trailing persisted menu reference before provider send/UI."""
    if not isinstance(text, str):
        return ""
    if MARKER not in text:
        return text
    visible, _ = text.rsplit(MARKER, 1)
    return visible


def _decode_reference(text):
    if not isinstance(text, str) or MARKER not in text:
        return []
    encoded = text.rsplit(MARKER, 1)[1].strip()
    if not 1 <= len(encoded) <= MAX_OUTPUT_BYTES:
        return []
    try:
        packed = base64.b64decode(encoded + '=' * (-len(encoded) % 4),
                                  altchars=b'-_', validate=True)
        decompressor = zlib.decompressobj()
        raw = decompressor.decompress(packed, MAX_DECODED_BYTES + 1)
        if (len(raw) > MAX_DECODED_BYTES or not decompressor.eof
                or decompressor.unconsumed_tail or decompressor.unused_data):
            return []
        data = json.loads(raw)
    except (ValueError, TypeError, UnicodeError, zlib.error, OverflowError):
        return []
    if not isinstance(data, list) or len(data) > 8:
        return []
    choices = []
    for value in data:
        if (not isinstance(value, list) or len(value) != 2
                or not isinstance(value[0], str) or value[0] not in CHOICE_IDS
                or not isinstance(value[1], dict)
                or not isinstance(value[1].get('step'), str)
                or value[1]['step'] not in STEPS
                or any(identifier == value[0] for identifier, _ in choices)):
            return []
        choices.append((value[0], {**value[1], 'route': 'booking'}))
    return choices


def _recent_choices(row):
    if not row or row.get('status') != 'confirmed':
        return []
    created = row.get('created_at')
    now = datetime.now(timezone.utc)
    if (not isinstance(created, datetime) or created.tzinfo is None
            or not now - REPLY_TTL <= created <= now + timedelta(seconds=30)):
        return []
    return _decode_reference(row.get('text'))


def _review_offer(conn, workspace, message, target):
    context = (workspace, message['conversation_id'], message['id'], 'instagram')
    key = booking.signing_key_for_context(conn, *context)
    result = booking.slots_for_message(*context, target['service_id'],
        target['resource_id'], target['day'], key, page=target['page'],
        connection=conn)
    offer = next((item for item in result['items']
                  if item['scheduled_for'] == target['scheduled_for']), None)
    if offer is None:
        raise HTTPException(409, 'O horário mudou. Consulte a disponibilidade novamente.')
    if target['step'] == 'confirm_ref' and target.get('details') != _offer_details(offer):
        raise HTTPException(409, 'Os detalhes do atendimento mudaram. Consulte os horários novamente antes de confirmar.')
    return {'route': 'booking', 'step': 'review', 'offer': offer,
            'day': target['day'], 'page': target['page']}


def respond(conn, workspace, message):
    """Return (state, result, selection) or None for the existing Instagram menu.

    Must be called inside the Instagram menu's existing account/workspace lock,
    after the source and human-pause checks and before any provider dispatch.
    """
    value = message['text'].strip().casefold()
    if value in flow.EXIT:
        return None
    latest = conn.execute(
        'SELECT text,status,created_at FROM socialmei.ig_menu_replies '
        'WHERE workspace_id=%s AND conversation_id=%s '
        'ORDER BY created_at DESC,id DESC LIMIT 1',
        (workspace, message['conversation_id']),
    ).fetchone()
    choices = _recent_choices(latest)
    selected = next((target for number, target in choices if number == value), None)
    if selected is None:
        if value in flow.START:
            selected = {'route': 'booking', 'step': 'services'}
        elif not choices:
            return None
        else:
            response = flow.response('booking_invalid_choice',
                'Escolha uma opção válida ou comece o agendamento novamente.',
                [flow.option('6', 'Recomeçar agendamento', 'services'),
                 *flow.navigation()], False)
            return response[0], response[1], {'step': 'services'}
    try:
        if selected.get('step') in {'review_ref', 'confirm_ref'}:
            confirming = selected['step'] == 'confirm_ref'
            selected = _review_offer(conn, workspace, message, selected)
            if confirming:
                selected = {'route': 'booking', 'step': 'confirm',
                            'confirmation': selected['offer']['confirmation']}
        state, result = flow.advance(conn, {'workspace_id': workspace}, message,
                                     selected, False, origin='instagram')
        return state, result, selected
    except HTTPException as error:
        if error.status_code not in {409, 422, 503}:
            raise
        details = str(error.detail)
        handoff = error.status_code == 503 or 'associar seu cadastro' in details
        state, result = flow.response('booking_handoff' if handoff else 'booking_unavailable',
            details + ('\nNossa equipe pode ajudar por aqui.' if handoff else ''),
            [] if handoff else [flow.option('6', 'Consultar novamente', 'services'),
                                *flow.navigation()], False, handoff=handoff)
        return state, result, {'step': 'services'}
