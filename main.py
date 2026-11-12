import hashlib
import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from transcription import api_error, generate_transcription


# ============================================================
# Environment
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash",
)

GEMINI_TRANSCRIPTION_BACKEND = os.getenv("GEMINI_TRANSCRIPTION_BACKEND", "transcribe")
GEMINI_TRANSCRIBE_MODEL = os.getenv("GEMINI_TRANSCRIBE_MODEL", "gemini-3.5-transcribe")
GEMINI_TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "45"))
if GEMINI_TRANSCRIPTION_BACKEND not in {"transcribe", "generate_content"}:
    raise RuntimeError("GEMINI_TRANSCRIPTION_BACKEND must be transcribe or generate_content")
if not 0 < GEMINI_TIMEOUT_SECONDS <= 300:
    raise RuntimeError("GEMINI_TIMEOUT_SECONDS must be between 0 and 300")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not configured"
    )


# ============================================================
# Gemini
# ============================================================

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(
        api_version="v1beta",
        timeout=int(GEMINI_TIMEOUT_SECONDS * 1000),
        retry_options=types.HttpRetryOptions(attempts=1),
    ),
)


# ============================================================
# FastAPI
# ============================================================

app = FastAPI(
    title="q transcription API",
    description=(
        "Transcription backend for Gemspace "
        "voice messages and video circles."
    ),
    version="0.3.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "https://web.gemspace.com",
    ],

    allow_credentials=False,

    allow_methods=[
        "GET",
        "POST",
        "OPTIONS",
    ],

    allow_headers=["*"],
)


# ============================================================
# Cache
#
# Temporary in-memory cache.
#
# key:
#   SHA-256(media bytes)
#
# value:
#   transcription
#
# Railway restart = cache reset.
#
# Later this can be replaced with PostgreSQL.
# ============================================================

transcription_cache: dict[str, str] = {}


# ============================================================
# MIME normalization
# ============================================================

def normalize_mime_type(
    mime_type: str | None,
    filename: str | None,
) -> str:

    mime = (
        mime_type
        or ""
    ).lower().strip()

    name = (
        filename
        or ""
    ).lower().strip()


    # Gemspace voice messages can arrive as
    # audio/x-m4a or audio/mp4a-latm.
    #
    # Gemini understands the underlying
    # MP4/M4A container as audio/mp4.

    if mime in {
        "audio/x-m4a",
        "audio/m4a",
        "audio/mp4a-latm",
    }:
        return "audio/mp4"


    # Known good MIME from the request.

    if mime in {
        "audio/mp4",
        "audio/mpeg",
        "audio/wav",
        "video/mp4",
    }:
        return mime


    # Fall back to filename.

    if name.endswith(".m4a"):
        return "audio/mp4"

    if name.endswith(".mp4"):
        return "video/mp4"

    if name.endswith(".mp3"):
        return "audio/mpeg"

    if name.endswith(".wav"):
        return "audio/wav"


    # Preserve unknown MIME for the
    # unsupported-media error below.

    if mime:
        return mime


    return "application/octet-stream"


# ============================================================
# Gemini block reason
# ============================================================

def get_block_reason(
    response,
) -> str | None:

    feedback = getattr(
        response,
        "prompt_feedback",
        None,
    )

    if feedback is None:
        return None


    reason = getattr(
        feedback,
        "block_reason",
        None,
    )

    if reason is None:
        return None


    value = getattr(
        reason,
        "value",
        None,
    )

    if value:
        return str(value)


    name = getattr(
        reason,
        "name",
        None,
    )

    if name:
        return str(name)


    return str(reason)


# ============================================================
# Health
# ============================================================

@app.get("/")
async def root():
    return {
        "service": "q",
        "status": "online",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "q",
        "version": "0.3.0",
        "provider": "gemini",
        "model": GEMINI_MODEL,
        "transcription_backend": GEMINI_TRANSCRIPTION_BACKEND,
        "transcribe_model": GEMINI_TRANSCRIBE_MODEL,
        "cache_entries": len(
            transcription_cache
        ),
    }


# ============================================================
# Transcription
# ============================================================

