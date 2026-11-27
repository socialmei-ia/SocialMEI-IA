-- Persist ordering and deferral independently for each workspace member.
ALTER TABLE socialmei.me_inbox_preferences
    ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS snoozed_until TIMESTAMPTZ;
