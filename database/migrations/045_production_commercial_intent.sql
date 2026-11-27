-- Reconcile the commercial intent already recorded by the production analysis worker.
ALTER TABLE socialmei.me_provider_sentiment_jobs ADD COLUMN IF NOT EXISTS commercial_intent TEXT;

DO $intent$
DECLARE
    definition text;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid='socialmei.me_provider_sentiment_jobs'::regclass
          AND attname='commercial_intent' AND NOT attisdropped
          AND atttypid='text'::regtype AND NOT attnotnull AND NOT atthasdef
    ) THEN
        RAISE EXCEPTION 'Unexpected type or default for commercial_intent';
    END IF;

    SELECT pg_get_constraintdef(oid) INTO definition
    FROM pg_constraint
    WHERE conrelid='socialmei.me_provider_sentiment_jobs'::regclass
      AND conname='me_provider_sentiment_jobs_commercial_intent_check';

    IF definition IS NULL THEN
        ALTER TABLE socialmei.me_provider_sentiment_jobs
            ADD CONSTRAINT me_provider_sentiment_jobs_commercial_intent_check
            CHECK (commercial_intent = ANY (ARRAY['none','inquiry','quote','purchase','booking','declined','support']));
    ELSIF definition <> 'CHECK ((commercial_intent = ANY (ARRAY[''none''::text, ''inquiry''::text, ''quote''::text, ''purchase''::text, ''booking''::text, ''declined''::text, ''support''::text])))' THEN
        RAISE EXCEPTION 'Unexpected commercial_intent check constraint';
    END IF;
END
$intent$;