@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
):
    # --------------------------------------------------------
    # Read upload
    # --------------------------------------------------------

    media = await file.read(30 * 1024 * 1024 + 1)


    if not media:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "empty_file",
                "message": (
                    "Uploaded media is empty"
                ),
            },
        )


    # --------------------------------------------------------
    # File size limit
    # --------------------------------------------------------

    max_size = (
        30
        * 1024
        * 1024
    )


    if len(media) > max_size:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "file_too_large",
                "message": (
                    "Media exceeds 30 MB"
                ),
            },
        )


    # --------------------------------------------------------
    # MIME
    # --------------------------------------------------------

    mime_type = normalize_mime_type(
        file.content_type,
        file.filename,
    )


    allowed_types = {
        "audio/mp4",
        "audio/mpeg",
        "audio/wav",
        "video/mp4",
    }


    if mime_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail={
                "code":
                    "unsupported_media",

                "message":
                    (
                        "Unsupported MIME type: "
                        f"{mime_type}"
                    ),
            },
        )


    # --------------------------------------------------------
    # SHA-256
    # --------------------------------------------------------

    digest = hashlib.sha256(
        media
    ).hexdigest()


    short_digest = digest[:12]


    print(
        "[q] received",
        {
            "filename":
                file.filename,

            "content_type":
                file.content_type,

            "normalized_type":
                mime_type,

            "size":
                len(media),

            "sha256":
                short_digest,
        },
        flush=True,
    )


    # --------------------------------------------------------
    # Cache
    # --------------------------------------------------------

    cached_text = (
        transcription_cache.get(
            digest
        )
    )


    if cached_text is not None:
        print(
            "[q] cache hit",
            short_digest,
            flush=True,
        )


        return {
            "text":
                cached_text,

            "cached":
                True,
        }


    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = (
        "Transcribe all clearly audible speech "
        "in this media accurately. "
        "Return only the transcription. "
        "Preserve the original spoken language. "
        "Do not translate. "
        "Do not summarize. "
        "Do not explain the content. "
        "Do not add introductory text or commentary. "
        "Add normal punctuation and paragraph breaks "
        "where useful. "
        "If a word cannot be understood reliably, "
        "do not invent it."
    )


    print(
        "[q] sending to Gemini",
        {
            "model": (
                GEMINI_TRANSCRIBE_MODEL
                if GEMINI_TRANSCRIPTION_BACKEND == "transcribe" and mime_type.startswith("audio/")
                else GEMINI_MODEL
            ),

            "mime_type":
                mime_type,

            "size":
                len(media),

            "sha256":
                short_digest,
        },
        flush=True,
    )


    # --------------------------------------------------------
    # Gemini request
    # --------------------------------------------------------

    try:
        response = await generate_transcription(
            client,
            media=media,
            mime_type=mime_type,
            prompt=prompt,
            backend=GEMINI_TRANSCRIPTION_BACKEND,
            model=GEMINI_MODEL,
            transcribe_model=GEMINI_TRANSCRIBE_MODEL,
            timeout=GEMINI_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        status, code, message = api_error(exc)
        # Provider exception strings may contain request URLs or credentials.
        print("[q] Gemini request failed", {"code": code}, flush=True)
        raise HTTPException(
            status_code=status, detail={"code": code, "message": message}
        ) from None


    # --------------------------------------------------------
    # Gemini response
    # --------------------------------------------------------

    block_reason = (
        get_block_reason(
            response
        )
    )


    try:
        text = (
            response.text
            or ""
        ).strip()

    except Exception:
        text = ""


    # --------------------------------------------------------
    # Empty response
    # --------------------------------------------------------

    if not text:
        print(
            "[q] empty Gemini response",
            flush=True,
        )


        print(
            "[q] block reason:",
            block_reason,
            flush=True,
        )


        normalized_reason = (
            block_reason
            or ""
        ).upper()


        if (
            "PROHIBITED_CONTENT"
            in normalized_reason
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code":
                        "gemini_content_blocked",

                    "message":
                        (
                            "Gemini blocked "
                            "this media"
                        ),
                },
            )


        raise HTTPException(
            status_code=502,
            detail={
                "code":
                    "empty_gemini_response",

                "message":
                    (
                        "Gemini returned "
                        "no transcription"
                    ),
            },
        )


    # --------------------------------------------------------
    # Cache successful result
    # --------------------------------------------------------

    transcription_cache[
        digest
    ] = text


    print(
        "[q] transcription ready",
        {
            "chars":
                len(text),

            "sha256":
                short_digest,
        },
        flush=True,
    )


    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "text":
            text,

        "cached":
            False,
    }