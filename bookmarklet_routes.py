"""Serve only the two generated public bookmarklet artifacts."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()
PUBLIC = Path(__file__).resolve().parent / "public"
HEADERS = {
    "Cache-Control": "no-cache, max-age=0, must-revalidate",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    # Applies to these resources as documents, not to the Gemspace document.
    # Dragging a bookmark link needs no script execution on the install page.
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; "
        "base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'"
    ),
}


@router.get("/install", response_class=FileResponse)
async def install():
    return FileResponse(PUBLIC / "install.html", media_type="text/html", headers=HEADERS)


@router.get("/q-runtime.js", response_class=FileResponse)
async def runtime():
    return FileResponse(PUBLIC / "q-runtime.js", media_type="application/javascript", headers=HEADERS)
