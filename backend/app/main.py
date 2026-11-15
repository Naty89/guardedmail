"""FastAPI entry point: API routes plus the built frontend, on one origin.

API routes are ordinary FastAPI routes. The frontend is NOT mounted as a
catch-all; it is served only when no API route matched (see `not_found`).
That way static files can never shadow an API route, whatever order routes
are added in.
"""

from pathlib import Path

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import REPO_ROOT, get_settings
from app import ask, audit, calendar_export, history, payer, tts
from app.letters import (
    current_balance_cents,
    demo_account_id,
    process_letter,
    reopen_letter,
    restore_from_audit,
)
from app.nessie import NessieError, get_read_client
from app.reader import MAX_UPLOAD_BYTES, GeminiCaller, ReaderError
from app.schemas import (
    AccountResponse,
    AskResponse,
    AuditResponse,
    BillSummary,
    HistoryResponse,
    ConfirmRequest,
    ConfirmResponse,
    LetterResponse,
    PaymentSummary,
    ReasonId,
    Receipt,
    RejectResponse,
)
from app.store import STORE, load_cached_reading, sample_image_bytes

FRONTEND_DIST: Path = REPO_ROOT / "frontend" / "dist"

# Paths that belong to the API. A 404 under these stays a JSON 404 and is
# never answered with the frontend. Add new API prefixes here.
API_PREFIXES = ("/health", "/letters", "/proposals", "/account", "/audit", "/history")

@asynccontextmanager
async def lifespan(_: FastAPI):
    """On startup, rebuild the ledger from the audit log."""
    await restore_from_audit()
    yield


app = FastAPI(title="Guarded Mail Agent", lifespan=lifespan)


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
        response = await process_letter(image_bytes, language)
        # Start making the read-aloud audio now, so Play is quick. Never awaited here.
        tts.warm_up(response.explanation, response.language)
        return response
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


@app.get("/letters/{letter_id}/calendar.ics")
async def get_letter_calendar(letter_id: UUID) -> Response:
    """The letter's due date as a calendar file, with two reminders.

    Refused for letters flagged as a possible scam, and for letters where the
    two readings did not agree on a due date.
    """
    record = STORE.by_letter(letter_id)
    if record is None:
        raise HTTPException(404, {"error": "letter_not_found"})
    letter = record.response
    if letter.scam.risk != "low":
        raise HTTPException(409, {"error": "scam_flagged"})
    due = letter.proposal.due_date
    if due is None:
        raise HTTPException(409, {"error": "no_due_date"})
    paying = letter.proposal.action == "pay"
    ics = calendar_export.build_ics(
        letter_id=letter_id, language=letter.language, due=due,
        # Merchant name from our own records for a bill; otherwise the short sender text.
        name=(letter.proposal.payee_name if paying else letter.summary.sender) or "",
        amount_cents=letter.proposal.amount_cents if paying else None)
    await audit.record("user", "calendar_exported", letter_id=letter_id, due_date=due.isoformat())
    return Response(
        ics, media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition":
                 f'inline; filename="{calendar_export.filename_for(due)}"',
                 "Cache-Control": "no-store"})


@app.get("/letters/{letter_id}/audio")
async def get_letter_audio(letter_id: UUID) -> Response:
    """The explanation read aloud (WAV), or 204 so the browser uses its own voice."""
    record = STORE.by_letter(letter_id)
    if record is None:
        raise HTTPException(404, {"error": "letter_not_found"})
    audio_bytes = await tts.get_audio(record.response.explanation, record.response.language)
    if audio_bytes is None:
        return Response(status_code=204)
    return Response(audio_bytes, media_type="audio/wav")


def _ask_caller():
    """The model caller for questions. Separate so tests can replace it."""
    return GeminiCaller()


@app.post("/letters/{letter_id}/ask")
async def ask_about_letter(
    letter_id: UUID,
    audio: UploadFile | None = File(None),
    question: str | None = Form(None),
) -> AskResponse:
    """Answer one spoken (WAV) or typed question about a letter, from the letter only.

    The answer is text for the screen. Nothing here can propose or make a payment.
    """
    record = STORE.by_letter(letter_id)
    if record is None:
        raise HTTPException(404, {"error": "letter_not_found"})
    language = record.response.language
    reading = load_cached_reading(record.image_sha256, language)
    if reading is None:
        raise HTTPException(503, {"error": "letter_text_unavailable"})

    audio_wav = None
    if question is None or not question.strip():
        question = None
        if audio is None:
            raise HTTPException(400, {"error": "question_missing"})
        audio_wav = await audio.read(ask.MAX_AUDIO_BYTES + 1)
        if len(audio_wav) > ask.MAX_AUDIO_BYTES:
            raise HTTPException(400, {"error": "audio_too_large"})
        if not tts._looks_like_wav(audio_wav):
            raise HTTPException(400, {"error": "audio_unreadable"})
    if get_settings().demo_offline:
        raise HTTPException(503, {"error": "offline"})

    try:
        heard, answer, source = await ask.answer_question(
            _ask_caller(), reading.first, language,
            audio_wav=audio_wav, question_text=question,
            scam_warning=record.response.scam.risk != "low")
    except ReaderError as exc:
        status = 400 if exc.reason == "question_unclear" else 503
        raise HTTPException(status, {"error": exc.reason}) from None

    record.answers.append(answer)
    answer_id = len(record.answers) - 1
    # Only facts about the exchange are logged, not the words.
    await audit.record("user", "question_asked", letter_id=letter_id,
                       spoken=audio_wav is not None, answer_source=source,
                       answer_id=answer_id)
    tts.warm_up(answer, language)
    return AskResponse(answer_id=answer_id, question=heard, answer=answer, source=source)


