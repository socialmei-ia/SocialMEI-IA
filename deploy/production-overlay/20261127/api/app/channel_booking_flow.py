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
    intent = natural_intent(text) if selected is None else None
    if intent:
        text = natural_command(intent)
    if selected is not None and selected.get('route') != 'booking':
        return None
    if selected is None and text in EXIT:
        return None
    previous = conn.execute("SELECT result FROM socialmei.wa_bot_decisions WHERE workspace_id=%s "
        "AND channel_id=%s AND conversation_id=%s AND binding_hash=%s AND status='confirmed' "
        "ORDER BY created_at DESC,id DESC LIMIT 1",
        (channel['workspace_id'], channel['channel_id'], message['conversation_id'], channel['binding_hash'])).fetchone()
    result = previous['result'] if previous else {}
    if selected is None and not intent and result.get('channel_booking') and result.get('booking_expires',0)>=datetime.now(timezone.utc).timestamp():
        chosen=natural_choice(message['text'],result.get('choices',[]),datetime.now(ZoneInfo('America/Recife')).date())
        if chosen is not None:
            text=chosen
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
        if intent=='start' and selected.get('step')=='services':
            selected=natural_entry(conn,channel,message,'waha')
        else:
            selected=natural_seek(conn,channel,message,selected,'waha')
        return advance(conn, channel, message, selected, native)
    except HTTPException as error:
        if error.status_code==503:
            return response('booking_unavailable','Não consegui consultar a agenda agora. Podemos tentar novamente?', [option('6','Consultar horários','services'), *navigation()],native)
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
            if len(rows)==1 and page==0 and target.get('appointment') is None:
                return _advance(conn,channel,message,{'route':'booking','step':'days','service_id':target['service_id'],'resource_id':rows[0]['id']},native,origin=origin)
            label = 'Quem você prefere para o atendimento?'
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
                                          target['day'], key, page=page, connection=conn,
                                          appointment_reference=target.get('appointment'))
        rows = result['items']
        label = 'Encontrei estes horários disponíveis para o dia '+datetime.fromisoformat(target['day']).strftime('%d/%m')+'. Qual fica melhor para você?'
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
        text = ('*Confira os dados da sua reserva*\n' + offer['service_name'] + '\n' + offer['resource_name']
            + '\n' + start.strftime('%d/%m/%Y às %H:%M') + '\nDuração: ' + friendly_duration(offer['duration_minutes'])
            + '\nValor: R$ ' + friendly_money(offer['price'])
            + '\n\nTudo certo? Confirme para reservar esse horário.')
        return response('booking_review', text,
            [option('1', 'Confirmar agendamento', 'confirm', confirmation=offer['confirmation']),
              option('2', 'Alterar horário', 'slots', service_id=offer['service_id'],
                     resource_id=offer['resource_id'], day=start.date().isoformat()),
              option('6', 'Alterar data', 'days', service_id=offer['service_id'],
                     resource_id=offer['resource_id'])], native)
    elif step == 'confirm':
        key = booking.signing_key_for_context(conn, *context)
        result = booking.confirm_for_message(*context, target['confirmation'], key, confirmed=True, connection=conn)
        zone = booking.read_policy(conn, context[0])['policy']['timezone']
        start = datetime.fromisoformat(result['scheduled_for']).astimezone(ZoneInfo(zone))
        text = ('*Agendamento confirmado*\n' + result['service_name'] + '\n' + result['resource_name']
                + '\n' + start.strftime('%d/%m/%Y às %H:%M') + '\nSeu horário está registrado! Agradecemos a preferência. Se precisar remarcar ou cancelar, é só me avisar.')
        return response('booking_confirmed', text, [], native)
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



# SM_NATURAL_BOOKING_V1

def natural_norm(value):
    import unicodedata,re
    return ' '.join(re.sub(
        r'[^a-z0-9/:]+',' ',
        unicodedata.normalize('NFKD',str(value).lower()).encode('ascii','ignore').decode()
    ).split())

def natural_intent(value):
    import re
    t=natural_norm(value)
    if re.search(r'\b(?:nao|nem|talvez)\b',t):
        return None

    prefix=r'(?:(?:oi|ola|bom dia|boa tarde|boa noite) )?(?:(?:eu )?(?:quero|gostaria de|preciso|posso|vou|queria) )?'

    if re.match('^'+prefix+r'(?:remarcar|reagendar)\b',t):
        return 'manage'

    if re.match('^'+prefix+r'(?:cancelar|consultar) (?:(?:o|a|meu|minha|meus|minhas) )?(?:agendamento|agendamentos|horario)\b',t):
        return 'manage'

    if re.match('^'+prefix+r'(?:agendar|marcar|reservar)\b',t):
        return 'start'

    return None

def natural_command(intent):
    if intent=='start':
        return 'agendar'
    return sorted(set(START)&set(MANAGE))[0]

