"""Bounded intents for already interpreted WhatsApp attachments."""

import os
import re
import unicodedata
from datetime import datetime

# References the authenticated e/m/v rows of the existing planner.
COMPLETED = """
    SELECT a.media_kind, j.interpretation
    FROM socialmei.me_inbound_attachments a
    JOIN socialmei.me_attachment_ai j ON j.attachment_id=a.id AND j.sha256=a.sha256
    WHERE a.workspace_id=e.workspace_id AND a.channel_id=e.canal_id
      AND a.conversation_id=v.id AND a.origin='waha'
      AND a.account_ref IN (v.account_ref, e.waha_account_snapshot)
      AND a.contact_ref IN (v.contact_ref, substring(v.contact_ref from 6))
      AND a.external_message_id=e.mensagem_externa_id
      AND a.media_kind=e.dados_normalizados->>'media_kind'
      AND v.origin='waha'
      AND a.source_fingerprint=e.fingerprint
      AND a.source_event_key IN (e.chave_evento, e.waha_event_key)
      AND j.status='completed' AND j.finished_at IS NOT NULL
      AND COALESCE(e.dados_normalizados->>'wa_selection','')=''
    LIMIT 1
"""

SOURCE = "e.tipo='message'"
MEDIA_WINDOW = """
    m.occurred_at BETWEEN NOW()-INTERVAL '2 minutes' AND NOW()+INTERVAL '30 seconds'
    AND NOT EXISTS (
        SELECT 1 FROM socialmei.me_messages newer
        WHERE newer.workspace_id=m.workspace_id AND newer.conversation_id=m.conversation_id
          AND newer.origin='waha' AND (newer.occurred_at,newer.id)>(m.occurred_at,m.id)
    )
"""
MEDIA_SOURCE = (
    f"({SOURCE} OR (e.tipo='media' AND e.recebido_em >= %s AND m.occurred_at >= %s "
    f"AND {MEDIA_WINDOW} AND EXISTS ({COMPLETED})))"
)

REQUESTS = {
    'booking': r'(?:agendar(?: (?:um )?horario| (?:um )?servico)?|marcar (?:um )?horario|consultar (?:os )?horarios(?: disponiveis)?|ver (?:os )?horarios(?: disponiveis)?)',
    'quote': r'(?:pedir|solicitar) (?:um )?orcamento|(?:um )?orcamento',
    'services': r'(?:(?:ver|conhecer|consultar|saber) (?:os )?)?(?:servicos|(?:os )?(?:precos|valores) dos servicos)|quais(?: sao)? os servicos',
    'products': r'(?:(?:ver|conhecer|consultar|saber) (?:os )?)?(?:produtos|catalogo|(?:os )?(?:precos|valores|estoque)(?: dos produtos)?|(?:a )?disponibilidade dos produtos)|quais(?: sao)? os produtos',
}
PREFIX = r'(?:(?:eu )?(?:quero|queria|gostaria de|posso|preciso) )?'


def activation(channel):
    if (channel['workspace_id'], channel['channel_id']) != (60, 3):
        return None
    raw = os.getenv('SOCIALMEI_WHATSAPP_MEDIA_START_UTC')
    if not raw:
        return None
    try:
        start = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return start if start.utcoffset() is not None else None


def intent(kind, interpretation):
    if not isinstance(interpretation, str) or len(interpretation) > 480:
        return None
    if kind in {'imagem', 'documento'}:
        return 'context_only'
    if kind != 'audio':
        return None
    text = unicodedata.normalize('NFKD', interpretation.strip().casefold())
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r'^transcricao:\s*', '', text)
    text = ' '.join(text.split()).strip('?"!. ')
    for name, pattern in REQUESTS.items():
        if re.fullmatch(PREFIX + '(?:' + pattern + ')', text):
            return name
    return 'clarify'


COMMERCIAL_HINTS = {
    'products': 'Quero consultar o catálogo, os preços ou a disponibilidade de produtos.',
    'services': 'Quero consultar os serviços e os valores.',
    'quote': 'Quero solicitar um orçamento.',
    'booking': 'Quero consultar opções de agendamento.',
}

# These are allowlisted summaries. Transcriptions and attachment contents stay private.
COMMERCIAL_DECISION = """
    SELECT d.result->>'media_intent' AS media_intent
    FROM socialmei.wa_bot_decisions d
    JOIN socialmei.crm_eventos_canal e ON e.workspace_id=d.workspace_id
      AND e.canal_id=d.channel_id AND e.inbox_message_id=d.source_message_id
      AND e.tipo='media' AND e.status='processado' AND e.dados_normalizados->>'media_kind'='audio'
    WHERE d.workspace_id=m.workspace_id AND d.conversation_id=m.conversation_id
      AND d.source_message_id=m.id AND d.workspace_id=60 AND d.channel_id=3
      AND d.status IN ('planned','claimed','confirmed') AND d.result->>'derived_from_media'='true'
      AND d.result->>'media_intent' IN ('products','services','quote','booking')
    LIMIT 1
"""
