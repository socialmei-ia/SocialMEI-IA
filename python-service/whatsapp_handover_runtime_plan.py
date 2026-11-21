"""Pure private-file preparation after reservation; no provider or runtime I/O."""
from copy import deepcopy
from datetime import datetime
import math
from uuid import UUID

from settings import waha_pilot_binding_digest
from workspace_access import require
from waha_ingress import WahaBinding


def prepare_runtime_plan(request, receipt, registry):
    """The returned registry includes its existing HMAC: keep the result private."""
    require(receipt.get('status') == 'reserved', 'RESERVED_RECEIPT_REQUIRED')
    require((receipt.get('source_workspace_id'),receipt.get('source_channel_id'),receipt.get('target_workspace_id'))
            == (request.source_workspace_id,request.source_channel_id,request.target_workspace_id),
            'RECEIPT_SCOPE_MISMATCH')
    UUID(receipt['id'])
    target=receipt.get('target_channel_id')
    require(type(target) is int and 0 < target <= 9007199254740991
            and target != request.source_channel_id, 'INVALID_TARGET_CHANNEL')
    try:
        stamp=datetime.fromisoformat(receipt['ingress_after'])
        require(stamp.tzinfo is not None,'INVALID_RECEIPT_CUTOFF')
        cutoff=math.ceil(stamp.timestamp())
        require(cutoff > 0,'INVALID_RECEIPT_CUTOFF')
    except (TypeError,ValueError,OverflowError):
        require(False,'INVALID_RECEIPT_CUTOFF')
    require(isinstance(registry,dict) and registry.get('version') == 1
            and isinstance(registry.get('bindings'),list) and len(registry['bindings']) == 1,
            'SINGLE_SOURCE_REGISTRY_REQUIRED')
    old=registry['bindings'][0]
    WahaBinding(**old)
    require((old.get('workspace_id'),old.get('channel_id'),old.get('instance'),old.get('session'),
             old.get('account_id'),old.get('revision'),old.get('engine')) ==
            (request.source_workspace_id,request.source_channel_id,request.expected_instance,
             request.expected_session,request.expected_account,request.expected_revision,'GOWS'),
            'SOURCE_REGISTRY_CHANGED')
    require(isinstance(old.get('hmac_key'),str) and len(old['hmac_key']) >= 32,'PRIVATE_HMAC_REQUIRED')
    candidate=deepcopy(registry)
    candidate['bindings'][0].update(workspace_id=request.target_workspace_id,channel_id=target,
                                    revision=2,ingress_after=cutoff)
    binding=candidate['bindings'][0]
    WahaBinding(**binding)
    reviewed=waha_pilot_binding_digest(binding['workspace_id'],target,binding['instance'],binding['session'],
                                       binding['account_id'],2,'GOWS')
    return {'operation_id':receipt['id'],'candidate_registry':candidate,
            'configuration_delta':{
                'SOCIALMEI_WAHA_PILOT_WORKSPACE_ID':str(request.target_workspace_id),
                'SOCIALMEI_WAHA_PILOT_BINDING_SHA256':reviewed,
                'SOCIALMEI_WHATSAPP_HUMAN_WORKSPACE_ID':str(request.target_workspace_id)},
            'target_binding_revision':2,'new_worker_credential_required':True,
            'runtime_modified':False,'responders_started':False}
