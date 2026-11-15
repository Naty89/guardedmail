"""Payment policy: the ONLY path from reader output to money. Plain Python, no model.

Two jobs:

1. `decide()` looks at two independent readings of a letter and either builds a
   `PaymentIntent` (Allow) or returns the reasons it refused (Block).
2. `sign_token()` / `verify_token()` make and check the confirmation token the
   user must send back before the payer may act.

Rules of this module:
- It never calls a model and never talks to the network.
- It never reads `raw_text`. Letter text cannot influence a decision here.
- `payee_candidate` is used for one thing only: comparing it with the names of
  merchants we already trust. It is never copied into the result.
- Everything in the returned `PaymentIntent` comes from our own data (the trusted
  merchant record, ids we generated) or from numbers both readings agreed on.
- When in doubt, block. A missing input is a reason to block, never to allow.
"""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Sequence
from uuid import UUID, uuid4

from rapidfuzz import fuzz

from app.schemas import (
    MAX_AMOUNT_CENTS,
    MERCHANT_ID_PATTERN,
    PAYEE_MATCH_THRESHOLD,
    TOKEN_TTL_SECONDS,
    PaymentIntent,
    ReaderOutput,
    ReasonId,
)

DUE_DATE_PAST_DAYS = 30     # a bill may be up to 30 days overdue
DUE_DATE_FUTURE_DAYS = 365  # or due up to a year from now
MIN_SECRET_CHARS = 16


# ------------------------------------------------------------------- data


@dataclass(frozen=True)
class TrustedMerchant:
    """A merchant we seeded in Nessie ourselves. Never built from letter content."""

    merchant_id: str
    name: str


@dataclass(frozen=True)
class Verdict:
    """The result of `decide()`.

    `allowed` is True only when `intent` is set. `reasons` lists every rule that
    failed (empty on Allow); `reason` is the first one, for simple callers.
    """

    allowed: bool
    reasons: tuple[ReasonId, ...]
    intent: PaymentIntent | None = None
    merchant: TrustedMerchant | None = None  # the trusted record that matched
    match_score: float | None = None         # fuzzy score of that match

    @property
    def reason(self) -> ReasonId | None:
        return self.reasons[0] if self.reasons else None


def trusted_merchants(nessie_merchants: Iterable[dict],
                      allowed_ids: Sequence[str]) -> list[TrustedMerchant]:
    """Keep only the Nessie merchants whose id is in our own seeded list.

    `allowed_ids` comes from settings (NESSIE_MERCHANT_IDS). If it is empty the
    result is empty, so no payment is possible.
    """
    allowed = set(allowed_ids)
    result = []
    for merchant in nessie_merchants:
        merchant_id = merchant.get("_id")
        name = merchant.get("name")
        if (isinstance(merchant_id, str) and merchant_id in allowed
                and MERCHANT_ID_PATTERN.fullmatch(merchant_id)
                and isinstance(name, str) and name.strip()):
            result.append(TrustedMerchant(merchant_id=merchant_id, name=name))
    return result


# ------------------------------------------------------------ payee match


def _normalise(name: str) -> str:
    """Lower-case and collapse spaces so 'ACME  Power' equals 'acme power'."""
    return " ".join(name.casefold().split())


def match_merchant(payee_candidate: str, merchants: Sequence[TrustedMerchant]
                   ) -> tuple[TrustedMerchant | None, float]:
    """Find the one trusted merchant whose name matches the payee, if any.

    Uses rapidfuzz's plain `ratio` on the whole string (not a partial match), so
    a trusted name buried inside a longer sentence does not count. A tie between
    two different merchants is treated as no match.
    """
    payee = _normalise(payee_candidate)
    if not payee:
        return None, 0.0
    scored = sorted(
        ((fuzz.ratio(payee, _normalise(m.name)), m) for m in merchants),
        key=lambda pair: pair[0], reverse=True)
    if not scored or scored[0][0] < PAYEE_MATCH_THRESHOLD:
        return None, scored[0][0] if scored else 0.0
    best_score, best = scored[0]
    if len(scored) > 1 and scored[1][0] == best_score \
            and scored[1][1].merchant_id != best.merchant_id:
        return None, best_score  # ambiguous
    return best, best_score


# ----------------------------------------------------------------- decide


