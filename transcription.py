"""Gemini transports; browser upload and response contracts live in main.py."""

import asyncio
import base64
from types import SimpleNamespace

import httpx
import httpx2
from google.genai import types


async def generate_transcription(
    client, *, media, mime_type, prompt, backend, model, transcribe_model, timeout
):
    # Bound the whole operation, not just each individual HTTP read.
    async with asyncio.timeout(timeout):
        if backend == "transcribe" and mime_type.startswith("audio/"):
            response = await client.aio.interactions.create(
                model=transcribe_model,
                input=[{
                    "type": "audio",
                    "data": base64.b64encode(media).decode("ascii"),
                    "mime_type": "audio/m4a" if mime_type == "audio/mp4" else mime_type,
                }],
                store=False,
                timeout=timeout,
            )
            # No conversation history or server-side Interaction storage is needed.
            # Default Transcribe mode preserves the spoken language.
            return SimpleNamespace(text=response.output_text)

        # Keep the existing generateContent path for CircleVideo and rollback.
        return await client.aio.models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=media, mime_type=mime_type), prompt],
        )


def api_error(exc):
    """Return safe HTTP status/code/message, never provider text or request URLs."""
    # SDK transports can wrap httpx exceptions; inspect causes without logging them.
    cause = exc
    for _ in range(5):
        if isinstance(cause, (TimeoutError, httpx.TimeoutException, httpx2.TimeoutException)):
            return 504, "gemini_timeout", "Transcription timed out. Please try again."
        cause = getattr(cause, "__cause__", None)
        if cause is None:
            break
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return 429, "gemini_rate_limited", "Gemini quota or rate limit reached. Please try later."
    if status == 404:
        return 503, "gemini_model_unavailable", "Configured Gemini model is unavailable. Contact the service administrator."
    if status in (408, 504):
        return 504, "gemini_timeout", "Transcription timed out. Please try again."
    if status in (401, 403):
        return 502, "gemini_access_denied", "Gemini access is not configured correctly. Contact the service administrator."
    if status == 400:
        return 422, "gemini_invalid_request", "Gemini could not process this media or model configuration."
    if status in (500, 502, 503) or isinstance(exc, (httpx.TransportError, httpx2.TransportError)):
        return 503, "gemini_unavailable", "Gemini is temporarily unavailable. Please try later."
    return 502, "gemini_error", "Gemini request failed. Please try again."
