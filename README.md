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

## Публичная установка q

- `GET /install` — HTML с двумя перетаскиваемыми javascript:-закладками:
  «🎤 q — автономная» (основная) и «🎤 q — автообновление».
- `GET /q-runtime.js` — сгенерированный runtime. Загрузчик использует
  `https://voice-recognision-server-production.up.railway.app/q-runtime.js`.

Файлы `public/install.html` и `public/q-runtime.js` создаются командой
`npm --prefix bookmarklet run build` из корня общего проекта. Они включаются
в backend-репозиторий, поэтому Railway не нужны Node.js, test.txt или каталог
bookmarklet. Не редактируйте сгенерированные файлы вручную.

Отдаются только два фиксированных пути; StaticFiles на весь проект не монтируется.
Ответы имеют `Cache-Control: no-cache, max-age=0, must-revalidate`, `nosniff`,
`Referrer-Policy: no-referrer`. CSP документов запрещает скрипты, фреймы и формы,
разрешая только встроенные стили страницы установки. Она не переносится на
Gemspace при запуске сохранённой закладки. На /install кнопку надо перетащить,
а не выполнять её на самой странице установки.
Существующий CORS разрешает origin https://web.gemspace.com, без credentials.
Внешний classic script не требует CORS, но подчиняется CSP Gemspace.
Корпоративные политики могут запретить сам bookmarklet: тогда он не сможет
показать диагностику. При запущенном загрузчике сеть/CSP/тайм-аут показываются
сообщением, предлагающим автономный вариант. Универсальный обход не реализован.

Локальная проверка (из backend, без реальных обращений к Gemini):

```sh
GEMINI_API_KEY=local-test-not-a-real-key python -m uvicorn main:app --host 127.0.0.1 --port 8766
# В другом терминале:
curl -i http://127.0.0.1:8766/install
curl -sS -D - -o /dev/null http://127.0.0.1:8766/q-runtime.js
```

Маршруты зарегистрированы для GET; для проверки заголовков runtime используйте
`curl -sS -D - -o /dev/null http://127.0.0.1:8766/q-runtime.js` (HEAD не добавлялся).

### Публикация — только после подтверждения

```sh
cd /Users/admin/Documents/dev/voice-gs
npm --prefix bookmarklet ci
npm --prefix bookmarklet run build
npm --prefix bookmarklet test
cd backend
python -m unittest discover -s tests -v
railway login
railway link
railway status
# Выбрать/проверить СУЩЕСТВУЮЩИЕ project, service и production environment.
railway up
```

`railway up` загружает и разворачивает код; это не команда предварительной проверки.
Запускайте из backend, не из общего каталога с расширением. Переменные Gemini
и стартовую команду работающего сервиса менять для этих маршрутов не нужно.
При публикации через Git включите main.py, bookmarklet_routes.py, public/ и тесты
в backend-репозиторий; push может запускать автоматический деплой.
Никакой push или deploy при локальной подготовке не выполнялся.

После публикации проверить /install, /q-runtime.js и /health; затем перетащить
обе закладки в Chrome, открыть Gemspace и по очереди проверить их на свежей
странице. Для транскрибации использовать только разрешённое тестовое медиа.

## Закрытая панель владельца

Новая локальная реализация `/admin`: [ADMIN.md](ADMIN.md) — архитектура,
PostgreSQL, Variables, безопасность, миграция, тесты и порядок деплоя.
По умолчанию доступ закрыт; пароль в открытом виде не используется.
