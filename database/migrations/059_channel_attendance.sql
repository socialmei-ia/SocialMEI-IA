ALTER TABLE socialmei.agenda_attendance_events
    ADD COLUMN IF NOT EXISTS source_message_id BIGINT,
    ADD COLUMN IF NOT EXISTS source_channel TEXT;

DO $checks$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
        WHERE conrelid='socialmei.agenda_attendance_events'::regclass AND conname='agenda_attendance_message') THEN
        ALTER TABLE socialmei.agenda_attendance_events
            ADD CONSTRAINT agenda_attendance_message FOREIGN KEY(workspace_id,source_message_id,source_channel)
                REFERENCES socialmei.me_messages(workspace_id,id,origin),
            ADD CONSTRAINT agenda_attendance_channel CHECK (
                (source_message_id IS NULL AND source_channel IS NULL) OR
                (source_message_id IS NOT NULL AND source_channel IS NOT NULL
                    AND source_channel IN ('waha','instagram') AND status='confirmed'));
    END IF;
END
$checks$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_agenda_attendance_source
    ON socialmei.agenda_attendance_events(workspace_id,source_message_id)
    WHERE source_message_id IS NOT NULL;
