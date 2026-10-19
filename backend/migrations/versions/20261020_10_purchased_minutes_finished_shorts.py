"""Snapshot purchased allowances; separate source minutes from completed Short credits.

Revision ID: 20261020_10
Revises: 20261019_09

Existing paid purchases and old-price subscriptions are preserved. New passes
and new-price subscriptions use 25/120/300/600 source minutes and first-successful-
export Short credits. No payment provider or production data is altered by the
migration beyond these entitlement snapshots and safe accounting functions.
"""
from alembic import op

revision = "20261020_10"
down_revision = "20261019_09"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS billing_plan_versions (
      provider_plan_id TEXT PRIMARY KEY,
      plan_key TEXT NOT NULL,
      amount INTEGER NOT NULL,
      currency TEXT NOT NULL DEFAULT 'INR',
      created_at TEXT NOT NULL
    );
    INSERT INTO billing_plan_versions(provider_plan_id,plan_key,amount,currency,created_at)
    SELECT provider_plan_id,plan_key,amount,currency,created_at FROM billing_plans
    WHERE TRUE ON CONFLICT(provider_plan_id) DO NOTHING;

    CREATE TABLE IF NOT EXISTS legacy_billing_subscriptions (
      subscription_id TEXT PRIMARY KEY,
      plan_key TEXT NOT NULL
    );
    INSERT INTO legacy_billing_subscriptions(subscription_id,plan_key)
    SELECT DISTINCT billing_reference,plan FROM users
    WHERE plan IN ('creator','growth','pro') AND billing_reference LIKE 'sub_%'
    ON CONFLICT(subscription_id) DO NOTHING;

    CREATE TABLE IF NOT EXISTS checkout_entitlement_snapshots (
      checkout_id TEXT PRIMARY KEY REFERENCES billing_checkouts(id) ON DELETE CASCADE,
      processing_minutes DOUBLE PRECISION NOT NULL,
      shorts INTEGER NOT NULL,
      source_video_limit_minutes DOUBLE PRECISION NOT NULL,
      short_mode TEXT NOT NULL CHECK(short_mode IN ('source_projects','finished_shorts')),
      price_paise INTEGER NOT NULL, created_at TEXT NOT NULL
    );
    -- Old checkouts still awaiting signed capture confirmation must deliver
    -- the offer that was originally purchased, even after the pricing cutover.
    INSERT INTO checkout_entitlement_snapshots
      (checkout_id,processing_minutes,shorts,source_video_limit_minutes,
       short_mode,price_paise,created_at)
    SELECT id, CASE plan WHEN 'mini_pass' THEN 125 WHEN 'creator' THEN 60
      WHEN 'growth' THEN 180 WHEN 'pro' THEN 480 ELSE 1500 END,
      CASE plan WHEN 'mini_pass' THEN 5 WHEN 'creator' THEN 15
        WHEN 'growth' THEN 50 WHEN 'pro' THEN 150 ELSE 500 END,
      CASE plan WHEN 'mini_pass' THEN 25 WHEN 'creator' THEN 60
        WHEN 'growth' THEN 180 WHEN 'pro' THEN 240 ELSE 240 END,
      'source_projects', amount, created_at FROM billing_checkouts
    WHERE status IN ('created','authorized')
      AND plan IN ('mini_pass','creator','growth','pro','agency')
    ON CONFLICT(checkout_id) DO NOTHING;

    CREATE TABLE IF NOT EXISTS short_credit_reservations (
      clip_id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      period_key TEXT NOT NULL,
      export_id TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('reserved','finalized','released')),
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_short_credit_period
      ON short_credit_reservations(user_id,period_key,status);
    CREATE TABLE IF NOT EXISTS plan_entitlement_snapshots (
      user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      period_key TEXT NOT NULL,
      plan_key TEXT NOT NULL,
      processing_minutes DOUBLE PRECISION NOT NULL CHECK(processing_minutes>0),
      shorts INTEGER NOT NULL CHECK(shorts>0),
      source_video_limit_minutes DOUBLE PRECISION NOT NULL CHECK(source_video_limit_minutes>0),
      short_mode TEXT NOT NULL CHECK(short_mode IN ('source_projects','finished_shorts')),
      price_paise INTEGER NOT NULL CHECK(price_paise>=0),
      created_at TEXT NOT NULL,
      PRIMARY KEY (user_id, period_key)
    );

    -- A paid customer has bought their existing current-period rights.
    -- Do not silently turn a 125m Mini Pass into 25m or change live renewals.
    INSERT INTO plan_entitlement_snapshots
      (user_id,period_key,plan_key,processing_minutes,shorts,
       source_video_limit_minutes,short_mode,price_paise,created_at)
    SELECT u.id,clipkaro_period(u),u.plan,
      CASE u.plan WHEN 'mini_pass' THEN 125 WHEN 'creator' THEN 60
           WHEN 'growth' THEN 180 WHEN 'pro' THEN 480 ELSE 1500 END,
      clipkaro_short_limit(u.plan),
      CASE u.plan WHEN 'mini_pass' THEN 25 WHEN 'creator' THEN 60
           WHEN 'growth' THEN 180 WHEN 'pro' THEN 240 ELSE 240 END,
      'source_projects',
      CASE u.plan WHEN 'mini_pass' THEN 5900 WHEN 'creator' THEN 19900
           WHEN 'growth' THEN 39900 WHEN 'pro' THEN 79900 ELSE 199900 END,
      CURRENT_TIMESTAMP::text
    FROM users u
    WHERE u.plan IN ('mini_pass','creator','growth','pro')
      AND u.billing_reference IS NOT NULL
    ON CONFLICT(user_id,period_key) DO NOTHING;

    CREATE OR REPLACE FUNCTION clipkaro_minute_limit(plan_name TEXT)
    RETURNS DOUBLE PRECISION LANGUAGE SQL IMMUTABLE AS $$
      SELECT CASE plan_name
        WHEN 'mini_pass' THEN 25 WHEN 'creator' THEN 120
        WHEN 'growth' THEN 300 WHEN 'pro' THEN 600
        WHEN 'agency' THEN 1500 ELSE 15 END
    $$;

    CREATE OR REPLACE FUNCTION reserve_video_minutes()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    DECLARE
      owner users%ROWTYPE;
      period TEXT;
      amount DOUBLE PRECISION;
      max_minutes DOUBLE PRECISION;
      short_mode TEXT;
      short_limit INTEGER;
      used_sources INTEGER;
    BEGIN
      IF NEW.status <> 'validated' OR OLD.status = 'validated' OR NEW.duration <= 0 THEN RETURN NEW; END IF;
      IF EXISTS(SELECT 1 FROM usage_reservations
                WHERE kind='minutes' AND resource_id=NEW.project_id
                  AND status IN ('reserved','finalized')) THEN RETURN NEW; END IF;

      SELECT u.* INTO owner FROM users u JOIN projects p ON p.user_id=u.id
      WHERE p.id=NEW.project_id FOR UPDATE;
      period := clipkaro_period(owner);
      amount := NEW.duration / 60.0;
      SELECT COALESCE(s.processing_minutes,clipkaro_minute_limit(owner.plan)),
             COALESCE(s.short_mode,'source_projects'),
             COALESCE(s.shorts,clipkaro_short_limit(owner.plan))
      INTO max_minutes,short_mode,short_limit
      FROM (SELECT 1) anchor LEFT JOIN plan_entitlement_snapshots s
        ON s.user_id=owner.id AND s.period_key=period;

      IF short_mode='source_projects' THEN
        SELECT COUNT(DISTINCT resource_id) INTO used_sources
        FROM usage_reservations
        WHERE user_id=owner.id AND period_key=period
          AND kind='minutes' AND status IN ('reserved','finalized');
        IF used_sources >= short_limit THEN RAISE EXCEPTION 'AI_SHORT_QUOTA_EXCEEDED'; END IF;
      END IF;
      INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit)
      VALUES(gen_random_uuid()::text,owner.id,period,0,0,short_limit)
      ON CONFLICT(user_id,month) DO NOTHING;
      UPDATE usage SET source_minutes=source_minutes+amount,exports_limit=short_limit
      WHERE user_id=owner.id AND month=period AND source_minutes+amount<=max_minutes+0.0000001;
      IF NOT FOUND THEN RAISE EXCEPTION 'KARO_MINUTES_QUOTA_EXCEEDED'; END IF;
      INSERT INTO usage_reservations
      VALUES(gen_random_uuid()::text,owner.id,period,'minutes',amount,NEW.project_id,
             'reserved',CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text);
      RETURN NEW;
    END $$;

    CREATE OR REPLACE FUNCTION reserve_export_slot()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    DECLARE
      owner users%ROWTYPE;
      period TEXT;
      mode TEXT;
      short_limit INTEGER;
      used_shorts INTEGER;
      existing_short short_credit_reservations%ROWTYPE;
    BEGIN
      SELECT * INTO owner FROM users WHERE id=NEW.user_id FOR UPDATE;
      period := clipkaro_period(owner);

      IF owner.plan='free' THEN
        INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit)
        VALUES(gen_random_uuid()::text,owner.id,period,0,0,clipkaro_export_limit(owner.plan))
        ON CONFLICT(user_id,month) DO NOTHING;
        UPDATE usage SET exports_used=exports_used+1,
            exports_limit=clipkaro_export_limit(owner.plan)
        WHERE user_id=owner.id AND month=period
          AND exports_used<clipkaro_export_limit(owner.plan);
        IF NOT FOUND THEN RAISE EXCEPTION 'SHORT_EXPORT_QUOTA_EXCEEDED'; END IF;
        INSERT INTO usage_reservations
        VALUES(gen_random_uuid()::text,owner.id,period,'export',1,NEW.id,
               'reserved',CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text);
        RETURN NEW;
      END IF;

      SELECT COALESCE(s.short_mode,'source_projects'),
             COALESCE(s.shorts,clipkaro_short_limit(owner.plan))
      INTO mode,short_limit
      FROM (SELECT 1) anchor LEFT JOIN plan_entitlement_snapshots s
      ON s.user_id=owner.id AND s.period_key=period;
      IF mode <> 'finished_shorts' THEN RETURN NEW; END IF;

      SELECT * INTO existing_short FROM short_credit_reservations
      WHERE clip_id=NEW.clip_id;
      IF FOUND AND existing_short.user_id<>owner.id THEN
        RAISE EXCEPTION 'AI_SHORT_OWNERSHIP_MISMATCH';
      END IF;
      IF existing_short.status='finalized'
         OR EXISTS(SELECT 1 FROM exports e
                   WHERE e.user_id=owner.id AND e.clip_id=NEW.clip_id AND e.status='ready')
      THEN RETURN NEW; END IF;
      IF existing_short.status='reserved' THEN
        RAISE EXCEPTION 'SHORT_RENDER_ALREADY_RESERVED';
      END IF;

      SELECT COUNT(*) INTO used_shorts
      FROM short_credit_reservations WHERE user_id=owner.id AND period_key=period
        AND status IN ('reserved','finalized');
      IF used_shorts >= short_limit THEN RAISE EXCEPTION 'AI_SHORT_QUOTA_EXCEEDED'; END IF;

      INSERT INTO short_credit_reservations
        (clip_id,user_id,period_key,export_id,status,created_at,updated_at)
      VALUES(NEW.clip_id,owner.id,period,NEW.id,'reserved',
             CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text)
      ON CONFLICT (clip_id) DO UPDATE SET
        period_key=EXCLUDED.period_key,export_id=EXCLUDED.export_id,status='reserved',
        updated_at=EXCLUDED.updated_at
      WHERE short_credit_reservations.status='released'
        AND short_credit_reservations.user_id=EXCLUDED.user_id;
      RETURN NEW;
    END $$;

    -- Previous settlement handles project minutes and Free export slots.
    -- This added trigger finalizes/refunds paid, clip-scoped Short credits.
    CREATE OR REPLACE FUNCTION settle_paid_short_slot()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.status='ready' AND OLD.status IS DISTINCT FROM NEW.status THEN
        UPDATE short_credit_reservations SET status='finalized',updated_at=CURRENT_TIMESTAMP::text
        WHERE user_id=NEW.user_id AND clip_id=NEW.clip_id AND export_id=NEW.id
          AND status='reserved';
      ELSIF NEW.status IN ('failed','expired') AND OLD.status IS DISTINCT FROM NEW.status THEN
        UPDATE short_credit_reservations SET status='released',updated_at=CURRENT_TIMESTAMP::text
        WHERE user_id=NEW.user_id AND clip_id=NEW.clip_id AND export_id=NEW.id
          AND status='reserved';
      END IF;
      RETURN NEW;
    END $$;
    DROP TRIGGER IF EXISTS trg_settle_paid_short_slot ON exports;
    CREATE TRIGGER trg_settle_paid_short_slot AFTER UPDATE OF status ON exports
      FOR EACH ROW EXECUTE FUNCTION settle_paid_short_slot();

    CREATE OR REPLACE FUNCTION release_deleted_paid_short()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
      UPDATE short_credit_reservations SET status='released',updated_at=CURRENT_TIMESTAMP::text
      WHERE user_id=OLD.user_id AND clip_id=OLD.clip_id AND export_id=OLD.id
        AND status='reserved';
      RETURN OLD;
    END $$;
    DROP TRIGGER IF EXISTS trg_release_deleted_paid_short ON exports;
    CREATE TRIGGER trg_release_deleted_paid_short BEFORE DELETE ON exports
      FOR EACH ROW EXECUTE FUNCTION release_deleted_paid_short();
    """)

def downgrade() -> None:
    raise RuntimeError(
        "Purchased entitlement snapshots must not be silently rolled back. "
        "Restore an approved database snapshot with a compatible application."
    )
