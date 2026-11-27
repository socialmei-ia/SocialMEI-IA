ALTER TABLE socialmei.ig_meta_ingress_events
    DROP CONSTRAINT IF EXISTS ig_meta_ingress_events_kind_check,
    DROP CONSTRAINT IF EXISTS ig_meta_ingress_events_check1;
ALTER TABLE socialmei.ig_meta_ingress_events
    ADD CONSTRAINT ig_meta_ingress_events_kind_check CHECK (kind IN ('message','media','echo','receipt','unsupported')),
    ADD CONSTRAINT ig_meta_ingress_events_check1 CHECK ((kind IN ('message','media'))=(status='processed'));

CREATE UNIQUE INDEX IF NOT EXISTS ig_media_ingress_source_idx
    ON socialmei.ig_meta_ingress_events(workspace_id,external_account_id,event_key,message_id);

CREATE TABLE IF NOT EXISTS socialmei.ig_inbound_media (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY CHECK (id <= 9007199254740991),
    workspace_id BIGINT NOT NULL,
    external_account_id VARCHAR(40) NOT NULL,
    event_key CHAR(64) NOT NULL,
    message_id BIGINT NOT NULL,
    position SMALLINT NOT NULL CHECK (position BETWEEN 0 AND 3),
    kind TEXT NOT NULL CHECK (kind IN ('image','audio')),
    source_url TEXT CHECK (length(source_url) <= 4096),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','fetching','ready','failed')),
    attempts SMALLINT NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '24 hours',
    lease_id UUID,
    sha256 CHAR(64) CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    mime TEXT,
    size_bytes INT CHECK (size_bytes BETWEEN 1 AND 10485760),
    UNIQUE(workspace_id,message_id,position),
    FOREIGN KEY(workspace_id,external_account_id,event_key,message_id)
      REFERENCES socialmei.ig_meta_ingress_events(workspace_id,external_account_id,event_key,message_id) ON DELETE CASCADE,
    CHECK ((status = 'fetching') = (lease_id IS NOT NULL)),
    CHECK ((status IN ('pending','fetching')) = (source_url IS NOT NULL)),
    CHECK ((status = 'ready') = (sha256 IS NOT NULL AND mime IS NOT NULL AND size_bytes IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ig_inbound_media_due_idx
    ON socialmei.ig_inbound_media(workspace_id,available_at,id)
    WHERE status IN ('pending','fetching');

DO $grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='socialmei_candidate040') THEN
        GRANT SELECT, INSERT, UPDATE ON socialmei.ig_inbound_media TO socialmei_candidate040;
        GRANT USAGE ON SEQUENCE socialmei.ig_inbound_media_id_seq TO socialmei_candidate040;
    END IF;
END
$grants$;
