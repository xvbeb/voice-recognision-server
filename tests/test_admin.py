import asyncio
import os
import re
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import AsyncMock, patch

os.environ['GEMINI_API_KEY']='unit-test-not-a-key'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main
import psycopg
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from admin_auth import SESSION, LOGIN, digest
from stats_store import store, boundaries

TEST_URL=os.getenv('Q_TEST_DATABASE_URL','')
PASSWORD='Only a synthetic test password 123!'
HASH=PasswordHasher().hash(PASSWORD)


class Defaults(unittest.TestCase):
    def test_disabled_without_secrets(self):
        with patch.dict(os.environ, {'ADMIN_PASSWORD_HASH':'','ADMIN_SESSION_SECRET':''}):
            with TestClient(main.app,base_url='https://testserver') as c:
                for url in ('/admin','/admin/login','/admin/app.js','/api/admin/stats'):
                    self.assertEqual(c.get(url).status_code,404)
                self.assertEqual(c.post('/api/admin/logout').status_code,404)

    def test_malformed_hash_or_missing_session_secret_disables_admin(self):
        for hashed, secret in [('bad-hash', 'x'*40), (HASH, '')]:
            with patch.dict(os.environ, {'ADMIN_PASSWORD_HASH':hashed,'ADMIN_SESSION_SECRET':secret}):
                with TestClient(main.app,base_url='https://testserver') as c:
                    self.assertEqual(c.get('/admin/login').status_code,404)

    def test_calendar_boundaries_use_kyiv_dst(self):
        now=datetime(2026,3,29,12,tzinfo=timezone.utc)
        start,*_=boundaries('today','Europe/Kyiv',now)
        self.assertEqual(start,datetime(2026,3,28,22,tzinfo=timezone.utc))
        start,*_=boundaries('7d','Europe/Kyiv',now)
        self.assertEqual(start,datetime(2026,3,22,22,tzinfo=timezone.utc))


