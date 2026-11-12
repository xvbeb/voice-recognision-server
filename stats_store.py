"""Small PostgreSQL repository. No schema changes at application startup."""
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

UTC = timezone.utc


def boundaries(period, tz, now=None):
    now = now or datetime.now(UTC)
    today = now.astimezone(ZoneInfo(tz)).replace(hour=0, minute=0, second=0, microsecond=0)
    days = {'today': 1, '7d': 7, '30d': 30}
    start = (today - timedelta(days=days[period]-1)).astimezone(UTC) if period in days else None
    return start, now, today.astimezone(UTC), (today-timedelta(days=6)).astimezone(UTC), (today-timedelta(days=29)).astimezone(UTC)


class Store:
    @asynccontextmanager
    async def connection(self):
        url = os.getenv('DATABASE_URL')
        if not url:
            raise RuntimeError('database_not_configured')
        async with asyncio.timeout(3):
            async with await psycopg.AsyncConnection.connect(
                url, connect_timeout=2, options='-c statement_timeout=2000', row_factory=dict_row
            ) as conn:
                yield conn

    async def record(self, event):
        async with self.connection() as conn:
            await conn.execute('''INSERT INTO transcription_events
                (id,created_at,status,duration_seconds,processing_ms,media_type,error_code,source)
                VALUES (%(id)s,%(created_at)s,%(status)s,%(duration_seconds)s,%(processing_ms)s,%(media_type)s,%(error_code)s,%(source)s)
                ON CONFLICT (id) DO NOTHING''', event)

    async def reserve_login(self):
        async with self.connection() as conn:
            row = await (await conn.execute('''INSERT INTO admin_login_limit VALUES (true, now(), 1)
                ON CONFLICT (singleton) DO UPDATE SET
                attempts=CASE WHEN admin_login_limit.window_start < now()-interval '15 minutes' THEN 1 ELSE admin_login_limit.attempts+1 END,
                window_start=CASE WHEN admin_login_limit.window_start < now()-interval '15 minutes' THEN now() ELSE admin_login_limit.window_start END
                RETURNING attempts''')).fetchone()
            return row['attempts'] <= 5

    async def create_session(self, digest, version, expires):
        async with self.connection() as conn:
            await conn.execute('DELETE FROM admin_sessions WHERE expires_at <= now()')
            await conn.execute('INSERT INTO admin_sessions VALUES (%s,%s,%s)', (digest,version,expires))

    async def session(self, digest, version):
        async with self.connection() as conn:
            return await (await conn.execute('SELECT expires_at FROM admin_sessions WHERE token_hash=%s AND auth_version=%s AND expires_at>now()', (digest,version))).fetchone()

    async def logout(self, digest):
        async with self.connection() as conn:
            await conn.execute('DELETE FROM admin_sessions WHERE token_hash=%s', (digest,))

    async def dashboard(self, period, tz):
        start, now, today, week, month = boundaries(period,tz)
        async with self.connection() as conn:
            # All cards, series and rows see one consistent database snapshot.
            await conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            summary = await (await conn.execute('''SELECT count(*) AS total,
                count(*) FILTER (WHERE status='success') AS success,
                count(*) FILTER (WHERE status='error') AS errors,
                sum(duration_seconds) FILTER (WHERE status='success') AS duration_seconds,
                count(duration_seconds) FILTER (WHERE status='success') AS duration_known,
                avg(processing_ms) AS avg_processing_ms
                FROM transcription_events WHERE (%s::timestamptz IS NULL OR created_at >= %s) AND created_at<=%s''', (start,start,now))).fetchone()
            counts = await (await conn.execute('''SELECT
                count(*) FILTER (WHERE created_at >= %s) AS today,
                count(*) FILTER (WHERE created_at >= %s) AS days7,
                count(*) FILTER (WHERE created_at >= %s) AS days30
                FROM transcription_events WHERE status='success' AND created_at<=%s''', (today,week,month,now))).fetchone()
            daily = await (await conn.execute('''SELECT (created_at AT TIME ZONE %s)::date AS day,
                count(*) FILTER (WHERE status='success') AS success,
                count(*) FILTER (WHERE status='error') AS errors
                FROM transcription_events WHERE (%s::timestamptz IS NULL OR created_at >= %s) AND created_at<=%s
                GROUP BY day ORDER BY day''', (tz,start,start,now))).fetchall()
            recent = await (await conn.execute('''SELECT * FROM transcription_events
                WHERE (%s::timestamptz IS NULL OR created_at >= %s) AND created_at<=%s
                ORDER BY created_at DESC,id DESC LIMIT 50''', (start,start,now))).fetchall()
        summary['success_rate'] = summary['success']/summary['total']*100 if summary['total'] else None
        return dict(summary=summary, successful_windows=counts, daily=daily, recent=recent,
                    period=period, timezone=tz, as_of=now)


store = Store()
