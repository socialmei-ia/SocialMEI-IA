-- Shared planning, separate from outcome_note and independent of sales/payments.
ALTER TABLE socialmei.crm_opportunities ADD COLUMN IF NOT EXISTS estimated_amount NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK(estimated_amount BETWEEN 0 AND 1000000000);
ALTER TABLE socialmei.crm_opportunities ADD COLUMN IF NOT EXISTS follow_up_date DATE;
ALTER TABLE socialmei.crm_opportunities ADD COLUMN IF NOT EXISTS planning_note TEXT NOT NULL DEFAULT '' CHECK(length(planning_note)+length(regexp_replace(planning_note,U&'[\0001-\FFFF]','','g'))<=140);
ALTER TABLE socialmei.crm_opportunities ADD COLUMN IF NOT EXISTS contacted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE socialmei.crm_opportunities ADD COLUMN IF NOT EXISTS planning_initialized BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE socialmei.crm_opportunities ADD COLUMN IF NOT EXISTS legacy_planning JSONB CHECK(legacy_planning IS NULL OR (jsonb_typeof(legacy_planning)='object' AND octet_length(legacy_planning::text)<=32768));