@unittest.skipUnless(TEST_URL,'Set Q_TEST_DATABASE_URL to an isolated localhost *_test database')
class AdminPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed=urlsplit(TEST_URL)
        if parsed.hostname not in ('localhost','127.0.0.1') or not parsed.path.endswith('_test'):
            raise RuntimeError('Tests require isolated loopback *_test database')
        with psycopg.connect(TEST_URL,autocommit=True) as conn:
            conn.execute(Path(__file__).resolve().parents[1].joinpath('migrations/001_admin.sql').read_text())

    def setUp(self):
        self.env=patch.dict(os.environ,dict(DATABASE_URL=TEST_URL, ADMIN_PASSWORD_HASH=HASH,
            ADMIN_SESSION_SECRET='synthetic-session-secret-at-least-32-characters',ADMIN_ORIGIN='https://testserver'))
        self.env.start();self.addCleanup(self.env.stop)
        with psycopg.connect(TEST_URL) as conn:
            conn.execute('TRUNCATE transcription_events,admin_sessions,admin_login_limit')
        main.transcription_cache.clear()
        self.c=TestClient(main.app,base_url='https://testserver')
        self.addCleanup(self.c.close)

    def token(self):
        r=self.c.get('/admin/login')
        self.assertEqual(r.status_code,200)
        return re.search('name="csrf" value="([^"]+)"',r.text)[1]

    def login(self,password=PASSWORD):
        return self.c.post('/admin/login',headers={'Origin':'https://testserver'},
            data={'password':password,'csrf':self.token()},follow_redirects=False)

    def stats(self,period='all'):
        return self.c.get('/api/admin/stats',params={'period':period,'timezone':'UTC'})

    def insert(self, days=0, status='success', duration=None):
        event=dict(id=uuid.uuid4(),created_at=datetime.now(timezone.utc)-timedelta(days=days),
            status=status,duration_seconds=duration,processing_ms=200,media_type='voice',error_code=None,source='unknown')
        asyncio.run(store.record(event))
        return event

    def test_authentication_cookie_logout_replay_and_csrf(self):
        self.assertEqual(self.c.get('/admin',follow_redirects=False).status_code,303)
        self.assertEqual(self.stats().status_code,401)
        self.assertEqual(self.c.get('/admin/app.js').status_code,401)
        self.c.cookies.set(SESSION,'x'*43)
        self.assertEqual(self.stats().status_code,401)
        self.c.cookies.clear()
        self.assertEqual(self.login('wrong').status_code,401)
        login=self.login()
        self.assertEqual(login.status_code,303)
        cookie=login.headers.get_list('set-cookie')[0]
        for flag in ('HttpOnly','Secure','SameSite=strict','Max-Age=3600','Path=/'):
            self.assertIn(flag,cookie)
        saved=self.c.cookies.get(SESSION)
        r=self.stats();self.assertEqual(r.status_code,200)
        csrf=r.json()['csrf']
        self.assertEqual(self.c.post('/api/admin/logout',headers={'Origin':'https://testserver'}).status_code,403)
        self.assertEqual(self.c.post('/api/admin/logout',headers={'Origin':'https://evil.example','X-CSRF-Token':csrf}).status_code,403)
        self.assertEqual(self.c.post('/api/admin/logout',headers={'Origin':'https://testserver','X-CSRF-Token':csrf}).status_code,200)
        self.c.cookies.clear();self.c.cookies.set(SESSION,saved)
        self.assertEqual(self.stats().status_code,401)

    def test_expiry_and_secret_rotation(self):
        self.login()
        with psycopg.connect(TEST_URL) as conn:
            conn.execute("UPDATE admin_sessions SET expires_at=now()-interval '1 second'")
        self.assertEqual(self.stats().status_code,401)
        self.login()
        with patch.dict(os.environ,{'ADMIN_SESSION_SECRET':'different-long-synthetic-session-secret-987'}):
            self.assertEqual(self.stats().status_code,401)

    def test_login_csrf_and_shared_rate_limit(self):
        self.assertEqual(self.c.post('/admin/login',data={'password':PASSWORD}).status_code,403)
        token=self.token()
        self.assertEqual(self.c.post('/admin/login',headers={'Origin':'https://evil.example'},data={'password':PASSWORD,'csrf':token}).status_code,403)
        for _ in range(5):
            self.assertEqual(self.login('wrong').status_code,401)
        self.c.cookies.clear()
        self.assertEqual(self.login().status_code,429)
        with psycopg.connect(TEST_URL) as conn:
            conn.execute("UPDATE admin_login_limit SET window_start=now()-interval '16 minutes'")
        self.assertEqual(self.login().status_code,303)

    def test_login_token_tampering_and_expiry(self):
        token=self.token()
        r=self.c.post('/admin/login',headers={'Origin':'https://testserver'},data={'password':PASSWORD,'csrf':token+'x'})
        self.assertEqual(r.status_code,403)
        with patch('admin_auth.time.time', return_value=1):
            expired=self.token()
        r=self.c.post('/admin/login',headers={'Origin':'https://testserver'},data={'password':PASSWORD,'csrf':expired})
        self.assertEqual(r.status_code,403)

    def test_empty_and_periods(self):
        self.login()
        empty=self.stats().json()
        self.assertEqual(empty['summary']['total'],0)
        self.assertIsNone(empty['summary']['success_rate'])
        self.assertIsNone(empty['summary']['duration_seconds'])
        self.assertEqual(empty['daily'],[])
        self.insert(0,duration=12);self.insert(2,status='error');self.insert(10);self.insert(40)
        for period,count in [('today',1),('7d',2),('30d',3),('all',4)]:
            r=self.stats(period).json()
            self.assertEqual(r['summary']['total'],count)
            self.assertEqual(sum(d['success']+d['errors'] for d in r['daily']),count)
        all_data=self.stats().json()
        self.assertEqual(all_data['summary']['success_rate'],75)
        self.assertEqual(all_data['summary']['duration_seconds'],12)
        self.assertEqual(all_data['summary']['avg_processing_ms'],200)
        self.assertEqual(all_data['successful_windows'],{'today':1,'days7':1,'days30':2})
        self.assertEqual(self.stats('injected').status_code,400)

    def test_success_cache_failure_validation_each_once(self):
        with patch.object(main,'generate_transcription',AsyncMock(return_value=SimpleNamespace(text='PRIVATE TRANSCRIPT'))):
            for _ in range(2):
                self.assertEqual(self.c.post('/transcribe',files={'file':('secret-name.m4a',b'audio','audio/mp4')}).status_code,200)
            self.assertEqual(self.c.post('/transcribe',files={'file':('bad.txt',b'x','text/plain')}).status_code,415)
            self.assertEqual(self.c.post('/transcribe').status_code,422)
        self.login()
        data=self.stats().json()
        self.assertEqual(data['summary']['total'],4)
        self.assertEqual(data['summary']['success'],2)
        self.assertEqual(data['summary']['errors'],2)
        text=str(data)
        for private in (PASSWORD,HASH,'PRIVATE TRANSCRIPT','secret-name'):
            self.assertNotIn(private,text)
        self.assertEqual({e['source'] for e in data['recent']},{'unknown'})
        self.assertTrue(all(e['duration_seconds'] is None for e in data['recent']))

    def test_unhandled_request_failure_is_counted_once(self):
        with patch.object(main,'normalize_mime_type',side_effect=RuntimeError('synthetic failure')):
            with TestClient(main.app,base_url='https://testserver',raise_server_exceptions=False) as c:
                self.assertEqual(c.post('/transcribe',files={'file':('voice.m4a',b'audio','audio/mp4')}).status_code,500)
        self.login()
        data=self.stats().json()
        self.assertEqual(data['summary']['total'],1)
        self.assertEqual(data['recent'][0]['error_code'],'request_failed')
        self.assertGreaterEqual(data['recent'][0]['processing_ms'],0)

    def test_error_and_circle_and_unique_id(self):
        with patch.object(main,'generate_transcription',AsyncMock(side_effect=TimeoutError())):
            self.assertEqual(self.c.post('/transcribe',files={'file':('circle.mp4',b'video','video/mp4')}).status_code,504)
        event=self.insert()
        asyncio.run(store.record(event))
        self.login();data=self.stats().json()
        self.assertEqual(data['summary']['total'],2)
        row=next(e for e in data['recent'] if e['status']=='error')
        self.assertEqual(row['media_type'],'circle')
        self.assertEqual(row['error_code'],'http_504')

    def test_unavailable_database_fails_closed_without_breaking_transcription(self):
        self.login()
        with patch.dict(os.environ,{'DATABASE_URL':'postgresql://127.0.0.1:1/unavailable'}):
            self.assertEqual(self.stats().status_code,503)
            with patch.object(main,'generate_transcription',AsyncMock(return_value=SimpleNamespace(text='ok'))):
                r=self.c.post('/transcribe',files={'file':('voice.m4a',b'audio','audio/mp4')})
                self.assertEqual(r.json(),{'text':'ok','cached':False})
        with patch.object(store,'dashboard',AsyncMock(side_effect=RuntimeError('SECRET CONNECTION STRING'))):
            r=self.stats();self.assertEqual(r.status_code,503);self.assertNotIn('SECRET',r.text)

    def test_security_headers_and_no_public_data(self):
        self.login()
        for path in ('/admin','/api/admin/stats','/admin/app.js','/admin/login'):
            r=self.c.get(path)
            self.assertEqual(r.headers['cache-control'],'no-store')
            self.assertIn("frame-ancestors 'none'",r.headers['content-security-policy'])
            self.assertNotIn(PASSWORD,r.text);self.assertNotIn(HASH,r.text)
        for path in ('/health','/install','/q-runtime.js'):
            r=self.c.get(path);self.assertEqual(r.status_code,200)
            self.assertNotIn('successful_windows',r.text);self.assertNotIn(HASH,r.text)

    def test_shared_throttle_atomic_under_concurrency(self):
        async def attempts():
            return await asyncio.gather(*(store.reserve_login() for _ in range(12)))
        self.assertEqual(sum(asyncio.run(attempts())),5)
