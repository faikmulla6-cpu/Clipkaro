"""Separate AI Short creation credits from paid export renders.

Revision ID: 20261006_08
Revises: 20261005_07
"""

from alembic import op

revision = "20261006_08"
down_revision = "20261005_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION clipkaro_short_limit(plan_name TEXT)
        RETURNS INTEGER
        LANGUAGE SQL
        IMMUTABLE
        AS $$
          SELECT CASE plan_name
            WHEN 'mini_pass' THEN 5
            WHEN 'creator' THEN 15
            WHEN 'growth' THEN 50
            WHEN 'pro' THEN 150
            WHEN 'agency' THEN 500
            ELSE 2
          END
        $$;

        CREATE OR REPLACE FUNCTION reserve_video_minutes()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
          owner users%ROWTYPE;
          period TEXT;
          amount DOUBLE PRECISION;
          used_shorts INTEGER;
        BEGIN
          IF NEW.status <> 'validated' OR OLD.status = 'validated' OR NEW.duration <= 0 THEN
            RETURN NEW;
          END IF;
          IF EXISTS(
            SELECT 1 FROM usage_reservations
            WHERE kind='minutes' AND resource_id=NEW.project_id
              AND status IN ('reserved','finalized')
          ) THEN
            RETURN NEW;
          END IF;

          SELECT u.* INTO owner
          FROM users u JOIN projects p ON p.user_id=u.id
          WHERE p.id=NEW.project_id
          FOR UPDATE;

          period := clipkaro_period(owner);
          amount := NEW.duration / 60.0;

          SELECT COUNT(DISTINCT resource_id) INTO used_shorts
          FROM usage_reservations
          WHERE user_id=owner.id AND period_key=period
            AND kind='minutes' AND status IN ('reserved','finalized');

          IF used_shorts >= clipkaro_short_limit(owner.plan) THEN
            RAISE EXCEPTION 'AI_SHORT_QUOTA_EXCEEDED';
          END IF;

          INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit)
          VALUES(gen_random_uuid()::text,owner.id,period,0,0,clipkaro_short_limit(owner.plan))
          ON CONFLICT(user_id,month) DO NOTHING;

          UPDATE usage
          SET source_minutes=source_minutes+amount,
              exports_limit=clipkaro_short_limit(owner.plan)
          WHERE user_id=owner.id AND month=period
            AND source_minutes+amount<=clipkaro_minute_limit(owner.plan);

          IF NOT FOUND THEN
            RAISE EXCEPTION 'KARO_MINUTES_QUOTA_EXCEEDED';
          END IF;

          INSERT INTO usage_reservations
          VALUES(
            gen_random_uuid()::text,owner.id,period,'minutes',amount,NEW.project_id,
            'reserved',CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text
          );
          RETURN NEW;
        END
        $$;

        CREATE OR REPLACE FUNCTION reserve_export_slot()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
          owner users%ROWTYPE;
          period TEXT;
        BEGIN
          SELECT * INTO owner FROM users WHERE id=NEW.user_id FOR UPDATE;

          -- Paid plans buy creation capacity. Rendering or re-rendering an
          -- already-created Short never consumes another paid credit.
          IF owner.plan <> 'free' THEN
            RETURN NEW;
          END IF;

          period := clipkaro_period(owner);
          INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit)
          VALUES(gen_random_uuid()::text,owner.id,period,0,0,clipkaro_export_limit(owner.plan))
          ON CONFLICT(user_id,month) DO NOTHING;

          UPDATE usage
          SET exports_used=exports_used+1,
              exports_limit=clipkaro_export_limit(owner.plan)
          WHERE user_id=owner.id AND month=period
            AND exports_used<clipkaro_export_limit(owner.plan);

          IF NOT FOUND THEN
            RAISE EXCEPTION 'SHORT_EXPORT_QUOTA_EXCEEDED';
          END IF;

          INSERT INTO usage_reservations
          VALUES(
            gen_random_uuid()::text,owner.id,period,'export',1,NEW.id,
            'reserved',CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text
          );
          RETURN NEW;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reserve_video_minutes()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        DECLARE owner users%ROWTYPE; period TEXT; amount DOUBLE PRECISION;
        BEGIN
          IF NEW.status <> 'validated' OR OLD.status = 'validated' OR NEW.duration <= 0 THEN RETURN NEW; END IF;
          IF EXISTS(SELECT 1 FROM usage_reservations WHERE kind='minutes' AND resource_id=NEW.project_id) THEN RETURN NEW; END IF;
          SELECT u.* INTO owner FROM users u JOIN projects p ON p.user_id=u.id WHERE p.id=NEW.project_id FOR UPDATE;
          period := clipkaro_period(owner); amount := NEW.duration/60.0;
          INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit)
          VALUES(gen_random_uuid()::text,owner.id,period,0,0,clipkaro_export_limit(owner.plan)) ON CONFLICT(user_id,month) DO NOTHING;
          UPDATE usage SET source_minutes=source_minutes+amount,exports_limit=clipkaro_export_limit(owner.plan)
          WHERE user_id=owner.id AND month=period AND source_minutes+amount<=clipkaro_minute_limit(owner.plan);
          IF NOT FOUND THEN RAISE EXCEPTION 'KARO_MINUTES_QUOTA_EXCEEDED'; END IF;
          INSERT INTO usage_reservations VALUES(gen_random_uuid()::text,owner.id,period,'minutes',amount,NEW.project_id,'reserved',CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text);
          RETURN NEW;
        END
        $$;

        CREATE OR REPLACE FUNCTION reserve_export_slot()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        DECLARE owner users%ROWTYPE; period TEXT;
        BEGIN
          SELECT * INTO owner FROM users WHERE id=NEW.user_id FOR UPDATE;
          period := clipkaro_period(owner);
          INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit)
          VALUES(gen_random_uuid()::text,owner.id,period,0,0,clipkaro_export_limit(owner.plan)) ON CONFLICT(user_id,month) DO NOTHING;
          UPDATE usage SET exports_used=exports_used+1,exports_limit=clipkaro_export_limit(owner.plan)
          WHERE user_id=owner.id AND month=period AND exports_used<clipkaro_export_limit(owner.plan);
          IF NOT FOUND THEN RAISE EXCEPTION 'SHORT_EXPORT_QUOTA_EXCEEDED'; END IF;
          INSERT INTO usage_reservations VALUES(gen_random_uuid()::text,owner.id,period,'export',1,NEW.id,'reserved',CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text);
          RETURN NEW;
        END
        $$;
        """
    )
