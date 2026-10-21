-- Non-sensitive user-reported preparation only; never an authorized connection.
CREATE TABLE IF NOT EXISTS socialmei.integration_setup (
    workspace_id BIGINT PRIMARY KEY REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision > 0 AND revision <= 9007199254740991),
    instagram JSONB NOT NULL CHECK (
        jsonb_typeof(instagram) = 'object'
        AND octet_length(instagram::text) <= 8192
        AND instagram ?& ARRAY['username','account_type','meta_app_status','test_participants','reply_mode']
        AND (instagram - ARRAY['username','account_type','meta_app_status','test_participants','reply_mode']) = '{}'::jsonb
        AND instagram->>'reply_mode' = 'review'
        AND instagram->>'account_type' IN ('unknown','business','creator')
        AND instagram->>'meta_app_status' IN ('unknown','exists','not_created')
        AND jsonb_typeof(instagram->'test_participants') = 'array'
        AND jsonb_array_length(instagram->'test_participants') <= 10
    ),
    updated_by BIGINT NOT NULL REFERENCES socialmei.users(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
