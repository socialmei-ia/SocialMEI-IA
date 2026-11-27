ALTER TABLE socialmei.ig_meta_publications
    ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS schedule_timezone TEXT,
    ADD COLUMN IF NOT EXISTS schedule_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE socialmei.ig_meta_publications DROP CONSTRAINT IF EXISTS ig_meta_publications_status_check;
ALTER TABLE socialmei.ig_meta_publications ADD CONSTRAINT ig_meta_publications_status_check
    CHECK (status IN ('creating','created','publishing','published','uncertain','scheduled','cancelled','failed'));
CREATE INDEX IF NOT EXISTS ig_meta_publications_schedule_due
    ON socialmei.ig_meta_publications(scheduled_at,id) WHERE status='scheduled';
CREATE INDEX IF NOT EXISTS ig_meta_publications_schedule_progress
    ON socialmei.ig_meta_publications(updated_at,id)
    WHERE scheduled_at IS NOT NULL AND status IN ('creating','created','publishing');
