"""WhatsApp booking menus over the shared agenda; no provider or new sender."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException

import channel_booking as booking

PAGE_SIZE = 3
MANAGE = {'8', 'meus agendamentos', 'cancelar agendamento', 'reagendar'}
START = {'6', 'agendar', 'agendar horario', 'agendar horário'} | MANAGE
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
    result = {**result, 'choices': [*result['choices'], option('8', 'Meus agendamentos', 'appointments')]}
    try:
        policy = booking.read_policy(conn, workspace)['policy']
    except HTTPException:
        return result
    if not policy['enabled']:
        return result
    return {**result, 'choices': [*result['choices'], option('6', 'Agendar horário', 'services')]}


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
    if (selected is None and result.get('channel_booking')
            and result.get('booking_expires', 0) < datetime.now(timezone.utc).timestamp()
            and text not in START
            and any(choice.get('id') == text for choice in result.get('choices', []))):
        return response('booking_expired', 'Esta opção de agendamento expirou. Consulte os horários novamente.',
                        [option('6', 'Consultar horários', 'services'), *navigation()], native)
    if selected is None and result.get('channel_booking') and result.get('booking_expires', 0) >= datetime.now(timezone.utc).timestamp():
        selected = next((choice.get('target') for choice in result.get('choices', [])
                         if choice.get('id') == text), None)
        if selected is None and text not in START:
            return response('booking_choice', 'Escolha uma das opções do agendamento ou volte ao menu.',
                            result['choices'], native)
    if selected is None:
        if text not in START:
            return None
        selected = {'route': 'booking', 'step': 'appointments' if text in MANAGE else 'services'}
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


def _advance(conn, channel, message, target, native, *, origin='waha'):
    context = (channel['workspace_id'], message['conversation_id'], message['id'], origin)
    step = target.get('step')
    page = target.get('page', 0)
    if type(page) is not int or not 0 <= page <= 100:
        raise HTTPException(409, 'Esta opção mudou. Comece o agendamento novamente.')
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
        from appointments import service
        item = service(conn, context[0], target['service_id'])
        rows = booking.bookable_days(policy, item['duracao_minutos'], datetime.now(timezone.utc))
        if not rows:
            return response('booking_no_days',
                'Não há datas compatíveis com a duração do serviço e a antecedência exigida. Fale com nossa equipe.',
                navigation(), native)
        label = 'Escolha a data. A disponibilidade será consultada em seguida.'
        choices = page_choices(rows, lambda day: {'step': 'slots', 'service_id': target['service_id'],
            'resource_id': target['resource_id'], 'day': day.isoformat()}, lambda day: day.strftime('%d/%m/%Y'), page=page)
    elif step == 'slots':
        key = booking.signing_key_for_context(conn, *context)
        result = booking.slots_for_message(*context, target['service_id'], target['resource_id'],
                                          target['day'], key, page=page, connection=conn,
                                          appointment_reference=target.get('appointment'))
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


def advance(conn, channel, message, target, native, *, origin='waha'):
    from appointments import lock_workspace
    context = (channel['workspace_id'], message['conversation_id'], message['id'], origin)
    step = target.get('step')
    reference = target.get('appointment')
    if step == 'appointments':
        rows = booking.appointments_for_message(*context, connection=conn)
        page = target.get('page', 0)
        if type(page) is not int or not 0 <= page <= 10:
            raise HTTPException(409, 'Consulte seus agendamentos novamente.')
        zone = ZoneInfo(booking.read_policy(conn, context[0])['policy']['timezone'])
        choices = page_choices(rows, lambda row: {'step': 'manage', 'appointment': row['reference']},
            lambda row: datetime.fromisoformat(str(row['scheduled_for'])).astimezone(zone).strftime('%d/%m %H:%M')
                        + ' ' + row['service_name'], page=page)
        if len(rows) > (page + 1) * PAGE_SIZE:
            choices.append(option('6', 'Próximos agendamentos', 'appointments', page=page + 1))
        if page:
            choices.append(option('7', 'Agendamentos anteriores', 'appointments', page=page - 1))
        return response('booking_appointments', 'Escolha seu agendamento.' if rows else
                        'Não há agendamentos futuros vinculados ao seu cadastro.', choices + navigation(), native)
    if reference is None:
        return _advance(conn, channel, message, target, native, origin=origin)
    lock_workspace(conn, context[0])
    identity = booking.context_for_message(conn, *context)
    row = booking.owned_appointment(conn, context[0], identity, reference)
    if step not in {'cancel_confirm', 'confirm'} and (
            row['revision'] != reference['revision'] or booking.appointment_snapshot(row) != reference.get('snapshot')
            or row['status'] != 'pending' or row['scheduled_for'] <= datetime.now(timezone.utc)):
        raise HTTPException(409, 'O agendamento mudou. Consulte seus agendamentos novamente.')
    if step in {'manage', 'cancel_review'}:
        zone = booking.read_policy(conn, context[0])['policy']['timezone']
        start = row['scheduled_for'].astimezone(ZoneInfo(zone))
        summary = row['service_name'] + '\n' + start.strftime('%d/%m/%Y às %H:%M')
        if step == 'manage':
            choices = [option('1', 'Cancelar agendamento', 'cancel_review', appointment=reference),
                       option('2', 'Reagendar', 'days', appointment=reference,
                              service_id=row['servico_id'], resource_id=str(row['resource_id']))]
        else:
            summary += '\nDeseja cancelar este agendamento? A vaga será liberada após confirmar.'
            choices = [option('1', 'Confirmar cancelamento', 'cancel_confirm', appointment=reference)]
        return response('booking_' + step, summary, choices + navigation(), native)
    if step in {'cancel_confirm', 'confirm'}:
        if step == 'confirm' and not isinstance(target.get('confirmation'), str):
            raise HTTPException(409, 'Escolha e confirme um novo horário.')
        key = booking.signing_key_for_context(conn, *context) if step == 'confirm' else None
        booking.change_for_message(*context, reference, confirmed=True, connection=conn,
            confirmation=target.get('confirmation') if step == 'confirm' else None, signing_key=key)
        return response('booking_cancelled' if step == 'cancel_confirm' else 'booking_rescheduled',
            'Agendamento cancelado.' if step == 'cancel_confirm' else 'Agendamento reagendado com sucesso.',
            navigation(), native)
    if step == 'review':
        offer = target['offer']
        if (offer['service_id'] != row['servico_id'] or offer['resource_id'] != str(row['resource_id'])
                or offer['duration_minutes'] != row['duration_minutes'] or str(offer['price']) != str(row['price'])):
            raise HTTPException(409, 'As condições do serviço mudaram. Fale com nossa equipe.')
    state, result = _advance(conn, channel, message, target, native, origin=origin)
    result['choices'] = [{**choice, 'target': {**choice['target'], 'appointment': reference}}
                         if choice.get('target', {}).get('route') == 'booking' else choice
                         for choice in result['choices']]
    if step == 'review':
        result['text'] = 'Confira o novo horário antes de reagendar.\n' + result['text']
    return state, result
