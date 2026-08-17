from __future__ import annotations

from app.core.database import execute
from app.core.version import APP_VERSION
from app.services.pipeline_provenance import PIPELINE_VERSION


async def init_behavioral_triggers() -> None:
    """Install DB-boundary capture for ranking exposure context and export outcomes.

    Clip batches produced by `_persist_suggestions` share one `created_at` value and
    are inserted in ranked order. The trigger uses that stable batch identity to
    create exactly one generation and preserve rank before later edits/reprocessing.
    Export triggers record strong labels even when browser telemetry never arrives.
    """
    statements = [
        f"""
        CREATE TRIGGER IF NOT EXISTS trg_learning_capture_clip_suggestion
        AFTER INSERT ON clips
        BEGIN
          INSERT INTO recommendation_generations(
            id,user_id,project_id,video_id,language,category,ranking_source,ranking_model,
            app_version,pipeline_version,clip_count,created_at
          )
          SELECT lower(hex(randomblob(16))),p.user_id,p.id,NEW.video_id,
            COALESCE((SELECT language FROM transcripts WHERE video_id=NEW.video_id ORDER BY created_at DESC LIMIT 1),p.language,'unknown'),
            COALESCE(p.category,'auto'),'pending','pending','{APP_VERSION}','{PIPELINE_VERSION}',0,NEW.created_at
          FROM videos v JOIN projects p ON p.id=v.project_id
          WHERE v.id=NEW.video_id
            AND NOT EXISTS (
              SELECT 1 FROM recommendation_generations
              WHERE video_id=NEW.video_id AND created_at=NEW.created_at
            );

          UPDATE recommendation_generations
          SET clip_count=clip_count+1
          WHERE video_id=NEW.video_id AND created_at=NEW.created_at;

          INSERT INTO clip_suggestion_snapshots(
            id,generation_id,user_id,project_id,video_id,clip_id,suggestion_rank,
            start_time,end_time,duration,score,score_breakdown_json,platform,
            ranking_source,ranking_model,language,category,app_version,pipeline_version,created_at
          )
          SELECT lower(hex(randomblob(16))),g.id,g.user_id,g.project_id,g.video_id,NEW.id,
            (SELECT COUNT(*)+1 FROM clip_suggestion_snapshots x WHERE x.generation_id=g.id),
            NEW.start_time,NEW.end_time,MAX(0,NEW.end_time-NEW.start_time),NEW.score,
            NEW.score_breakdown_json,NEW.platform,g.ranking_source,g.ranking_model,
            g.language,g.category,g.app_version,g.pipeline_version,NEW.created_at
          FROM recommendation_generations g
          WHERE g.video_id=NEW.video_id AND g.created_at=NEW.created_at
          LIMIT 1;
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_learning_capture_ranking_source
        AFTER INSERT ON audit_events
        WHEN NEW.event='project.processed' AND NEW.entity_type='project'
        BEGIN
          UPDATE recommendation_generations
          SET ranking_source=COALESCE(json_extract(NEW.metadata_json,'$.ranking_source'),'local'),
              ranking_model=CASE
                WHEN COALESCE(json_extract(NEW.metadata_json,'$.ranking_source'),'local')='groq'
                  THEN 'groq-configured'
                ELSE 'deterministic-local'
              END
          WHERE id=(
            SELECT id FROM recommendation_generations
            WHERE project_id=NEW.entity_id ORDER BY created_at DESC LIMIT 1
          );

          UPDATE clip_suggestion_snapshots
          SET ranking_source=(
                SELECT ranking_source FROM recommendation_generations g
                WHERE g.id=clip_suggestion_snapshots.generation_id
              ),
              ranking_model=(
                SELECT ranking_model FROM recommendation_generations g
                WHERE g.id=clip_suggestion_snapshots.generation_id
              )
          WHERE generation_id=(
            SELECT id FROM recommendation_generations
            WHERE project_id=NEW.entity_id ORDER BY created_at DESC LIMIT 1
          );
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_learning_export_requested
        AFTER INSERT ON exports
        BEGIN
          INSERT OR IGNORE INTO clip_behavior_events(
            id,event_key,user_id,project_id,video_id,clip_id,generation_id,event_type,
            source,client_session_id,context_json,created_at
          )
          SELECT lower(hex(randomblob(16))),'server:export_requested:' || NEW.id,
            s.user_id,s.project_id,s.video_id,s.clip_id,s.generation_id,'export_requested',
            'server',NULL,'{}',NEW.created_at
          FROM clip_suggestion_snapshots s
          WHERE s.clip_id=NEW.clip_id ORDER BY s.created_at DESC LIMIT 1;
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_learning_export_ready
        AFTER UPDATE OF status ON exports
        WHEN NEW.status='ready' AND OLD.status <> 'ready'
        BEGIN
          INSERT OR IGNORE INTO clip_behavior_events(
            id,event_key,user_id,project_id,video_id,clip_id,generation_id,event_type,
            source,client_session_id,context_json,created_at
          )
          SELECT lower(hex(randomblob(16))),'server:export_ready:' || NEW.id,
            s.user_id,s.project_id,s.video_id,s.clip_id,s.generation_id,'export_ready',
            'server',NULL,'{}',strftime('%Y-%m-%dT%H:%M:%fZ','now')
          FROM clip_suggestion_snapshots s
          WHERE s.clip_id=NEW.clip_id ORDER BY s.created_at DESC LIMIT 1;
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_learning_export_failed
        AFTER UPDATE OF status ON exports
        WHEN NEW.status='failed' AND OLD.status <> 'failed'
        BEGIN
          INSERT OR IGNORE INTO clip_behavior_events(
            id,event_key,user_id,project_id,video_id,clip_id,generation_id,event_type,
            source,client_session_id,context_json,created_at
          )
          SELECT lower(hex(randomblob(16))),'server:export_failed:' || NEW.id,
            s.user_id,s.project_id,s.video_id,s.clip_id,s.generation_id,'export_failed',
            'server',NULL,'{}',strftime('%Y-%m-%dT%H:%M:%fZ','now')
          FROM clip_suggestion_snapshots s
          WHERE s.clip_id=NEW.clip_id ORDER BY s.created_at DESC LIMIT 1;
        END
        """,
    ]
    for statement in statements:
        await execute(statement)
