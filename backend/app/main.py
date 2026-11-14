"""FastAPI entry point: API routes plus the built frontend, on one origin.

API routes are ordinary FastAPI routes. The frontend is NOT mounted as a
catch-all; it is served only when no API route matched (see `not_found`).
That way static files can never shadow an API route, whatever order routes
are added in.
"""

from pathlib import Path

from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import REPO_ROOT, get_settings
from app.letters import process_letter
from app.reader import MAX_UPLOAD_BYTES, ReaderError
from app.schemas import LetterResponse
from app.store import STORE, sample_image_bytes

FRONTEND_DIST: Path = REPO_ROOT / "frontend" / "dist"

# Paths that belong to the API. A 404 under these stays a JSON 404 and is
# never answered with the frontend. Add new API prefixes here.
API_PREFIXES = ("/health", "/letters", "/proposals", "/account", "/audit")

app = FastAPI(title="Guarded Mail Agent")


@app.get("/health")
def health() -> dict:
    """Report what is configured. Booleans only, never secret values."""
    settings = get_settings()
    return {
        "status": "ok",
        "demo_offline": settings.demo_offline,
        "nessie_configured": settings.demo_offline
        or bool(settings.nessie_api_key and settings.nessie_account_id),
        "gemini_configured": bool(settings.gemini_api_key),
    }


# Reader failures the user can fix by taking another photo -> 400.
# Everything else means our side could not read it right now -> 503.
_USER_FIXABLE = {"image_empty", "image_too_large", "image_unreadable",
                 "language_not_supported"}


@app.post("/letters")
async def post_letter(
    language: str = Form(...),
    image: UploadFile | None = File(None),
    sample: str | None = Form(None),
) -> LetterResponse:
    """Read a letter photo (or a built-in sample) and propose one action."""
    if sample is not None:
        image_bytes = sample_image_bytes(sample)
        if image_bytes is None:
            raise HTTPException(400, {"error": "unknown_sample"})
    elif image is not None:
        image_bytes = await image.read(MAX_UPLOAD_BYTES + 1)
    else:
        raise HTTPException(400, {"error": "image_missing"})
    try:
        return await process_letter(image_bytes, language)
    except ReaderError as exc:
        status = 400 if exc.reason in _USER_FIXABLE else 503
        # Only the reason id goes to the client, never model or letter text.
        raise HTTPException(status, {"error": exc.reason}) from None


@app.get("/letters/{letter_id}")
def get_letter(letter_id: UUID) -> LetterResponse:
    """Return a letter result that was produced earlier in this session."""
    record = STORE.by_letter(letter_id)
    if record is None:
        raise HTTPException(404, {"error": "letter_not_found"})
    return record.response


@app.get("/letters/{letter_id}/debug")
def get_letter_debug(letter_id: UUID) -> dict:
    """Timing and policy details for the judge panel. No letter text."""
    record = STORE.by_letter(letter_id)
    if record is None:
        raise HTTPException(404, {"error": "letter_not_found"})
    return record.debug


# Later milestones add their routes here.


def _is_api_path(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in API_PREFIXES)


def _frontend_file(url_path: str) -> Path | None:
    """Return the built file for this URL path, or None if there is not one."""
    dist = FRONTEND_DIST.resolve()
    candidate = (dist / url_path.lstrip("/")).resolve()
    # Refuse anything that escapes frontend/dist (e.g. "/../.env").
    if candidate.is_relative_to(dist) and candidate.is_file():
        return candidate
    return None


@app.exception_handler(StarletteHTTPException)
async def not_found(request: Request, exc: StarletteHTTPException) -> Response:
    """Serve the frontend for GET requests that matched no API route."""
    is_page_request = (
        exc.status_code == 404
        and request.method in ("GET", "HEAD")
        and not _is_api_path(request.url.path)
    )
    if not is_page_request:
        return await http_exception_handler(request, exc)

    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        if request.url.path == "/":
            return JSONResponse(
                {
                    "message": "Backend is running, but the frontend is not built yet.",
                    "hint": "Run: cd frontend && npm install && npm run build",
                    "health": "/health",
                }
            )
        return await http_exception_handler(request, exc)

    # A real built file (JS, CSS, images), else index.html so the SPA can route.
    return FileResponse(_frontend_file(request.url.path) or index)
