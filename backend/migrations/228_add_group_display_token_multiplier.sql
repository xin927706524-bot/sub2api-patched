-- Optional user-facing Token multiplier. Stored usage and billing remain unchanged.
ALTER TABLE groups
    ADD COLUMN IF NOT EXISTS display_token_multiplier DECIMAL(10,4) NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'groups_display_token_multiplier_positive'
          AND conrelid = 'groups'::regclass
    ) THEN
        ALTER TABLE groups
            ADD CONSTRAINT groups_display_token_multiplier_positive
            CHECK (display_token_multiplier IS NULL OR display_token_multiplier > 0);
    END IF;
END $$;

COMMENT ON COLUMN groups.display_token_multiplier IS
    'User-facing usage-log Token multiplier; NULL means 1.0 and never affects stored usage or billing';
