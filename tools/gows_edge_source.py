"""Derive the GOWS edge from its pinned installed source without loosening WEBJS."""

def patch_receiver(source):
    old = "event.get('engine') != 'WEBJS'"
    if source.count(old) != 1 or "WAHA_INGRESS_AFTER" not in source:
        raise ValueError('Unexpected edge source')
    return source.replace(old, "event.get('engine') != self.binding.get('engine', 'WEBJS')")


def patch_service(source):
    old = '    return {k: entry[k] for k in (\n        "workspace_id", "instance", "session", "account_id", "hmac_key"\n    )}'
    new = '''    engine = entry.get("engine", "WEBJS")
    if engine not in {"WEBJS", "GOWS"}:
        raise ValueError("engine_not_authorized")
    binding = {k: entry[k] for k in (
        "workspace_id", "instance", "session", "account_id", "hmac_key"
    )}
    binding["engine"] = engine
    return binding'''
    if source.count(old) != 1:
        raise ValueError('Unexpected edge service source')
    return source.replace(old, new)
