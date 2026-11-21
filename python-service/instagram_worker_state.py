"""Reconcile file checkpoints against the durable outbox before resuming work."""


def reconcile(state, workspace, start, *, unresolved):
    if type(workspace) is not int or workspace <= 0 or start.tzinfo is None:
        raise RuntimeError('Instagram worker identity invalid')
    if unresolved:
        raise RuntimeError('Instagram delivery requires reconciliation')
    if state is None:
        return {'workspace_id': workspace, 'status': 'running', 'in_flight': False,
                'confirmed': 0, 'start': start.isoformat()}
    if (not isinstance(state, dict) or state.get('status') != 'running'
            or state.get('start') != start.isoformat()
            or type(state.get('in_flight')) is not bool
            or type(state.get('confirmed')) is not int or state['confirmed'] < 0):
        raise RuntimeError('Instagram checkpoint requires review')
    binding = state.get('workspace_id')
    # Legacy idle checkpoints can be bound after the lease/database review.
    # An unbound interrupted operation cannot be attributed to a workspace.
    if ((binding is not None and (type(binding) is not int or binding != workspace))
            or (binding is None and state['in_flight'])):
        raise RuntimeError('Instagram checkpoint workspace mismatch')
    result = dict(state)
    result['workspace_id'] = workspace
    if state['in_flight']:
        result['in_flight'] = False
        result['recovered_after_restart'] = state.get('recovered_after_restart', 0) + 1
    return result
