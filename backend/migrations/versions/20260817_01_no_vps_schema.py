"""ClipKaro no-VPS PostgreSQL baseline.

Revision ID: 20260817_01
"""
from alembic import op

revision = "20260817_01"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = r"""
CREATE TABLE users (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
 plan TEXT NOT NULL DEFAULT 'free', role TEXT NOT NULL DEFAULT 'creator', onboarding_complete INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, billing_reference TEXT, plan_started_at TEXT,
 plan_expires_at TEXT, cancel_at_period_end INTEGER NOT NULL DEFAULT 0, session_version INTEGER NOT NULL DEFAULT 0,
 email_verified_at TEXT
);
CREATE TABLE projects (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, title TEXT NOT NULL,
 description TEXT DEFAULT '', status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, stage TEXT NOT NULL DEFAULT 'created',
 language TEXT DEFAULT 'auto', category TEXT DEFAULT 'auto', error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE videos (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, original_filename TEXT NOT NULL,
 duration DOUBLE PRECISION DEFAULT 0, width INTEGER DEFAULT 0, height INTEGER DEFAULT 0, file_size BIGINT DEFAULT 0,
 file_path TEXT NOT NULL, object_generation TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE transcripts (id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE, language TEXT NOT NULL, text TEXT NOT NULL, segments_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE transcript_corrections (id TEXT PRIMARY KEY,transcript_id TEXT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,segment_index INTEGER NOT NULL,segment_key TEXT NOT NULL,original_text TEXT NOT NULL,corrected_text TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'corrected',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(transcript_id,segment_key));
CREATE TABLE clips (
 id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE, start_time DOUBLE PRECISION NOT NULL,
 end_time DOUBLE PRECISION NOT NULL, hook TEXT NOT NULL, title TEXT NOT NULL, reason TEXT NOT NULL, transcript_text TEXT DEFAULT '',
 score DOUBLE PRECISION NOT NULL, score_breakdown_json TEXT NOT NULL DEFAULT '{}', platform TEXT NOT NULL,
 status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE exports (
 id TEXT PRIMARY KEY, clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 output_path TEXT NOT NULL, object_generation TEXT, resolution TEXT NOT NULL, aspect_ratio TEXT NOT NULL DEFAULT '9:16',
 caption_style TEXT NOT NULL, watermark INTEGER NOT NULL, status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
 error TEXT, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE jobs (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, project_id TEXT, export_id TEXT,
 kind TEXT NOT NULL, status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, stage TEXT NOT NULL, message TEXT NOT NULL,
 error TEXT, failure_category TEXT, attempt_count INTEGER NOT NULL DEFAULT 0, started_at TEXT, heartbeat_at TEXT,
 completed_at TEXT, failed_at TEXT, cloud_run_execution TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE usage (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, month TEXT NOT NULL, source_minutes DOUBLE PRECISION NOT NULL DEFAULT 0, exports_used INTEGER NOT NULL DEFAULT 0, exports_limit INTEGER NOT NULL, UNIQUE(user_id,month));
CREATE TABLE usage_reservations (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, period_key TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('minutes','export')), amount DOUBLE PRECISION NOT NULL CHECK(amount>0), resource_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('reserved','finalized','released')), created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(kind,resource_id)
);
CREATE TABLE brand_kits (id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,name TEXT NOT NULL,primary_color TEXT NOT NULL,accent_color TEXT NOT NULL,font_family TEXT NOT NULL,logo_text TEXT DEFAULT '',caption_preset TEXT NOT NULL DEFAULT 'kinetic',is_default INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE scheduled_posts (id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,export_id TEXT NOT NULL REFERENCES exports(id) ON DELETE CASCADE,platform TEXT NOT NULL,caption TEXT NOT NULL,hashtags TEXT NOT NULL DEFAULT '',scheduled_for TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',created_at TEXT NOT NULL);
CREATE TABLE content_packs (id TEXT PRIMARY KEY,project_id TEXT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,status TEXT NOT NULL,payload_json TEXT NOT NULL DEFAULT '{}',provider TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE audit_events (id TEXT PRIMARY KEY,user_id TEXT,event TEXT NOT NULL,entity_type TEXT,entity_id TEXT,metadata_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL);
CREATE TABLE payment_events (id TEXT PRIMARY KEY,provider_event_id TEXT UNIQUE NOT NULL,user_id TEXT,event_type TEXT NOT NULL,plan TEXT,amount INTEGER DEFAULT 0,status TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE billing_plans (plan_key TEXT PRIMARY KEY,provider_plan_id TEXT UNIQUE NOT NULL,amount INTEGER NOT NULL,currency TEXT NOT NULL DEFAULT 'INR',created_at TEXT NOT NULL);
CREATE TABLE billing_checkouts (id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,kind TEXT NOT NULL,plan TEXT NOT NULL,provider_reference TEXT UNIQUE NOT NULL,amount INTEGER NOT NULL,status TEXT NOT NULL,payment_id TEXT,created_at TEXT NOT NULL,verified_at TEXT);
CREATE UNIQUE INDEX uq_active_checkout_per_user ON billing_checkouts(user_id,kind,plan) WHERE status IN ('created','authorized');
CREATE TABLE subscription_plan_changes (user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,subscription_id TEXT NOT NULL,from_plan TEXT NOT NULL,to_plan TEXT NOT NULL,change_kind TEXT NOT NULL CHECK(change_kind IN ('downgrade','cancel')),provider_plan_id TEXT,effective_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE billing_webhook_state (subscription_id TEXT PRIMARY KEY,last_event_created_at BIGINT NOT NULL DEFAULT 0,last_event_id TEXT,terminal INTEGER NOT NULL DEFAULT 0 CHECK(terminal IN (0,1)),last_status TEXT,updated_at TEXT NOT NULL);
CREATE TABLE job_payloads (job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,payload_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE job_claims (job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,worker_id TEXT NOT NULL,claimed_at TEXT NOT NULL,heartbeat_at TEXT NOT NULL,attempt_count INTEGER NOT NULL DEFAULT 1,cloud_run_execution TEXT);
CREATE TABLE worker_runtime_state (id INTEGER PRIMARY KEY CHECK(id=1),worker_id TEXT NOT NULL,status TEXT NOT NULL,started_at TEXT NOT NULL,heartbeat_at TEXT NOT NULL,capabilities_json TEXT NOT NULL DEFAULT '{}',last_error_code TEXT NOT NULL DEFAULT '');
CREATE TABLE auth_sessions (id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,session_version INTEGER NOT NULL,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,revoked_at TEXT,user_agent TEXT NOT NULL DEFAULT '',client_fingerprint TEXT NOT NULL DEFAULT '');
CREATE TABLE password_resets (user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,token_hash TEXT UNIQUE NOT NULL,expires_at TEXT NOT NULL,last_sent_at TEXT NOT NULL,send_window_started_at TEXT NOT NULL,send_count INTEGER NOT NULL DEFAULT 1,consumed_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE email_verifications (user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,token_hash TEXT UNIQUE NOT NULL,expires_at TEXT NOT NULL,last_sent_at TEXT NOT NULL,send_window_started_at TEXT NOT NULL,send_count INTEGER NOT NULL DEFAULT 1,consumed_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE user_preferences (user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,default_language TEXT NOT NULL DEFAULT 'auto',timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',creator_category TEXT NOT NULL DEFAULT 'auto',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE upload_sessions (
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,object_key TEXT UNIQUE NOT NULL,
 original_filename TEXT NOT NULL,expected_size BIGINT NOT NULL CHECK(expected_size>0),expected_content_type TEXT NOT NULL,
 object_generation TEXT,status TEXT NOT NULL CHECK(status IN ('initiated','uploaded','consumed','expired','rejected')),
 title TEXT NOT NULL,language TEXT NOT NULL,category TEXT NOT NULL,project_id TEXT,job_id TEXT,
 expires_at TEXT NOT NULL,created_at TEXT NOT NULL,consumed_at TEXT
);
CREATE TABLE security_rate_limits (bucket_key TEXT PRIMARY KEY,window_started_at TEXT NOT NULL,request_count INTEGER NOT NULL CHECK(request_count>=0),updated_at TEXT NOT NULL);
CREATE TABLE legal_acceptances (id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,version TEXT NOT NULL,documents_json TEXT NOT NULL,source TEXT NOT NULL,user_agent TEXT NOT NULL DEFAULT '',accepted_at TEXT NOT NULL,UNIQUE(user_id,version));
CREATE TABLE privacy_requests (id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,kind TEXT NOT NULL CHECK(kind IN ('access','correction','deletion','grievance')),status TEXT NOT NULL CHECK(status IN ('received','in_review','completed','rejected')),details TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE legal_launch_state (id INTEGER PRIMARY KEY CHECK(id=1),enforcement_enabled INTEGER NOT NULL,paid_launch_ready INTEGER NOT NULL,version TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE recommendation_generations (id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,language TEXT NOT NULL,category TEXT NOT NULL,ranking_source TEXT NOT NULL,ranking_model TEXT NOT NULL,app_version TEXT NOT NULL,pipeline_version TEXT NOT NULL,clip_count INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(video_id,created_at));
CREATE TABLE clip_suggestion_snapshots (id TEXT PRIMARY KEY,generation_id TEXT NOT NULL REFERENCES recommendation_generations(id) ON DELETE CASCADE,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,clip_id TEXT NOT NULL,suggestion_rank INTEGER NOT NULL CHECK(suggestion_rank>0),start_time DOUBLE PRECISION NOT NULL,end_time DOUBLE PRECISION NOT NULL,duration DOUBLE PRECISION NOT NULL,score DOUBLE PRECISION NOT NULL,score_breakdown_json TEXT NOT NULL,platform TEXT NOT NULL,ranking_source TEXT NOT NULL,ranking_model TEXT NOT NULL,language TEXT NOT NULL,category TEXT NOT NULL,app_version TEXT NOT NULL,pipeline_version TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(generation_id,clip_id),UNIQUE(generation_id,suggestion_rank));
CREATE TABLE clip_behavior_events (id TEXT PRIMARY KEY,event_key TEXT UNIQUE NOT NULL,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,clip_id TEXT NOT NULL,generation_id TEXT NOT NULL REFERENCES recommendation_generations(id) ON DELETE CASCADE,event_type TEXT NOT NULL CHECK(event_type IN ('impression','preview_started','selected','edited','export_requested','export_ready','export_failed','downloaded')),source TEXT NOT NULL CHECK(source IN ('frontend','server')),client_session_id TEXT,context_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL);
CREATE INDEX idx_projects_user ON projects(user_id,updated_at DESC); CREATE INDEX idx_videos_project ON videos(project_id);
CREATE INDEX idx_transcript_corrections_project ON transcript_corrections(project_id,updated_at DESC);
CREATE INDEX idx_clips_video ON clips(video_id,score DESC); CREATE INDEX idx_exports_user ON exports(user_id,created_at DESC);
CREATE INDEX idx_content_packs_project ON content_packs(project_id);
CREATE INDEX idx_jobs_user ON jobs(user_id,updated_at DESC); CREATE INDEX idx_jobs_claimable ON jobs(status,kind,created_at);
CREATE INDEX idx_usage_reservation_period ON usage_reservations(user_id,period_key,kind,status);
CREATE INDEX idx_upload_sessions_user ON upload_sessions(user_id,created_at DESC);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id,revoked_at,expires_at);
CREATE INDEX idx_password_reset_expiry ON password_resets(expires_at,consumed_at);
CREATE INDEX idx_email_verification_expiry ON email_verifications(expires_at,consumed_at);
CREATE INDEX idx_legal_acceptances_user ON legal_acceptances(user_id,accepted_at DESC);
CREATE INDEX idx_privacy_requests_user ON privacy_requests(user_id,created_at DESC);
CREATE INDEX idx_recommendation_generation_project ON recommendation_generations(project_id,created_at DESC);
CREATE INDEX idx_suggestion_snapshot_clip ON clip_suggestion_snapshots(clip_id,created_at DESC);
CREATE INDEX idx_behavior_user_created ON clip_behavior_events(user_id,created_at DESC);
CREATE INDEX idx_behavior_generation_type ON clip_behavior_events(generation_id,event_type,created_at);
CREATE INDEX idx_behavior_clip_type ON clip_behavior_events(clip_id,event_type,created_at);

CREATE FUNCTION capture_clip_suggestion() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE generation TEXT;
BEGIN
 INSERT INTO recommendation_generations(
   id,user_id,project_id,video_id,language,category,ranking_source,ranking_model,
   app_version,pipeline_version,clip_count,created_at
 )
 SELECT gen_random_uuid()::text,p.user_id,p.id,NEW.video_id,
   COALESCE((SELECT language FROM transcripts WHERE video_id=NEW.video_id ORDER BY created_at DESC LIMIT 1),p.language,'unknown'),
   COALESCE(p.category,'auto'),'pending','pending','7.8.0','7.8.0',0,NEW.created_at
 FROM videos v JOIN projects p ON p.id=v.project_id WHERE v.id=NEW.video_id
 ON CONFLICT DO NOTHING;
 SELECT id INTO generation FROM recommendation_generations
  WHERE video_id=NEW.video_id AND created_at=NEW.created_at ORDER BY id LIMIT 1 FOR UPDATE;
 IF generation IS NULL THEN RAISE EXCEPTION 'RECOMMENDATION_GENERATION_MISSING'; END IF;
 UPDATE recommendation_generations SET clip_count=clip_count+1 WHERE id=generation;
 INSERT INTO clip_suggestion_snapshots(
   id,generation_id,user_id,project_id,video_id,clip_id,suggestion_rank,start_time,end_time,duration,
   score,score_breakdown_json,platform,ranking_source,ranking_model,language,category,app_version,pipeline_version,created_at
 )
 SELECT gen_random_uuid()::text,g.id,g.user_id,g.project_id,g.video_id,NEW.id,
   (SELECT COUNT(*)+1 FROM clip_suggestion_snapshots x WHERE x.generation_id=g.id),
   NEW.start_time,NEW.end_time,GREATEST(0,NEW.end_time-NEW.start_time),NEW.score,
   NEW.score_breakdown_json,NEW.platform,g.ranking_source,g.ranking_model,g.language,g.category,
   g.app_version,g.pipeline_version,NEW.created_at
 FROM recommendation_generations g WHERE g.id=generation;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_learning_capture_clip_suggestion AFTER INSERT ON clips FOR EACH ROW EXECUTE FUNCTION capture_clip_suggestion();

CREATE FUNCTION capture_ranking_source() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE generation TEXT; source_name TEXT;
BEGIN
 IF NEW.event<>'project.processed' OR NEW.entity_type<>'project' THEN RETURN NEW; END IF;
 SELECT id INTO generation FROM recommendation_generations WHERE project_id=NEW.entity_id ORDER BY created_at DESC LIMIT 1;
 source_name := COALESCE((NEW.metadata_json::jsonb)->>'ranking_source','local');
 UPDATE recommendation_generations SET ranking_source=source_name,
   ranking_model=CASE WHEN source_name='groq' THEN 'groq-configured' ELSE 'deterministic-local' END
   WHERE id=generation;
 UPDATE clip_suggestion_snapshots s SET ranking_source=g.ranking_source,ranking_model=g.ranking_model
   FROM recommendation_generations g WHERE s.generation_id=generation AND g.id=generation;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_learning_capture_ranking_source AFTER INSERT ON audit_events FOR EACH ROW EXECUTE FUNCTION capture_ranking_source();

CREATE FUNCTION capture_export_behavior() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE event_name TEXT; event_time TEXT;
BEGIN
 IF TG_OP='INSERT' THEN
   event_name := 'export_requested'; event_time := NEW.created_at;
 ELSIF NEW.status='ready' AND OLD.status IS DISTINCT FROM 'ready' THEN
   event_name := 'export_ready'; event_time := CURRENT_TIMESTAMP::text;
 ELSIF NEW.status='failed' AND OLD.status IS DISTINCT FROM 'failed' THEN
   event_name := 'export_failed'; event_time := CURRENT_TIMESTAMP::text;
 ELSE RETURN NEW;
 END IF;
 INSERT INTO clip_behavior_events(
   id,event_key,user_id,project_id,video_id,clip_id,generation_id,event_type,source,client_session_id,context_json,created_at
 )
 SELECT gen_random_uuid()::text,'server:'||event_name||':'||NEW.id,s.user_id,s.project_id,s.video_id,s.clip_id,
   s.generation_id,event_name,'server',NULL,'{}',event_time
 FROM clip_suggestion_snapshots s WHERE s.clip_id=NEW.clip_id ORDER BY s.created_at DESC LIMIT 1
 ON CONFLICT(event_key) DO NOTHING;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_learning_export_requested AFTER INSERT ON exports FOR EACH ROW EXECUTE FUNCTION capture_export_behavior();
CREATE TRIGGER trg_learning_export_outcome AFTER UPDATE OF status ON exports FOR EACH ROW EXECUTE FUNCTION capture_export_behavior();

CREATE FUNCTION clipkaro_period(p users) RETURNS TEXT LANGUAGE SQL STABLE AS $$
 SELECT CASE WHEN p.plan='free' THEN 'free:' || to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM')
 ELSE p.plan || ':' || COALESCE(NULLIF(p.billing_reference,''),p.id,'local') || ':' ||
      substring(COALESCE(p.plan_started_at,to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM')) from 1 for 19) END
$$;
CREATE FUNCTION clipkaro_export_limit(plan_name TEXT) RETURNS INTEGER LANGUAGE SQL IMMUTABLE AS $$
 SELECT CASE plan_name WHEN 'mini_pass' THEN 5 WHEN 'creator' THEN 15 WHEN 'growth' THEN 50 WHEN 'pro' THEN 150 WHEN 'agency' THEN 500 ELSE 2 END
$$;
CREATE FUNCTION clipkaro_minute_limit(plan_name TEXT) RETURNS DOUBLE PRECISION LANGUAGE SQL IMMUTABLE AS $$
 SELECT CASE plan_name WHEN 'mini_pass' THEN 25 WHEN 'creator' THEN 60 WHEN 'growth' THEN 180 WHEN 'pro' THEN 480 WHEN 'agency' THEN 1500 ELSE 15 END
$$;
CREATE FUNCTION reserve_video_minutes() RETURNS TRIGGER LANGUAGE plpgsql AS $$
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
END $$;
CREATE TRIGGER trg_reserve_video_minutes BEFORE UPDATE OF status ON videos FOR EACH ROW EXECUTE FUNCTION reserve_video_minutes();

CREATE FUNCTION reserve_export_slot() RETURNS TRIGGER LANGUAGE plpgsql AS $$
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
END $$;
CREATE TRIGGER trg_reserve_export BEFORE INSERT ON exports FOR EACH ROW EXECUTE FUNCTION reserve_export_slot();

CREATE FUNCTION settle_usage_reservation() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE target_kind TEXT; target_id TEXT;
BEGIN
 target_kind := CASE TG_TABLE_NAME WHEN 'projects' THEN 'minutes' ELSE 'export' END;
 target_id := NEW.id;
 IF NEW.status IN ('ready','completed') AND OLD.status IS DISTINCT FROM NEW.status THEN
   UPDATE usage_reservations SET status='finalized',updated_at=CURRENT_TIMESTAMP::text WHERE kind=target_kind AND resource_id=target_id AND status='reserved';
 ELSIF NEW.status IN ('failed','expired') AND OLD.status IS DISTINCT FROM NEW.status THEN
   IF target_kind='minutes' THEN
     UPDATE usage u SET source_minutes=GREATEST(0,u.source_minutes-r.amount) FROM usage_reservations r
      WHERE r.kind=target_kind AND r.resource_id=target_id AND r.status='reserved' AND u.user_id=r.user_id AND u.month=r.period_key;
   ELSE
     UPDATE usage u SET exports_used=GREATEST(0,u.exports_used-1) FROM usage_reservations r
      WHERE r.kind=target_kind AND r.resource_id=target_id AND r.status='reserved' AND u.user_id=r.user_id AND u.month=r.period_key;
   END IF;
   UPDATE usage_reservations SET status='released',updated_at=CURRENT_TIMESTAMP::text WHERE kind=target_kind AND resource_id=target_id AND status='reserved';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_settle_project_minutes AFTER UPDATE OF status ON projects FOR EACH ROW EXECUTE FUNCTION settle_usage_reservation();
CREATE TRIGGER trg_settle_export_slot AFTER UPDATE OF status ON exports FOR EACH ROW EXECUTE FUNCTION settle_usage_reservation();
"""

def upgrade() -> None:
    op.execute(SCHEMA)

def downgrade() -> None:
    raise RuntimeError("The production baseline is intentionally irreversible; restore from a database backup.")
