ALTER TABLE groups
    ADD COLUMN IF NOT EXISTS force_openai_ultrafast BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN groups.force_openai_ultrafast IS
    'Bill OpenAI requests in this group at the Ultrafast (6x) tier even when the upstream reports a cheaper service_tier';