def decide(
    first: ReaderOutput,
    second: ReaderOutput,
    *,
    merchants: Sequence[TrustedMerchant],
    balance_cents: int,
    today: date,
    letter_id: UUID,
    scam_risk: str | None = None,
    evidence_ok: bool = True,
    already_paid: bool = False,
) -> Verdict:
    """Decide whether a payment may be PROPOSED for this letter.

    first, second  the two independent extraction passes
    merchants      trusted merchants only (see `trusted_merchants`)
    balance_cents  from our own ledger
    scam_risk      "low" / "med" / "high" from scam.py, or None if not run yet.
                   Anything other than "low" or None blocks. "low" allows
                   nothing by itself: every other rule still has to pass.
    evidence_ok    False when the reader could not find the amount or the date
                   in its own transcription
    already_paid   True when this letter already had a money action

    An Allow only means the user may be asked. The payer still needs a valid
    confirmation token.
    """
    reasons: list[ReasonId] = []

    def block(reason: ReasonId) -> None:
        if reason not in reasons:
            reasons.append(reason)

    # 1. Scam checks come first and can only ever remove the pay option.
    if first.doc_type == "scam_suspect" or second.doc_type == "scam_suspect":
        block(ReasonId.DOC_TYPE_SCAM_SUSPECT)
    if first.scam_signals or second.scam_signals:
        block(ReasonId.SCAM_SIGNAL_PRESENT)
    if scam_risk not in (None, "low"):
        block(ReasonId.SCAM_SIGNAL_PRESENT)

    # 2. One money action per letter.
    if already_paid:
        block(ReasonId.ALREADY_PAID)

    # 3. Both readings must agree exactly on the amount and the due date.
    if first.amount_cents != second.amount_cents or first.due_date != second.due_date:
        block(ReasonId.READINGS_DISAGREE)

    # 4. Only bills can be paid.
    if first.doc_type != "bill" or second.doc_type != "bill":
        block(ReasonId.NOT_A_BILL)

    # 5. The amount and date must appear in the transcription.
    if evidence_ok is not True:
        block(ReasonId.EVIDENCE_MISSING)

    # 5b. If the reader itself says it could not read the letter clearly, do not
    #     offer to pay it. A blurry photo is a reason to retake it.
    if "low" in (first.confidence, second.confidence):
        block(ReasonId.LOW_CONFIDENCE)

    # 6. Amount: 0 < amount <= min(cap, balance). Checked on both readings.
    for amount in (first.amount_cents, second.amount_cents):
        if type(amount) is not int or amount <= 0:
            block(ReasonId.AMOUNT_NOT_POSITIVE)
        elif amount > MAX_AMOUNT_CENTS:
            block(ReasonId.AMOUNT_OVER_CAP)
        elif type(balance_cents) is not int or amount > balance_cents:
            block(ReasonId.AMOUNT_OVER_BALANCE)

    # 7. Due date: a real date inside the allowed window.
    earliest = today - timedelta(days=DUE_DATE_PAST_DAYS)
    latest = today + timedelta(days=DUE_DATE_FUTURE_DAYS)
    for due in (first.due_date, second.due_date):
        if due is None:
            block(ReasonId.DUE_DATE_MISSING)
        elif type(due) is not date or not earliest <= due <= latest:
            block(ReasonId.DUE_DATE_OUT_OF_RANGE)

    # 8. Payee: both readings must match the SAME trusted merchant.
    merchant, score = match_merchant(first.payee_candidate, merchants)
    other, other_score = match_merchant(second.payee_candidate, merchants)
    if merchant is None or other is None or merchant.merchant_id != other.merchant_id:
        block(ReasonId.UNKNOWN_PAYEE)
        merchant = None

    if reasons or merchant is None:
        return Verdict(allowed=False, reasons=tuple(reasons))

    intent = PaymentIntent(
        proposal_id=uuid4(),
        letter_id=letter_id,
        merchant_id=merchant.merchant_id,   # from our trusted record
        amount_cents=first.amount_cents,    # equal in both readings (rule 3)
        due_date=first.due_date,
    )
    return Verdict(allowed=True, reasons=(), intent=intent, merchant=merchant,
                   match_score=min(score, other_score))


# ----------------------------------------------------- confirmation token


def expiry_for(now: datetime) -> int:
    """Unix time (whole seconds) at which a token created `now` stops working."""
    return int(now.timestamp()) + TOKEN_TTL_SECONDS


def sign_token(intent: PaymentIntent, expires_at: int, secret: str) -> str:
    """HMAC-SHA256 over proposal_id|merchant_id|amount_cents|expiry, as hex.

    None of the four parts can contain "|", so the message is unambiguous.
    """
    if not isinstance(secret, str) or len(secret) < MIN_SECRET_CHARS:
        raise ValueError(
            f"TOKEN_SECRET must be set and at least {MIN_SECRET_CHARS} characters")
    message = f"{intent.proposal_id}|{intent.merchant_id}|{intent.amount_cents}|{expires_at}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


class UsedTokens:
    """Remembers which proposals have already been confirmed (single use).

    In memory for now; M5 can back it with the database. One entry per proposal,
    so this is also the idempotency record for that proposal.
    """

    def __init__(self) -> None:
        self._used: set[UUID] = set()

    def is_used(self, proposal_id: UUID) -> bool:
        return proposal_id in self._used

    def mark_used(self, proposal_id: UUID) -> None:
        self._used.add(proposal_id)


def verify_token(
    token: str,
    intent: PaymentIntent,
    expires_at: int,
    *,
    now: datetime,
    secret: str,
    used: UsedTokens,
) -> ReasonId | None:
    """Check a confirmation token. Returns None when valid, else the reason.

    `intent` and `expires_at` must be the copies the SERVER stored when it made
    the proposal. Nothing about amount or payee is ever taken from the client.
    A valid token is marked used here, so the same call can never pass twice.
    """
    expected = sign_token(intent, expires_at, secret)
    if not isinstance(token, str) or not hmac.compare_digest(
            token.encode("utf-8", "replace"), expected.encode()):
        return ReasonId.TOKEN_INVALID
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if int(now.timestamp()) >= expires_at:
        return ReasonId.TOKEN_EXPIRED
    if used.is_used(intent.proposal_id):
        return ReasonId.TOKEN_REUSED
    used.mark_used(intent.proposal_id)
    return None
