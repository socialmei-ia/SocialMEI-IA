-- Public handles are distinct from bearer/session-token hashes. Existing sessions survive.
ALTER TABLE socialmei.auth_sessoes ADD COLUMN IF NOT EXISTS public_id UUID NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS ux_auth_sessoes_public_id ON socialmei.auth_sessoes(public_id);
COMMENT ON COLUMN socialmei.auth_sessoes.public_id IS 'Non-secret handle for the account owner to list/revoke a session; never accepted for authentication.';
