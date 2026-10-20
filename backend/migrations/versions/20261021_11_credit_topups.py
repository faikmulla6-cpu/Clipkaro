"""Purchased balances preserved separately from immutable plan entitlements."""
from alembic import op
revision = "20261021_11"
down_revision = "20261020_10"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS credit_topup_wallets (
       user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
       minutes_balance DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK(minutes_balance >= -0.000001),
       shorts_balance INTEGER NOT NULL DEFAULT 0 CHECK(shorts_balance>=0),
       updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS credit_topup_checkouts (
       id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
       provider_reference TEXT UNIQUE NOT NULL, minutes INTEGER NOT NULL CHECK(minutes>=0),
       shorts INTEGER NOT NULL CHECK(shorts>=0),amount_paise INTEGER NOT NULL CHECK(amount_paise>0),
       status TEXT NOT NULL, payment_id TEXT,created_at TEXT NOT NULL,verified_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_credit_topup_checkouts_user ON credit_topup_checkouts(user_id,created_at DESC);
    CREATE TABLE IF NOT EXISTS credit_topup_spends (
       user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
       kind TEXT NOT NULL CHECK(kind IN ('minutes','shorts')),
       resource_id TEXT NOT NULL, amount DOUBLE PRECISION NOT NULL CHECK(amount>0),
       status TEXT NOT NULL CHECK(status IN ('reserved','finalized','released')),
       created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
       PRIMARY KEY(kind,resource_id)
    );
    CREATE INDEX IF NOT EXISTS idx_credit_topup_spends_user ON credit_topup_spends(user_id,status);
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
      used_minutes DOUBLE PRECISION;
      extra_minutes DOUBLE PRECISION;
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
        IF used_sources >= short_limit THEN
          IF owner.plan NOT IN ('creator','growth','pro','agency') THEN RAISE EXCEPTION 'AI_SHORT_QUOTA_EXCEEDED'; END IF;
          UPDATE credit_topup_wallets SET shorts_balance=shorts_balance-1,updated_at=CURRENT_TIMESTAMP::text
          WHERE user_id=owner.id AND shorts_balance>=1;
          IF NOT FOUND THEN RAISE EXCEPTION 'AI_SHORT_QUOTA_EXCEEDED'; END IF;
          INSERT INTO credit_topup_spends (user_id,kind,resource_id,amount,status,created_at,updated_at)
          VALUES(owner.id,'shorts',NEW.project_id,1,'reserved',CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text)
          ON CONFLICT(kind,resource_id) DO UPDATE SET status='reserved',updated_at=EXCLUDED.updated_at
          WHERE credit_topup_spends.status='released' AND credit_topup_spends.user_id=EXCLUDED.user_id;
          IF NOT FOUND THEN RAISE EXCEPTION 'AI_SHORT_TOPUP_ALREADY_RESERVED'; END IF;
        END IF;
      END IF;
      INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit)
      VALUES(gen_random_uuid()::text,owner.id,period,0,0,short_limit)
      ON CONFLICT(user_id,month) DO NOTHING;
      SELECT source_minutes INTO used_minutes FROM usage WHERE user_id=owner.id AND month=period FOR UPDATE;
      extra_minutes := GREATEST(0,used_minutes+amount-max_minutes)-GREATEST(0,used_minutes-max_minutes);
      IF extra_minutes>0.0000001 THEN
        IF owner.plan NOT IN ('creator','growth','pro','agency') THEN RAISE EXCEPTION 'KARO_MINUTES_QUOTA_EXCEEDED'; END IF;
        UPDATE credit_topup_wallets SET minutes_balance=minutes_balance-extra_minutes,
          updated_at=CURRENT_TIMESTAMP::text WHERE user_id=owner.id
            AND minutes_balance+0.0000001>=extra_minutes;
        IF NOT FOUND THEN RAISE EXCEPTION 'KARO_MINUTES_QUOTA_EXCEEDED'; END IF;
        INSERT INTO credit_topup_spends (user_id,kind,resource_id,amount,status,created_at,updated_at)
        VALUES(owner.id,'minutes',NEW.project_id,extra_minutes,'reserved',CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text)
        ON CONFLICT(kind,resource_id) DO UPDATE SET amount=EXCLUDED.amount,status='reserved',updated_at=EXCLUDED.updated_at
        WHERE credit_topup_spends.status='released' AND credit_topup_spends.user_id=EXCLUDED.user_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'KARO_MINUTES_TOPUP_ALREADY_RESERVED'; END IF;
      END IF;
      UPDATE usage SET source_minutes=source_minutes+amount,exports_limit=short_limit
      WHERE user_id=owner.id AND month=period;
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
      IF used_shorts >= short_limit THEN
        UPDATE credit_topup_wallets SET shorts_balance=shorts_balance-1,updated_at=CURRENT_TIMESTAMP::text
          WHERE user_id=owner.id AND shorts_balance>=1;
        IF NOT FOUND THEN RAISE EXCEPTION 'AI_SHORT_QUOTA_EXCEEDED'; END IF;
        INSERT INTO credit_topup_spends (user_id,kind,resource_id,amount,status,created_at,updated_at)
        VALUES(owner.id,'shorts',NEW.id,1,'reserved',CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text)
        ON CONFLICT(kind,resource_id) DO UPDATE SET status='reserved',updated_at=EXCLUDED.updated_at
        WHERE credit_topup_spends.status='released' AND credit_topup_spends.user_id=EXCLUDED.user_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'AI_SHORT_TOPUP_ALREADY_RESERVED'; END IF;
      END IF;

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


    -- Refund only unfinalized reservations. Settlement is safe under retries.
    CREATE OR REPLACE FUNCTION settle_purchased_credits()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    DECLARE identity TEXT; item credit_topup_spends%ROWTYPE;
    BEGIN
      identity := CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
      IF TG_OP='DELETE' OR (NEW.status IN ('failed','expired') AND OLD.status IS DISTINCT FROM NEW.status) THEN
        FOR item IN SELECT * FROM credit_topup_spends WHERE resource_id=identity AND status='reserved' FOR UPDATE LOOP
          IF item.kind='minutes' THEN
            UPDATE credit_topup_wallets SET minutes_balance=minutes_balance+item.amount,updated_at=CURRENT_TIMESTAMP::text
            WHERE user_id=item.user_id;
          ELSE
            UPDATE credit_topup_wallets SET shorts_balance=shorts_balance+item.amount::INTEGER,updated_at=CURRENT_TIMESTAMP::text
            WHERE user_id=item.user_id;
          END IF;
          UPDATE credit_topup_spends SET status='released',updated_at=CURRENT_TIMESTAMP::text
          WHERE resource_id=item.resource_id AND kind=item.kind AND status='reserved';
        END LOOP;
      ELSIF TG_OP <> 'DELETE' AND NEW.status IN ('ready','completed') AND OLD.status IS DISTINCT FROM NEW.status THEN
        UPDATE credit_topup_spends SET status='finalized',updated_at=CURRENT_TIMESTAMP::text
          WHERE resource_id=identity AND status='reserved';
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$;
    DROP TRIGGER IF EXISTS trg_settle_purchased_project ON projects;
    CREATE TRIGGER trg_settle_purchased_project AFTER UPDATE OF status ON projects
       FOR EACH ROW EXECUTE FUNCTION settle_purchased_credits();
    DROP TRIGGER IF EXISTS trg_delete_purchased_project ON projects;
    CREATE TRIGGER trg_delete_purchased_project BEFORE DELETE ON projects
       FOR EACH ROW EXECUTE FUNCTION settle_purchased_credits();
    DROP TRIGGER IF EXISTS trg_settle_purchased_export ON exports;
    CREATE TRIGGER trg_settle_purchased_export AFTER UPDATE OF status ON exports
       FOR EACH ROW EXECUTE FUNCTION settle_purchased_credits();
    DROP TRIGGER IF EXISTS trg_delete_purchased_export ON exports;
    CREATE TRIGGER trg_delete_purchased_export BEFORE DELETE ON exports
       FOR EACH ROW EXECUTE FUNCTION settle_purchased_credits();
    """)

def downgrade() -> None:
    raise RuntimeError("Purchased credit balances cannot be safely rolled back.")
