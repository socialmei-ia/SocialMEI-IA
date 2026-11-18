"""WhatsApp booking menus over the shared agenda; no provider or new sender."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException

import channel_booking as booking

PAGE_SIZE = 3
START = {'6', 'agendar', 'agendar horario', 'agendar horário'}
MANAGE_START = {'8', 'meus agendamentos', 'cancelar agendamento', 'reagendar agendamento', 'reagendar'}
EXIT = {'0', 'menu', 'inicio', 'início', '4', '5', 'atendente', 'humano', 'falar com atendente',
        'voltar', 'encerrar', 'sair', 'finalizar'}


def option(identifier, title, step, **values):
    return {'id': str(identifier), 'title': ' '.join(title.split())[:24],
            'target': {'route': 'booking', 'step': step, **values}}


def response(action, text, choices, native, *, handoff=False):
    return ('human' if handoff else 'menu'), {
        'action': action, 'text': text, 'choices': choices, 'items': [], 'handoff': handoff,
        'channel_booking': True, 'catalog_navigation': native,
        'booking_expires': int(datetime.now(timezone.utc).timestamp()) + 600,
    }


def navigation():
    return [{'id': '0', 'title': 'Voltar ao menu', 'target': {'route': 'main'}},
            {'id': '5', 'title': 'Falar com a equipe', 'target': {'route': 'human'}}]


def with_entry(conn, workspace, result):
    if result.get('action') != 'menu':
        return result
    try:
        policy = booking.read_policy(conn, workspace)['policy']
    except HTTPException:
        return result
    if not policy['enabled']:
        return result
    return {**result, 'choices': [*result['choices'], option('6', 'Agendar horário', 'services'),
                                   option('8', 'Meus agendamentos', 'manage')]}


def page_choices(rows, target, label, *, page=0):
    start = page * PAGE_SIZE
    selected = rows[start:start + PAGE_SIZE]
    choices = [option(index + 1, label(row), **target(row)) for index, row in enumerate(selected)]
    return choices


def respond(conn, channel, message, state, *, native=False):
    """Return None when the existing catalog/human planner owns this message."""
    if state['state'] == 'human':
        return None
    text = message['text'].strip().casefold()
    selected = message.get('catalog_target')
    if selected is not None and selected.get('route') != 'booking':
        return None
    if selected is None and text in EXIT:
        return None
    previous = conn.execute("SELECT result FROM socialmei.wa_bot_decisions WHERE workspace_id=%s "
        "AND channel_id=%s AND conversation_id=%s AND binding_hash=%s AND status='confirmed' "
        "ORDER BY created_at DESC,id DESC LIMIT 1",
        (channel['workspace_id'], channel['channel_id'], message['conversation_id'], channel['binding_hash'])).fetchone()
    result = previous['result'] if previous else {}
    if selected is None and result.get('channel_booking') and result.get('booking_expires', 0) >= datetime.now(timezone.utc).timestamp():
        selected = next((choice.get('target') for choice in result.get('choices', [])
                         if choice.get('id') == text), None)
        if selected is None and text not in START | MANAGE_START:
            return response('booking_choice', 'Escolha uma das opções do agendamento ou volte ao menu.',
                            result['choices'], native)
    if selected is None:
        if text not in START | MANAGE_START:
            return None
        selected = {'route': 'booking', 'step': 'manage' if text in MANAGE_START else 'services'}
    if selected.get('route') != 'booking':
        return None
    try:
        return advance(conn, channel, message, selected, native)
    except HTTPException as error:
        if error.status_code not in {409, 422, 503}:
            raise
        if 'associar seu cadastro' in str(error.detail) or error.status_code == 503:
            return response('booking_handoff', str(error.detail) + '\nNossa equipe pode ajudar por aqui.',
                            [], native, handoff=True)
        return response('booking_unavailable', str(error.detail),
                        [option('6', 'Consultar horários', 'services'), *navigation()], native)


def advance(conn, channel, message, target, native, *, origin='waha'):
    context = (channel['workspace_id'], message['conversation_id'], message['id'], origin)
    step = target.get('step')
    page = target.get('page', 0)
    if type(page) is not int or not 0 <= page <= 100:
        raise HTTPException(409, 'Esta opção mudou. Comece o agendamento novamente.')
    if step in {'manage', 'manage_review', 'cancel_review', 'cancel_confirm', 'move_days',
                'move_slots', 'move_review', 'move_confirm'}:
        return manage_advance(conn, channel, message, target, native, origin=origin)
    if step in {'services', 'resources'}:
        if step == 'services':
            rows = booking.services_for_message(*context, connection=conn)['items']
            label = 'Qual serviço você deseja agendar?'
            choices = page_choices(rows, lambda row: {'step': 'resources', 'service_id': row['id']},
                                   lambda row: row['nome'], page=page)
        else:
            rows = booking.resources_for_message(*context, target['service_id'], connection=conn)['items']
            label = 'Escolha o profissional ou recurso para seu atendimento.'
            choices = page_choices(rows, lambda row: {'step': 'days', 'service_id': target['service_id'],
                                   'resource_id': row['id']}, lambda row: row['nome'], page=page)
        if not choices:
            return response('booking_empty', 'Não há opções disponíveis nesta seleção. Nossa equipe pode ajudar.',
                            navigation(), native)
    elif step == 'days':
        booking.resources_for_message(*context, target['service_id'], connection=conn)
        policy, _ = booking.active_policy(conn, context[0])
        today = datetime.now(ZoneInfo(policy.timezone)).date()
        weekdays = {window.weekday for window in policy.hours}
        rows = [today + timedelta(days=offset) for offset in range(policy.horizon_days + 1)
                if (today + timedelta(days=offset)).weekday() in weekdays]
        label = 'Escolha a data. A disponibilidade será consultada em seguida.'
        choices = page_choices(rows, lambda day: {'step': 'slots', 'service_id': target['service_id'],
            'resource_id': target['resource_id'], 'day': day.isoformat()}, lambda day: day.strftime('%d/%m/%Y'), page=page)
    elif step == 'slots':
        key = booking.signing_key_for_context(conn, *context)
        result = booking.slots_for_message(*context, target['service_id'], target['resource_id'],
                                          target['day'], key, page=page, connection=conn)
        rows = result['items']
        label = 'Escolha um horário disponível. A reserva só é feita após sua confirmação.'
        choices = page_choices(rows, lambda row: {'step': 'review', 'offer': row},
            lambda row: datetime.fromisoformat(row['scheduled_for']).strftime('%H:%M'))
        if not choices:
            go_back = ([option('7', 'Opções anteriores', 'slots',
                         service_id=target['service_id'], resource_id=target['resource_id'],
                         day=target['day'], page=page - 1)] if page else [])
            return response('booking_no_slots', 'Não há horários disponíveis nessa página.',
                [*go_back, option('6', 'Escolher outra data', 'days',
                    service_id=target['service_id'], resource_id=target['resource_id']),
                 *navigation()], native)
        if result['has_more']:
            choices.append(option('6', 'Próximos horários', 'slots',
                service_id=target['service_id'], resource_id=target['resource_id'],
                day=target['day'], page=page + 1))
        if page:
            choices.append(option('7', 'Horários anteriores', 'slots',
                service_id=target['service_id'], resource_id=target['resource_id'],
                day=target['day'], page=page - 1))
        return response('booking_slots', label, choices + navigation(), native)
    elif step == 'review':
        offer = target['offer']
        start = datetime.fromisoformat(offer['scheduled_for'])
        text = ('*Confirme seu agendamento*\n' + offer['service_name'] + '\n' + offer['resource_name']
            + '\n' + start.strftime('%d/%m/%Y às %H:%M') + '\nDuração: ' + str(offer['duration_minutes'])
            + ' min\nValor: R$ ' + offer['price'].replace('.', ',')
            + '\n\nO horário será reservado somente após sua confirmação.')
        return response('booking_review', text,
            [option('1', 'Confirmar agendamento', 'confirm', confirmation=offer['confirmation']), *navigation()], native)
    elif step == 'confirm':
        key = booking.signing_key_for_context(conn, *context)
        result = booking.confirm_for_message(*context, target['confirmation'], key, confirmed=True, connection=conn)
        zone = booking.read_policy(conn, context[0])['policy']['timezone']
        start = datetime.fromisoformat(result['scheduled_for']).astimezone(ZoneInfo(zone))
        text = ('*Agendamento confirmado*\n' + result['service_name'] + '\n' + result['resource_name']
                + '\n' + start.strftime('%d/%m/%Y às %H:%M') + '\nSeu horário está registrado em nossa agenda.')
        return response('booking_confirmed', text, navigation(), native)
    else:
        raise HTTPException(409, 'Esta opção mudou. Comece o agendamento novamente.')
    if len(rows) > (page + 1) * PAGE_SIZE:
        choices.append(option('6', 'Próximas opções', step, **{k: v for k, v in target.items()
                              if k not in {'route', 'step', 'page'}}, page=page + 1))
    if page:
        choices.append(option('7', 'Opções anteriores', step, **{k: v for k, v in target.items()
                              if k not in {'route', 'step', 'page'}}, page=page - 1))
    return response('booking_' + step, label, choices + navigation(), native)


def manage_advance(conn, channel, message, target, native, *, origin):
    """Self-service actions originate only from the linked, authenticated conversation."""
    context = (channel['workspace_id'], message['conversation_id'], message['id'], origin)
    step = target['step']
    page = target.get('page', 0)
    if type(page) is not int or not 0 <= page <= 100:
        raise HTTPException(409, 'Esta opção mudou. Consulte novamente.')
    key = booking.signing_key_for_context(conn, *context)
    if step == 'manage':
        rows = booking.manageable_for_message(*context, key, connection=conn)['items']
        if not rows:
            return response('booking_manage_empty',
                'Não encontrei horários futuros pendentes marcados nesta conversa. Nossa equipe pode ajudar.',
                navigation(), native)
        choices = page_choices(rows, lambda row: {'step': 'manage_review', 'management': row['management']},
            lambda row: row['service_name'][:11] + ' ' +
                datetime.fromisoformat(row['scheduled_for']).strftime('%d/%m %H:%M'), page=page)
        if len(rows) > (page + 1) * PAGE_SIZE:
            choices.append(option('6', 'Próximos horários', 'manage', page=page + 1))
        if page:
            choices.append(option('7', 'Horários anteriores', 'manage', page=page - 1))
        return response('booking_manage', 'Selecione um agendamento desta conversa.',
                        choices + navigation(), native)

    management = target['management']
    row = booking.managed_for_message(*context, management, key, connection=conn)
    start = datetime.fromisoformat(row['scheduled_for'])
    zone = booking.read_policy(conn, context[0])['policy']['timezone']
    start = start.astimezone(ZoneInfo(zone))
    summary = row['service_name'] + '\n' + row['resource_name'] + '\n' + start.strftime('%d/%m/%Y às %H:%M')

    if step == 'manage_review':
        return response('booking_manage_review', '*Seu agendamento*\n' + summary,
            [option('1', 'Cancelar agendamento', 'cancel_review', management=management),
             option('2', 'Alterar data e hora', 'move_days', management=management), *navigation()], native)
    if step == 'cancel_review':
        return response('booking_cancel_review',
            '*Confirmar cancelamento?*\n' + summary + '\n\nO horário será liberado.',
            [option('1', 'Confirmar cancelamento', 'cancel_confirm', management=management),
             option('2', 'Não cancelar', 'manage_review', management=management), *navigation()], native)
    if step == 'cancel_confirm':
        booking.cancel_for_message(*context, management, key, confirmed=True, connection=conn)
        return response('booking_cancelled',
            'Agendamento cancelado. Seu horário foi liberado.',
            [option('8', 'Meus agendamentos', 'manage'), *navigation()], native)
    if step == 'move_days':
        policy, _ = booking.active_policy(conn, context[0])
        today = datetime.now(ZoneInfo(policy.timezone)).date()
        weekdays = {window.weekday for window in policy.hours}
        rows = [today + timedelta(days=offset) for offset in range(policy.horizon_days + 1)
                if (today + timedelta(days=offset)).weekday() in weekdays]
        choices = page_choices(rows,
            lambda day: {'step': 'move_slots', 'management': management, 'day': day.isoformat()},
            lambda day: day.strftime('%d/%m/%Y'), page=page)
        if len(rows) > (page + 1) * PAGE_SIZE:
            choices.append(option('6', 'Próximas datas', 'move_days', management=management, page=page + 1))
        if page:
            choices.append(option('7', 'Datas anteriores', 'move_days', management=management, page=page - 1))
        return response('booking_move_days', 'Escolha a nova data para seu atendimento.',
                        choices + navigation(), native)
    if step == 'move_slots':
        result = booking.slots_for_message(*context, row['servico_id'], row['resource_id'],
                                           target['day'], key, page=page, connection=conn)
        choices = page_choices(result['items'],
            lambda offer: {'step': 'move_review', 'management': management,
                           'offer': offer, 'day': target['day'], 'page': page},
            lambda offer: datetime.fromisoformat(offer['scheduled_for']).strftime('%H:%M'))
        if result['has_more']:
            choices.append(option('6', 'Próximos horários', 'move_slots',
                                  management=management, day=target['day'], page=page + 1))
        if page:
            choices.append(option('7', 'Horários anteriores', 'move_slots',
                                  management=management, day=target['day'], page=page - 1))
        if not choices:
            choices.append(option('8', 'Escolher outra data', 'move_days', management=management))
        return response('booking_move_slots',
            'Escolha um horário livre. Nada muda antes da confirmação.',
            choices + navigation(), native)
    if step == 'move_review':
        offer = target['offer']
        new_time = datetime.fromisoformat(offer['scheduled_for']).astimezone(ZoneInfo(zone))
        return response('booking_move_review',
            '*Confirmar reagendamento?*\nDe: ' + start.strftime('%d/%m/%Y às %H:%M')
            + '\nPara: ' + new_time.strftime('%d/%m/%Y às %H:%M')
            + '\n' + summary.split('\n')[0],
            [option('1', 'Confirmar nova data', 'move_confirm', management=management,
                    confirmation=offer['confirmation'], offer=offer, day=target['day'], page=page),
             *navigation()], native)
    if step == 'move_confirm':
        result = booking.reschedule_for_message(*context, management, target['confirmation'],
                                                key, confirmed=True, connection=conn)
        new_time = datetime.fromisoformat(result['scheduled_for']).astimezone(ZoneInfo(zone))
        return response('booking_rescheduled',
            'Agendamento reagendado para ' + new_time.strftime('%d/%m/%Y às %H:%M') + '.',
            [option('8', 'Meus agendamentos', 'manage'), *navigation()], native)
    raise HTTPException(409, 'Esta opção mudou. Consulte seus agendamentos novamente.')
