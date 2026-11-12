# q transcription API

FastAPI backend for Gemspace VoiceMessage and CircleVideo. Python 3.11+ is
required (`asyncio.timeout`). No browser changes or Railway deployment are part
of this update.

## Configuration and rollback

Copy `.env.example` to `.env` locally; put the same variables in Railway Variables
when deploying an approved release. Never commit `.env` or put the key in the extension.

| Variable | Default / purpose |
| --- | --- |
| `GEMINI_API_KEY` | Required server-side credential; retain the existing Railway secret |
| `GEMINI_TRANSCRIPTION_BACKEND` | `transcribe`; use `generate_content` for rollback |
| `GEMINI_TRANSCRIBE_MODEL` | `gemini-3.5-transcribe`, audio only |
| `GEMINI_MODEL` | `gemini-3.8-flash`, CircleVideo and legacy audio path |
| `GEMINI_TIMEOUT_SECONDS` | `45`, total operation deadline, maximum 300 |

To roll back the model/protocol, set `GEMINI_TRANSCRIPTION_BACKEND=generate_content`
and retain `GEMINI_MODEL=gemini-3.8-flash`, then restart the service. This path was
also tested with the updated SDK. There is no automatic second-model retry or
silent model substitution on errors.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

Run these commands inside `backend/`. `/health` reports configured models and
cache size; it is a liveness endpoint, not proof of Google API availability.

## Contract and transport

The extension fetches media and sends multipart `file` plus `message_id` to
`POST /transcribe`. The backend still ignores the optional extra `message_id`
field and returns `{ "text": "...", "cached": false }`. Errors retain
`{ "detail": { "code": "...", "message": "..." } }`, understood by content.js.
The 30 MiB limit and accepted MIME types are unchanged. Upload reads are bounded.

Audio uses `POST /v1beta/interactions`: inline base64 audio, `store=false`, default
Transcribe mode and automatic language detection. Internally `audio/mp4` maps to
Transcribe's documented `audio/m4a`; no transcoding, file upload lifecycle or
client protocol change is required. Text comes from `output_text`.

Video and rollback use the retained `POST /v1beta/models/{model}:generateContent`
path with inline bytes, the original prompt, and `response.text`. Calls are now
asynchronous so one upstream request does not block FastAPI's event loop.
API version is explicit because SDK 3.x defaults to v1.

The existing process-local SHA-256(media bytes) → successful text cache is
unchanged. Errors are never cached; a restart clears the cache. There is one
configured SDK attempt with a bounded overall timeout. Errors distinguish 429,
404/model unavailable, access errors, invalid input, timeouts and service failure.
Provider exception strings and full responses are not logged or sent to clients.

## Model decision — checked 2026-11-12

Before: `gemini-3.8-flash` for both media types, `google-genai` unpinned
(locally installed 2.25.0), synchronous generateContent.
Now: pinned `google-genai==3.2.0`, specialized Transcribe for audio, original Flash
for video and rollback. Transcribe exists and supports Russian/Ukrainian among
85+ languages. It needs Interactions, not a model-name-only replacement in the
old call. The change is isolated in `transcription.py`.

| Model | Standard input / output USD per million tokens | Decision |
| --- | --- | --- |
| Gemini 3.5 Transcribe | $2 audio / $12 text; Google's estimate ~$0.005/min total | Specialized speech default; real RU/UK checks passed |
| Gemini 3.5 Flash-Lite | $0.30 / $2.50 | Cheaper alternative; audio smoke test passed |
| Gemini 3.8 Flash | $0.75 / $3.75 until 2026-12-31; $1.50 / $7.50 from 2027-01-01 | Preserve existing video/rollback behavior |

Transcribe is **not** the cheapest of these models. The choice favors its speech
specific API and multilingual support at a small absolute cost for short clips.
The tiny synthetic sample does not demonstrate superior accuracy or production
latency. Flash-Lite remains an explicit low-cost option by setting
`GEMINI_TRANSCRIPTION_BACKEND=generate_content` and
`GEMINI_MODEL=gemini-3.5-flash-lite`; this also changes the video model, whose
Flash-Lite path has not been live-tested here.

Official references:
- [Transcribe formats, languages and API](https://aistudio.google.com/docs/transcribe)
- [Pricing](https://aistudio.google.com/docs/pricing)
- [Flash-Lite capabilities](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite)
- [Flash capabilities](https://aistudio.google.com/docs/models/gemini-3.8-flash)
- [Inline media limits](https://aistudio.google.com/docs/file-input-methods)
- [Python SDK](https://github.com/googleapis/python-genai)

## Verification

Offline unit tests (fake credentials, no Google requests):

```sh
python -m unittest discover -s tests -v
python -m py_compile main.py transcription.py tests/test_transcription.py
```

From repository root: `node --test extension/tests/*.test.cjs`.

Performed locally in an isolated virtualenv with SDK 3.2.0 and the existing local
server credential, using only macOS TTS-generated recordings:

| Test through FastAPI multipart endpoint | Result | Single-request wall time |
| --- | --- | --- |
| Russian M4A → Transcribe | HTTP 200, original-language text | 1.55 s |
| Ukrainian M4A → Transcribe | HTTP 200, original-language text | 1.05 s |
| Black-frame MP4 + synthetic Russian audio → Flash | HTTP 200, speech text | 2.60 s |
| Repeat each upload | Identical cached result, no new model call | — |
| Ukrainian M4A with legacy backend | HTTP 200, original-language text | — |

Direct synthetic Russian audio comparison: Flash-Lite 1.84 s, Flash 2.30 s.
These are individual smoke checks, not a benchmark; Transcribe formatted spoken
time as `10:00`. No real user's voice was uploaded. Railway and the live
extension-to-Railway flow have not been tested or deployed with this release.

After approved deployment, test one explicitly permitted short voice clip in
Gemspace, then repeat it to check caching; test one permitted CircleVideo.
Check language preservation and readable errors. Use `/health` to confirm
configuration, without treating it as a transcription test.
