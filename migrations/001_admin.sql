BEGIN;
CREATE TABLE IF NOT EXISTS transcription_events (
 id uuid PRIMARY KEY,
 created_at timestamptz NOT NULL,
 status text NOT NULL CHECK (status IN ('success','error')),
 duration_seconds double precision CHECK (duration_seconds >= 0 AND duration_seconds < 'Infinity'::float8),
 processing_ms double precision NOT NULL CHECK (processing_ms >= 0),
 media_type text NOT NULL CHECK (media_type IN ('voice','circle','unknown')),
 error_code varchar(64),
 source text NOT NULL CHECK (source IN ('extension','bookmarklet','unknown'))
);
CREATE INDEX IF NOT EXISTS transcription_events_created ON transcription_events(created_at DESC);
CREATE TABLE IF NOT EXISTS admin_sessions (
 token_hash text PRIMARY KEY,
 auth_version text NOT NULL,
 expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS admin_sessions_expiry ON admin_sessions(expires_at);
CREATE TABLE IF NOT EXISTS admin_login_limit (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 window_start timestamptz NOT NULL,
 attempts integer NOT NULL
);
COMMIT;
