-- Optional user-facing multiplier. The real billing multiplier remains groups.rate_multiplier.
ALTER TABLE groups
    ADD COLUMN IF NOT EXISTS display_rate_multiplier DECIMAL(10,4) NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'groups_display_rate_multiplier_positive'
          AND conrelid = 'groups'::regclass
    ) THEN
        ALTER TABLE groups
            ADD CONSTRAINT groups_display_rate_multiplier_positive
            CHECK (display_rate_multiplier IS NULL OR display_rate_multiplier > 0);
    END IF;
END $$;

COMMENT ON COLUMN groups.display_rate_multiplier IS
    'User-facing multiplier override; NULL follows rate_multiplier and never affects billing';
