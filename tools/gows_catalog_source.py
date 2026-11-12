"""Small source patch retaining the deployed bot's human/quiet-repeat policies."""
import ast
import copy
import re
from datetime import datetime


def catalog_registry_snapshot(value):
    """Retain the original ingress boundary, including already accepted edge events."""
    bindings = value.get('bindings', [])
    if (len(bindings) != 1 or bindings[0].get('engine') != 'GOWS'
            or type(bindings[0].get('ingress_after')) is not int
            or bindings[0]['ingress_after'] <= 0):
        raise ValueError('Unexpected catalog ingress binding')
    return copy.deepcopy(value)


def catalog_source_boundary(environment):
    """Catalog updates retain the source gate of the already active sender."""
    value = environment.get('SOCIALMEI_CONTINUOUS_START_UTC', '')
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError('Existing catalog activation required') from None
    if parsed.tzinfo is None:
        raise ValueError('Existing catalog activation timezone required')
    return value


def verified_candidate_images(prepared, image_identity):
    """Check mutable tags before stopping services, then return immutable IDs."""
    expected = prepared.get('image_ids', {})
    tags = prepared.get('images', {})
    if set(expected) != {'api', 'menu', 'worker'} or set(tags) != set(expected):
        raise ValueError('Candidate image identities required')
    for kind, identity in expected.items():
        if (not isinstance(identity, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', identity)
                or image_identity(tags[kind]) != identity
                or image_identity(identity) != identity):
            raise ValueError('Candidate image identity changed')
    return dict(expected)


def patch_history(source):
    old = "text = render_waha('', '', row['result']['text'], row['result']['choices'])['body']['text']"
    if source.count(old) != 1:
        raise ValueError('Unexpected inbox source')
    source = source.replace('from whatsapp_bot import render_waha',
        'from whatsapp_bot import render_waha\n            from whatsapp_catalog_navigation import history_text', 1)
    return source.replace(old, "text = history_text(row['result']) if row['result'].get('catalog_navigation') else render_waha('', '', row['result']['text'], row['result']['choices'])['body']['text']", 1)

HELPER = '''def _catalog_answer(conn, workspace, state, text, target, enabled):
    if not enabled or state == 'human':
        return answer(conn, workspace, state, text)
    if target is not None:
        return navigation.respond(conn, workspace, target)
    command = globals().get('canonical_choice', lambda value: value.strip().casefold())(text)
    routes = {'0': {'route':'main'}, '1': {'route':'browse','kind':'Produto'},
              '2': {'route':'browse','kind':'Produto'}, '3': {'route':'browse','kind':'Serviço'},
              '4': {'route':'quote'}, '5': {'route':'human'},
              'encerrar': {'route':'close'}, 'finalizar': {'route':'close'}}
    if state == 'ask_product' and command not in routes:
        return navigation.browse(conn, workspace, {'route':'browse','kind':'Produto','query':text})
    return navigation.respond(conn, workspace, routes.get(command, {'route':'main'}))


'''


NATIVE = """def native_list_canary(channel, contact):
    return (
        os.getenv('SOCIALMEI_MENU_GOWS_LIST_CANARY_ACTIVE') == 'YES'
        and os.getenv('SOCIALMEI_MENU_WAHA_ENGINE') == 'GOWS'
        and (channel['workspace_id'], channel['channel_id'], channel['instancia'], channel['sessao'])
        == (1, 1, 'socialmei-equipe-piloto', '01')
        and contact in navigation.configured_contacts(os.environ)
    )
"""


def patch_bot(source):
    if 'def _catalog_answer(' in source:
        raise ValueError('Catalog navigation already installed')
    source = source.replace('import os\n', 'import os\nimport whatsapp_catalog_navigation as navigation\n', 1)
    source = source.replace('def native_list_canary(', HELPER + 'def native_list_canary(', 1)
    old = 'SELECT m.*,v.contact_ref FROM socialmei.crm_eventos_canal e '
    assert source.count(old) == 1
    source = source.replace(old, 'SELECT m.*,v.contact_ref,e.dados_normalizados AS ingress_data FROM socialmei.crm_eventos_canal e ')
    anchor = '        now = datetime.now(timezone.utc)\n'
    assert source.count(anchor) == 1
    source = source.replace(anchor, '''        nav_enabled = native_list_canary(channel, message['contact_ref'])
        metadata = message.get('ingress_data') or {}
        token = metadata.get('wa_selection')
        if nav_enabled and navigation.valid_token(token):
            message['catalog_target'] = navigation.resolve(conn, channel, conv, token)
            if message['catalog_target'].get('route') == 'resume' and not pending_human_reply(conn, workspace, cid, conv):
                message['text'] = '0'
                state['state'] = 'menu'
''' + anchor, 1)
    source = source.replace("and not explicit_menu_action(message['text'])):", "and not (explicit_menu_action(message['text']) or message.get('catalog_target') is not None)):")
    source = source.replace("and text_for_resume in {'menu', 'menu principal', '0'}", "and text_for_resume in {'menu', 'menu principal', '0'}\n                        and (message.get('catalog_target') is None or message['catalog_target'].get('route') == 'resume')")
    tree = ast.parse(source)
    native = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'native_list_canary')
    source = source.replace(ast.get_source_segment(source, native), NATIVE.rstrip())
    tree = ast.parse(source)
    prepare = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'prepare')
    calls = [n for n in ast.walk(prepare) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'answer']
    assert len(calls) == 1
    old_call = ast.get_source_segment(source, calls[0])
    new_call = old_call.replace('answer(', '_catalog_answer(', 1)[:-1] + ", message.get('catalog_target'), nav_enabled)"
    source = source.replace(old_call, new_call, 1)
    source = source.replace("row['result']['choices'],\n", "(navigation.offered_choices(row) if row['result'].get('catalog_navigation') else row['result']['choices']),\n")
    # Deployed claim may use a single-line renderer call.
    source = source.replace("row['result']['choices'], engine=", "(navigation.offered_choices(row) if row['result'].get('catalog_navigation') else row['result']['choices']), engine=")
    source = source.replace("'description': None} for c in choices", "'description': c.get('description')} for c in choices")
    claim_gate = '        if not permitted:\n'
    if source.count(claim_gate) != 1:
        raise ValueError('Unexpected catalog claim gate')
    source = source.replace(claim_gate,
        "        permitted = permitted and (not row['result'].get('catalog_navigation')\n"
        "                                   or native_list_canary(channel, state['contact_ref']))\n"
        + claim_gate, 1)
    assert 'navigation.offered_choices(row)' in source
    compile(source, 'whatsapp_bot.py', 'exec')
    return source
