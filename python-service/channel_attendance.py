"""Persist an explicit attendance selection from a verified inbound message."""

import os
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException

from channel_booking import appointment_snapshot, context_for_message, owned_appointment
from shared_data import MAX_SAFE_ID


def enabled(workspace):
    return (os.getenv("SOCIALMEI_CHANNEL_ATTENDANCE_ENABLED") == "YES"
            and str(workspace) in os.getenv("SOCIALMEI_CHANNEL_ATTENDANCE_WORKSPACES", "").split(","))


def confirm(conn, workspace, conversation, message, origin, reference):
    from appointments import history, lock_workspace

    lock_workspace(conn, workspace)
    identity = context_for_message(conn, workspace, conversation, message, origin)
    row = owned_appointment(conn, workspace, identity, reference)
    receipt = conn.execute(
        "SELECT appointment_id,expected_revision FROM socialmei.agenda_attendance_events "
        "WHERE workspace_id=%s AND source_message_id=%s",
        (workspace, message),
    ).fetchone()
    if receipt:
        if (receipt["appointment_id"], receipt["expected_revision"]) != (row["id"], reference["revision"]):
            raise HTTPException(409, "Esta mensagem já confirmou outro agendamento.")
        return
    if (row["revision"] != reference["revision"] or row["revision"] >= MAX_SAFE_ID
            or appointment_snapshot(row) != reference.get("snapshot")
            or row["status"] != "pending" or row["attendance"] is not None):
        raise HTTPException(409, "O agendamento mudou. Consulte seus agendamentos novamente.")
    saved = conn.execute(
        "UPDATE socialmei.agenda_appointments SET attendance='confirmed',revision=revision+1,updated_at=now() "
        "WHERE workspace_id=%s AND id=%s AND ends_at>now() RETURNING *",
        (workspace, row["id"]),
    ).fetchone()
    if not saved:
        raise HTTPException(409, "O horário da reserva terminou.")
    history(conn, workspace, saved)
    operation = uuid5(NAMESPACE_URL, f"socialmei-channel-attendance:{workspace}:{message}")
    conn.execute(
        "INSERT INTO socialmei.agenda_attendance_events(workspace_id,operation_id,appointment_id,"
        "expected_revision,revision,status,scheduled_for,actor_id,source_message_id,source_channel) "
        "VALUES(%s,%s,%s,%s,%s,'confirmed',%s,%s,%s,%s)",
        (workspace, operation, saved["id"], row["revision"], saved["revision"], saved["scheduled_for"],
         identity["cliente_id"], message, origin),
    )