@app.get("/letters/{letter_id}/answers/{answer_id}/audio")
async def get_answer_audio(letter_id: UUID, answer_id: int) -> Response:
    """An answer read aloud (WAV), or 204 so the browser uses its own voice."""
    record = STORE.by_letter(letter_id)
    if record is None or not 0 <= answer_id < len(record.answers):
        raise HTTPException(404, {"error": "answer_not_found"})
    audio_bytes = await tts.get_audio(record.answers[answer_id], record.response.language)
    if audio_bytes is None:
        return Response(status_code=204)
    return Response(audio_bytes, media_type="audio/wav")


@app.post("/proposals/{proposal_id}/confirm")
async def confirm_proposal(proposal_id: UUID, body: ConfirmRequest) -> ConfirmResponse:
    """Pay a proposal the user confirmed.

    The body holds the token and nothing else (extra fields are rejected).
    Amount and payee come from the intent this server stored earlier.
    """
    record = STORE.by_proposal(proposal_id)
    letter_id = record.response.letter_id if record else None

    async def blocked(reason: ReasonId, **extra) -> ConfirmResponse:
        await audit.record("payer", "payment_blocked", letter_id=letter_id,
                           proposal_id=proposal_id, reason=reason.value, **extra)
        return ConfirmResponse(status="blocked", block_reason=reason)

    await audit.record("user", "confirm_requested", letter_id=letter_id,
                       proposal_id=proposal_id)
    if record is None or record.intent is None or record.expires_at is None:
        return await blocked(ReasonId.PROPOSAL_NOT_FOUND)
    if record.status == "rejected":
        return await blocked(ReasonId.PROPOSAL_REJECTED)
    if record.status != "paid" and STORE.is_paid(record.image_sha256):
        return await blocked(ReasonId.ALREADY_PAID)

    settings = get_settings()
    now = datetime.now(timezone.utc)
    result = await payer.pay(
        record.intent, body.token,
        expires_at=record.expires_at,
        now=now,
        secret=settings.token_secret,
        account_id=demo_account_id(),
        balance_cents=current_balance_cents(),
    )
    if result.steps:  # keep the steps of the attempt that reached the bank
        record.debug["payer_steps"] = list(result.steps)
    if not result.paid:
        return await blocked(result.reason, tool_calls=list(result.steps))

    record.status = "paid"
    STORE.record_payment(record.image_sha256, {
        "nessie_id": result.nessie_id, "payee_name": record.payee_name or "",
        "amount_cents": record.intent.amount_cents, "paid_on": now.date().isoformat(),
    })
    receipt = Receipt(
        nessie_id=result.nessie_id,
        payee_name=record.payee_name or "",
        amount_cents=record.intent.amount_cents,
        new_balance_cents=current_balance_cents(),  # our ledger, after this payment
    )
    record.receipt = receipt.model_dump()
    await audit.record(
        "payer", "payment_executed", letter_id=letter_id, proposal_id=proposal_id,
        image_sha256=record.image_sha256, merchant_id=record.intent.merchant_id,
        payee_name=receipt.payee_name, amount_cents=receipt.amount_cents,
        nessie_id=receipt.nessie_id, new_balance_cents=receipt.new_balance_cents,
        bill_marked=result.bill_marked, tool_calls=list(result.steps))
    return ConfirmResponse(status="paid", receipt=receipt)


@app.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: UUID) -> RejectResponse:
    """The user said no. The proposal can no longer be confirmed."""
    record = STORE.by_proposal(proposal_id)
    if record is None:
        raise HTTPException(404, {"error": "proposal_not_found"})
    if record.status == "proposed":
        record.status = "rejected"
        await audit.record("user", "proposal_rejected",
                           letter_id=record.response.letter_id, proposal_id=proposal_id)
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
        PaymentSummary(purchase_id=payment["nessie_id"], merchant_name=payment["payee_name"],
                       amount_cents=payment["amount_cents"],
                       paid_on=payment.get("paid_on") or None)
        for payment in STORE.payments()
    ]
    return AccountResponse(balance_cents=current_balance_cents(), bills=bills,
                           recent_payments=payments)


@app.get("/audit")
async def get_audit(letter_id: UUID | None = None) -> AuditResponse:
    """Audit events (for one letter if `letter_id` is given), oldest first.

    `chain_ok` is the result of re-checking every hash in the whole log.
    """
    log = audit.get_log()
    chain_ok, _ = await log.chain_ok()
    return AuditResponse(events=await log.events(letter_id), chain_ok=chain_ok)


@app.get("/history")
async def get_history() -> HistoryResponse:
    """Every letter read on this server, newest first, rebuilt from the audit log."""
    return HistoryResponse(items=history.build_history(await audit.get_log().events()))


@app.post("/history/{letter_id}/open")
async def open_history_letter(letter_id: UUID) -> LetterResponse:
    """Reopen an old letter as a fresh result (new proposal and token if payable)."""
    events = await audit.get_log().events(letter_id)
    read = next((e for e in events if e.get("event") == "letter_read"), None)
    if read is None:
        raise HTTPException(404, {"error": "letter_not_found"})
    try:
        return await reopen_letter(
            str(read["data"].get("image_sha256", "")), str(read["data"].get("language", "")))
    except ReaderError as exc:
        status = 404 if exc.reason == "letter_text_unavailable" else 400
        raise HTTPException(status, {"error": exc.reason}) from None


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
