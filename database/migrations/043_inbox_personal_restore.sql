-- Preserve the visibility record while restoring the conversation.
ALTER TABLE socialmei.me_inbox_hidden ADD COLUMN IF NOT EXISTS restored_at TIMESTAMPTZ;
