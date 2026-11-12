"""Apply native-list canary to the pinned live bot without replacing its policies."""
import ast


def patch_bot(source, candidate):
    tree = ast.parse(candidate)
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'native_list_canary')
    helper_source = ast.get_source_segment(candidate, helper)
    if 'def native_list_canary(' in source:
        raise ValueError('Canary already present')
    anchor = "def render_waha(session, chat, text, choices, *, engine='WEBJS', list_verified=False):"
    old = "delivery = render_waha(channel['sessao'], state['contact_ref'].removeprefix('waha:'), row['result']['text'], row['result']['choices'])"
    new = "delivery = render_waha(channel['sessao'], state['contact_ref'].removeprefix('waha:'), row['result']['text'], row['result']['choices'], engine='GOWS', list_verified=native_list_canary(channel, state['contact_ref']))"
    if source.count(anchor) != 1 or source.count(old) != 1 or source.count('import os\n') != 1:
        raise ValueError('Unexpected live bot source')
    result = source.replace('import os\n', 'import os\nimport re\n', 1)
    result = result.replace(anchor, helper_source + '\n\n\n' + anchor, 1).replace(old, new, 1)
    old_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    new_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(result).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    if {name for name in old_functions if old_functions[name] != new_functions.get(name)} != {'claim'}:
        raise ValueError('Unrelated behavior changed')
    return result
