-- Least-privileged report collaborators are distinct from broader CRM viewers.
ALTER TABLE socialmei.workspace_members
    DROP CONSTRAINT IF EXISTS workspace_members_role_check;
ALTER TABLE socialmei.workspace_members
    ADD CONSTRAINT workspace_members_role_check
    CHECK (role IN ('owner','admin','member','viewer','report_viewer'));
