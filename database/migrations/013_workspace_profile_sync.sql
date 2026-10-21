-- Workspace onboarding and each membership's non-sensitive UI preferences.
CREATE TABLE IF NOT EXISTS socialmei.workspace_profiles (
    workspace_id BIGINT PRIMARY KEY REFERENCES socialmei.workspaces(id) ON DELETE CASCADE,
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision > 0 AND revision <= 9007199254740991),
    profile JSONB NOT NULL CHECK (jsonb_typeof(profile) = 'object' AND profile ? 'version' AND profile->'version' = '1'::jsonb AND octet_length(profile::text) <= 65536),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS socialmei.auth_preferences (
    workspace_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision > 0 AND revision <= 9007199254740991),
    preferences JSONB NOT NULL CHECK (jsonb_typeof(preferences) = 'object' AND octet_length(preferences::text) <= 2048),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, user_id),
    FOREIGN KEY (workspace_id, user_id) REFERENCES socialmei.workspace_members(workspace_id, user_id) ON DELETE CASCADE
);