def natural_day(value,today):
    import re
    from datetime import date,timedelta
    t=natural_norm(value)

    if re.search(r'\b(?:nao|nem|ou|talvez)\b',t):
        return None

    if re.search(r'\bdepois de amanha\b',t):
        return today+timedelta(days=2)
    if re.search(r'\bamanha\b',t):
        return today+timedelta(days=1)
    if re.search(r'\bhoje\b',t):
        return today

    dates=re.findall(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b',t)

    if len(dates)!=1:
        return None

    d,m,y=dates[0]

    try:
        return date(int(y or today.year),int(m),int(d))
    except ValueError:
        return None

def natural_time(value):
    import re
    t=natural_norm(value)

    if re.search(r'\b(?:nao|nem|ou|talvez)\b',t):
        return None

    matches=re.findall(r'\b(\d{1,2})(?::(\d{2})|h(?: ?(\d{2}))?)(?!\d)',t)

    if len(matches)!=1:
        return None

    h,a,b=matches[0]
    h=int(h)
    m=int(a or b or 0)

    if ('da tarde' in t or 'da noite' in t) and 1<=h<=11:
        h+=12

    if h>23 or m>59:
        return None

    return '%02d:%02d'%(h,m)

def natural_choice(value,choices,today):
    import re
    t=natural_norm(value)

    if not t or re.search(r'\b(?:nao|nem|talvez|ou)\b',t):
        return None

    out=[]

    for item in choices:
        target=item.get('target') or {}
        step=target.get('step')
        label=natural_norm(item.get('title',''))

        if step in ('confirm','confirm_ref','cancel_confirm'):
            expected='confirmar cancelamento' if step=='cancel_confirm' else 'confirmar agendamento'
            matched=t==expected

        elif step in ('resources','days','slots','review','review_ref','appointments','manage','cancel_review'):
            matched=bool(label and t in (label,'quero '+label,'escolho '+label))

            if step=='slots' and target.get('day'):
                d=natural_day(t,today)
                matched=matched or bool(d and d.isoformat()==target['day'])

            if step in ('review','review_ref'):
                start=(target.get('offer') or {}).get('scheduled_for') or target.get('scheduled_for')
                tm=natural_time(t)

                matched=matched or bool(
                    tm and start and datetime.fromisoformat(start).strftime('%H:%M')==tm
                )
        else:
            matched=False

        if matched:
            out.append(str(item['id']))

    return out[0] if len(out)==1 else None

def natural_seek(conn,channel,message,target,origin):
    if target.get('step')!='slots' or target.get('appointment') is not None:
        return target

    tm=natural_time(message['text'])

    if not tm:
        return target

    context=(channel['workspace_id'],message['conversation_id'],message['id'],origin)
    key=booking.signing_key_for_context(conn,*context)

    for page in range(20):
        r=booking.slots_for_message(
            *context,target['service_id'],target['resource_id'],
            target['day'],key,page=page,connection=conn
        )

        if any(
            datetime.fromisoformat(row['scheduled_for']).strftime('%H:%M')==tm
            for row in r['items']
        ):
            if origin in ('waha','instagram') and natural_intent(message['text'])=='start':
                import re
                t=natural_norm(message['text'])
                if not re.search(r'\b(?:antes|depois das|ate|entre|por volta|aproximadamente|se|preferencia)\b',t):
                    offer=next(row for row in r['items'] if datetime.fromisoformat(row['scheduled_for']).strftime('%H:%M')==tm)
                    return {'route':'booking','step':'review','offer':offer,'day':target['day'],'page':page}
            return {**target,'page':page}

        if not r['has_more']:
            break

    return target

def natural_entry(conn,channel,message,origin):
    import re
    context=(channel['workspace_id'],message['conversation_id'],message['id'],origin)

    value=message['text']
    t=natural_norm(value)

    rows=booking.services_for_message(*context,connection=conn)['items']

    matches=[
        r for r in rows
        if natural_norm(r['nome']) and re.search(
            r'(?<![a-z0-9])'+re.escape(natural_norm(r['nome']))+r'(?![a-z0-9])',t
        )
    ]

    base={'route':'booking','step':'services'}

    if len(matches)!=1:
        return base

    service=matches[0]['id']
    target={'route':'booking','step':'resources','service_id':service}

    resources=booking.resources_for_message(*context,service,connection=conn)['items']

    if len(resources)!=1:
        return target

    target.update(step='days',resource_id=resources[0]['id'])

    policy,_=booking.active_policy(conn,context[0])
    today=datetime.now(ZoneInfo(policy.timezone)).date()
    day=natural_day(value,today)

    if day is None or not today<=day<=today+timedelta(days=policy.horizon_days):
        return target

    target.update(step='slots',day=day.isoformat())

    return natural_seek(conn,channel,message,target,origin)


# SM_BOOKING_UX_V2
def friendly_duration(minutes):
    h,m=divmod(int(minutes),60)
    return ('%d %s'%(h,'hora' if h==1 else 'horas') if h else '')+(' e ' if h and m else '')+('%d min'%m if m else '')

def friendly_money(value):
    from decimal import Decimal
    return format(Decimal(str(value)),',.2f').translate(str.maketrans(',.','.,'))
