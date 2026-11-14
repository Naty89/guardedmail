"""FastAPI entry point: API routes plus the built frontend, on one origin.

API routes are ordinary FastAPI routes. The frontend is NOT mounted as a
catch-all; it is served only when no API route matched (see `not_found`).
That way static files can never shadow an API route, whatever order routes
are added in.
"""

from pathlib import Path

from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import REPO_ROOT, get_settings
from app import payer
from app.letters import current_balance_cents, demo_account_id, process_letter
from app.nessie import NessieError, get_read_client
from app.reader import MAX_UPLOAD_BYTES, ReaderError
from app.schemas import (
    AccountResponse,
    BillSummary,
    ConfirmRequest,
    ConfirmResponse,
    LetterResponse,
    PaymentSummary,
    ReasonId,
    Receipt,
    RejectResponse,
)
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


@app.get("/letters/{letter_id}/image")
def get_letter_image(letter_id: UUID) -> Response:
    """A small picture of the letter, shown beside the confirm question."""
    record = STORE.by_letter(letter_id)
    if record is None or record.thumbnail_jpeg is None:
        raise HTTPException(404, {"error": "letter_not_found"})
    return Response(record.thumbnail_jpeg, media_type="image/jpeg")


@app.post("/proposals/{proposal_id}/confirm")
async def confirm_proposal(proposal_id: UUID, body: ConfirmRequest) -> ConfirmResponse:
    """Pay a proposal the user confirmed.

    The body holds the token and nothing else (extra fields are rejected).
    Amount and payee come from the intent this server stored earlier.
    """
    record = STORE.by_proposal(proposal_id)
    if record is None or record.intent is None or record.expires_at is None:
        return ConfirmResponse(status="blocked", block_reason=ReasonId.PROPOSAL_NOT_FOUND)
    if record.status == "rejected":
        return ConfirmResponse(status="blocked", block_reason=ReasonId.PROPOSAL_REJECTED)
    if record.status != "paid" and STORE.is_paid(record.image_sha256):
        return ConfirmResponse(status="blocked", block_reason=ReasonId.ALREADY_PAID)

    settings = get_settings()
    result = await payer.pay(
        record.intent, body.token,
        expires_at=record.expires_at,
        now=datetime.now(timezone.utc),
        secret=settings.token_secret,
        account_id=demo_account_id(),
        balance_cents=current_balance_cents(),
    )
    if result.steps:  # keep the steps of the attempt that reached the bank
        record.debug["payer_steps"] = list(result.steps)
    if not result.paid:
        return ConfirmResponse(status="blocked", block_reason=result.reason)

    record.status = "paid"
    STORE.mark_paid(record.image_sha256)
    record.receipt = Receipt(
        nessie_id=result.nessie_id,
        payee_name=record.payee_name or "",
        amount_cents=record.intent.amount_cents,
        new_balance_cents=current_balance_cents(),  # our ledger, after this payment
    ).model_dump()
    record.debug["paid_at"] = datetime.now(timezone.utc).isoformat()
    return ConfirmResponse(status="paid", receipt=Receipt(**record.receipt))


@app.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: UUID) -> RejectResponse:
    """The user said no. The proposal can no longer be confirmed."""
    record = STORE.by_proposal(proposal_id)
    if record is None:
        raise HTTPException(404, {"error": "proposal_not_found"})
    if record.status == "proposed":
        record.status = "rejected"
    return RejectResponse()


@app.get("/account")
async def get_account() -> AccountResponse:
    """Balance from our own ledger, bills from the bank, payments we made."""
    settings = get_settings()
    bills: list[BillSummary] = []
    client = get_read_client()
    try:
        for bill in await client.list_account_bills(demo_account_id()):
            bills.append(BillSummary(
                bill_id=str(bill.get("_id", "")), payee=str(bill.get("payee", "")),
                amount_cents=round(float(bill.get("payment_amount") or 0) * 100),
                due_date=bill.get("payment_date") or None,
                status=str(bill.get("status", "")),
            ))
    except (NessieError, ValueError):
        bills = []  # the bank is unreachable: still show our own ledger
    finally:
        await client.aclose()
    payments = [
        PaymentSummary(
            purchase_id=record.receipt["nessie_id"], merchant_name=record.payee_name or "",
            amount_cents=record.intent.amount_cents,
            paid_on=(record.debug.get("paid_at") or "")[:10] or None)
        for record in STORE.paid_records() if record.receipt
    ]
    return AccountResponse(balance_cents=current_balance_cents(), bills=bills,
                           recent_payments=payments)


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
