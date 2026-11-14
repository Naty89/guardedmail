"""The letter pipeline: photo in, explanation and ONE proposed action out.

Order of work:
1. reader      (model, no tools)  -> two readings + explanation
2. scam check                     -> risk level and reasons
3. policy      (plain Python)     -> Allow with a PaymentIntent, or Block
4. controller                     -> which single action to propose
5. sign a confirmation token if, and only if, the action is "pay"

Nothing here moves money. That needs POST /proposals/{id}/confirm (M5).
"""

import time
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from app import policy
from app.config import get_settings
from app.controller import choose_action
from app.nessie import NessieError, get_read_client
from app.reader import ModelCaller, ReaderError, ReaderResult, image_sha256, read_letter
from app.schemas import (
    LANGUAGES,
    LetterResponse,
    LetterSummary,
    Proposal,
    ReaderOutput,
    ScamReason,
    ScamResult,
)
from app.store import STORE, LetterRecord, load_cached_reading, save_cached_reading

_HIGH_RISK_SIGNALS = {"gift_card", "wire", "crypto"}
_merchant_cache: list[policy.TrustedMerchant] | None = None


def interim_scam_result(first: ReaderOutput, second: ReaderOutput) -> ScamResult:
    """Scam risk from the reader's own signals. M6 replaces this with scam.py."""
    signals = list(dict.fromkeys(first.scam_signals + second.scam_signals))
    suspect = "scam_suspect" in (first.doc_type, second.doc_type)
    if suspect or _HIGH_RISK_SIGNALS & set(signals):
        risk = "high"
    elif signals:
        risk = "med"
    else:
        risk = "low"
    return ScamResult(risk=risk, reasons=[ScamReason(reason_id=s, quote="") for s in signals])


async def get_trusted_merchants() -> list[policy.TrustedMerchant]:
    """Our seeded merchants, fetched from Nessie once and then remembered.

    If Nessie cannot be reached and nothing is remembered, the list is empty,
    which means no payment can be proposed.
    """
    global _merchant_cache
    if _merchant_cache is not None:
        return _merchant_cache
    settings = get_settings()
    client = get_read_client()
    try:
        merchants = await client.list_merchants()
    except NessieError:
        return []
    finally:
        await client.aclose()
    if settings.demo_offline:
        # The offline mock holds only our own seeded merchants.
        allowed_ids = [m.get("_id") for m in merchants]
    else:
        allowed_ids = settings.nessie_merchant_ids
    found = policy.trusted_merchants(merchants, allowed_ids)
    if found:
        _merchant_cache = found
    return found


def reset_merchant_cache() -> None:
    global _merchant_cache
    _merchant_cache = None


def current_balance_cents() -> int:
    """Our own ledger: seed balance minus the payments we executed."""
    return get_settings().seed_balance_cents - STORE.paid_total_cents()


async def _get_reading(image_bytes: bytes, language: str,
                       caller: ModelCaller | None) -> tuple[ReaderResult, bool]:
    """Return (reader result, came_from_cache)."""
    sha = image_sha256(image_bytes)
    cached = load_cached_reading(sha, language)
    if cached is not None:
        return cached, True
    if get_settings().demo_offline and caller is None:
        raise ReaderError("offline_no_fixture")
    result = await read_letter(image_bytes, language, caller)
    save_cached_reading(result, language)
    return result, False


async def process_letter(image_bytes: bytes, language: str, *,
                         caller: ModelCaller | None = None,
                         today: date | None = None,
                         now: datetime | None = None) -> LetterResponse:
    """Run the whole pipeline for one uploaded letter and store the result."""
    if language not in LANGUAGES:
        raise ReaderError("language_not_supported")
    started = time.monotonic()
    now = now or datetime.now(timezone.utc)
    letter_id: UUID = uuid4()

    reading, from_cache = await _get_reading(image_bytes, language, caller)
    first, second = reading.first, reading.second
    scam = interim_scam_result(first, second)

    merchants = await get_trusted_merchants()
    verdict = policy.decide(
        first, second,
        merchants=merchants,
        balance_cents=current_balance_cents(),
        today=today or now.date(),
        letter_id=letter_id,
        scam_risk=scam.risk,
        evidence_ok=reading.evidence_ok,
        already_paid=STORE.is_paid(reading.image_sha256),
    )

    agreed_due = first.due_date if first.due_date == second.due_date else None
    action = choose_action(pay_allowed=verdict.allowed, scam_risk=scam.risk,
                           has_due_date=agreed_due is not None)

    intent = verdict.intent if action == "pay" else None
    expires_at = None
    if intent is not None:
        # Every field below comes from the PaymentIntent or our merchant record.
        expires_at = policy.expiry_for(now)
        proposal = Proposal(
            id=intent.proposal_id, action="pay",
            payee_name=verdict.merchant.name,
            amount_cents=intent.amount_cents, due_date=intent.due_date,
            expires_at=datetime.fromtimestamp(expires_at, timezone.utc),
            token=policy.sign_token(intent, expires_at, get_settings().token_secret),
        )
    else:
        proposal = Proposal(
            id=uuid4(), action=action,
            due_date=agreed_due if action == "calendar" else None,
            block_reason=verdict.reason,
        )

    response = LetterResponse(
        letter_id=letter_id, language=language, explanation=reading.explanation,
        summary=LetterSummary(
            doc_type=first.doc_type, sender=first.payee_candidate,
            amount_cents=first.amount_cents or None, due_date=first.due_date),
        scam=scam, proposal=proposal,
    )
    STORE.add(LetterRecord(
        response=response, image_sha256=reading.image_sha256,
        intent=intent, expires_at=expires_at,
        debug={
            "from_cache": from_cache,
            "reader_ms": reading.latency_ms,
            "total_ms": int((time.monotonic() - started) * 1000),
            "model_ids": list(reading.model_ids),
            "explanation_source": reading.explanation_source,
            "evidence_ok": reading.evidence_ok,
            "policy_allowed": verdict.allowed,
            "policy_reasons": [reason.value for reason in verdict.reasons],
            "match_score": verdict.match_score,
        },
    ))
    return response
