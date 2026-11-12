import asyncio
import base64
import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Unit tests never use credentials from .env or contact Google.
os.environ['GEMINI_API_KEY'] = 'unit-test-not-a-key'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from fastapi.testclient import TestClient
from google.genai import errors
import httpx
import httpx2
from transcription import api_error, generate_transcription


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.interaction = AsyncMock(return_value=SimpleNamespace(output_text='Привіт'))
        self.generate = AsyncMock(return_value=SimpleNamespace(text='Привет'))
        self.client = SimpleNamespace(aio=SimpleNamespace(
            interactions=SimpleNamespace(create=self.interaction),
            models=SimpleNamespace(generate_content=self.generate)))
        self.args = dict(media=b'audio bytes', mime_type='audio/mp4', prompt='unchanged prompt',
                         backend='transcribe', model='legacy', transcribe_model='specialized', timeout=1)

    async def test_audio_inline_m4a(self):
        result = await generate_transcription(self.client, **self.args)
        self.assertEqual(result.text, 'Привіт')
        call = self.interaction.call_args.kwargs
        self.assertEqual(call['model'], 'specialized')
        self.assertFalse(call['store'])
        self.assertEqual(call['input'][0]['mime_type'], 'audio/m4a')
        self.assertEqual(base64.b64decode(call['input'][0]['data']), b'audio bytes')
        self.generate.assert_not_awaited()

    async def test_video_and_rollback_keep_generate_content(self):
        for mime, backend in [('video/mp4', 'transcribe'), ('audio/mp4', 'generate_content')]:
            with self.subTest(mime=mime):
                args = self.args | dict(mime_type=mime, backend=backend)
                await generate_transcription(self.client, **args)
                call = self.generate.call_args.kwargs
                self.assertEqual(call['model'], 'legacy')
                self.assertEqual(call['contents'][0].inline_data.data, b'audio bytes')
                self.assertEqual(call['contents'][0].inline_data.mime_type, mime)
                self.assertEqual(call['contents'][1], 'unchanged prompt')
        self.interaction.assert_not_awaited()

    async def test_total_deadline(self):
        async def slow(**kwargs):
            await asyncio.sleep(1)
        self.interaction.side_effect = slow
        with self.assertRaises(TimeoutError):
            await generate_transcription(self.client, **(self.args | {'timeout': 0.001}))


class EndpointTests(unittest.TestCase):
    def setUp(self):
        main.transcription_cache.clear()
        self.client = TestClient(main.app)
        self.provider = AsyncMock(return_value=SimpleNamespace(text=' Привіт! '))
        self.patch = patch.object(main, 'generate_transcription', self.provider)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.client.close)

    def upload(self, data=b'media', mime='audio/x-m4a', name='voice.m4a'):
        return self.client.post('/transcribe', files={'file': (name, data, mime)},
                                data={'message_id': 'existing-client-field'})

    def test_browser_contract_and_sha_cache(self):
        self.assertEqual(self.upload().json(), {'text': 'Привіт!', 'cached': False})
        self.assertEqual(self.upload().json(), {'text': 'Привіт!', 'cached': True})
        self.provider.assert_awaited_once()
        self.assertEqual(self.provider.call_args.kwargs['mime_type'], 'audio/mp4')

    def test_video_contract(self):
        self.assertEqual(self.upload(mime='video/mp4', name='circle.mp4').status_code, 200)
        self.assertEqual(self.provider.call_args.kwargs['mime_type'], 'video/mp4')

    def test_invalid_uploads_do_not_reach_provider(self):
        self.assertEqual(self.upload(data=b'').status_code, 400)
        self.assertEqual(self.upload(mime='text/plain', name='file.txt').status_code, 415)
        self.assertEqual(self.upload(data=b'x' * (30 * 1024 * 1024 + 1)).status_code, 413)
        self.provider.assert_not_awaited()

    def test_errors_are_safe_and_not_cached(self):
        cases = [(429,429,'gemini_rate_limited'), (404,503,'gemini_model_unavailable'),
                 (503,503,'gemini_unavailable'), (403,502,'gemini_access_denied'),
                 (400,422,'gemini_invalid_request'), (504,504,'gemini_timeout')]
        for upstream, status, code in cases:
            with self.subTest(upstream=upstream):
                self.provider.side_effect = errors.APIError(upstream, {'error': {'message': 'SECRET-KEY'}})
                log = io.StringIO()
                with contextlib.redirect_stdout(log):
                    response = self.upload()
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()['detail']['code'], code)
                self.assertNotIn('SECRET-KEY', response.text + log.getvalue())
                self.assertFalse(main.transcription_cache)
        self.provider.side_effect = TimeoutError()
        self.assertEqual(self.upload().status_code, 504)
        self.provider.side_effect = RuntimeError('SECRET-KEY')
        self.assertEqual(self.upload().status_code, 502)

    def test_empty_and_blocked_responses_not_cached(self):
        self.provider.return_value = SimpleNamespace(text='')
        self.assertEqual(self.upload().json()['detail']['code'], 'empty_gemini_response')
        self.provider.return_value = SimpleNamespace(text='', prompt_feedback=SimpleNamespace(block_reason='PROHIBITED_CONTENT'))
        self.assertEqual(self.upload().status_code, 422)
        self.assertFalse(main.transcription_cache)

    def test_wrapped_transport_timeout(self):
        wrapped = RuntimeError('provider detail')
        wrapped.__cause__ = httpx.ReadTimeout('private URL')
        self.assertEqual(api_error(wrapped)[0], 504)
        self.assertEqual(api_error(httpx2.ReadTimeout('private URL'))[0], 504)
        self.assertEqual(api_error(httpx2.ConnectError('private URL'))[0], 503)


if __name__ == '__main__':
    unittest.main()
