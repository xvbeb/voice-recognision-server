"""One event per HTTP attempt, independent of model calls and cache hits."""
import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from stats_store import store

log = logging.getLogger('q.stats')


class TranscriptionEvents:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST' or scope['path'] != '/transcribe':
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        event = dict(id=uuid.uuid4(), created_at=datetime.now(timezone.utc), status='error',
                     duration_seconds=None, processing_ms=0, media_type='unknown',
                     error_code='internal_error', source='unknown')
        finished = False
        async def capture(message):
            nonlocal finished
            if message['type'] == 'http.response.start':
                status = message['status']
                event['status'] = 'success' if 200 <= status < 300 else 'error'
                event['error_code'] = None if event['status']=='success' else f'http_{status}'
            if message['type'] == 'http.response.body' and not message.get('more_body',False):
                event['processing_ms'] = round((time.perf_counter()-started)*1000, 2)
                finished = True
            await send(message)
        try:
            await self.app(scope, receive, capture)
        except BaseException:
            event['status'] = 'error'
            event['error_code'] = 'request_failed'
            raise
        finally:
            if not finished:
                event['processing_ms'] = round((time.perf_counter()-started)*1000, 2)
            media = scope.get('state',{}).get('q_media_type')
            event['media_type'] = media if media in ('voice','circle') else 'unknown'
            # Never inspect response bodies, file names, headers, or transcription text.
            try:
                async with asyncio.timeout(0.75):
                    await store.record(event)
            except Exception:
                log.warning('transcription_event_write_failed')
