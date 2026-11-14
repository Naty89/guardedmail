"""Shared data models. This is the leaf module: it imports nothing from `app`.

Trust boundaries (read this before using the models):

- `ReaderOutput` is written by a vision model that has just read an untrusted
  letter. Treat every field as untrusted data, never as instructions.
- `PaymentIntent` is the ONLY object that crosses to the controller/payer. It is
  built by policy code and has no field that can hold model-written free text.
- The API models at the bottom are our own outputs, so they are not strict.
"""

import re
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------- constants

MAX_AMOUNT_CENTS = 50000  # hard cap on any single payment ($500.00)
TOKEN_TTL_SECONDS = 300  # a confirmation token lives for 5 minutes
PAYEE_MATCH_THRESHOLD = 90  # rapidfuzz score needed to match a known merchant

MAX_PAYEE_CHARS = 60
MAX_RAW_TEXT_CHARS = 20000
MAX_SCAM_SIGNALS = 7  # one slot per distinct signal
MAX_QUOTE_CHARS = 200

# Letters, digits, underscore, space and . , & ' - only. No newlines, colons,
# slashes, brackets or semicolons, so a sentence of instructions rarely fits.
PAYEE_PATTERN = re.compile(r"[\w .,&'\-]+")
# Nessie ids are 24-char hex; the offline mock uses short readable ids.
MERCHANT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")

# code -> (name shown in the language picker, text-to-speech locale)
LANGUAGES: dict[str, tuple[str, str]] = {
    "en": ("English", "en-US"),
    "es": ("Español", "es-ES"),
    "hi": ("हिन्दी", "hi-IN"),
    "te": ("తెలుగు", "te-IN"),
    "ta": ("தமிழ்", "ta-IN"),
    "pt": ("Português", "pt-BR"),
    "zh": ("中文", "cmn-CN"),
    "ar": ("العربية", "ar-XA"),
    "am": ("አማርኛ", "am-ET"),
}
RTL = {"ar"}  # languages rendered right-to-left
VOICE_ENABLED = {"en", "es", "hi", "te", "ta", "pt"}  # languages with read-aloud

LanguageCode = Literal["en", "es", "hi", "te", "ta", "pt", "zh", "ar", "am"]

DocType = Literal["bill", "notice", "appointment", "government", "scam_suspect", "other"]
ScamSignal = Literal[
    "urgency", "gift_card", "wire", "crypto", "threat", "mismatch_sender", "unknown_payee"
]
Confidence = Literal["low", "med", "high"]
RiskLevel = Literal["low", "med", "high"]
ProposalAction = Literal["pay", "calendar", "flag", "ask_user"]
AuditActor = Literal["reader", "policy", "user", "payer"]


class ReasonId(str, Enum):
    """Machine-readable reasons why the policy or payer blocked an action."""

    READINGS_DISAGREE = "readings_disagree"
    UNKNOWN_PAYEE = "unknown_payee"
    SCAM_SIGNAL_PRESENT = "scam_signal_present"
    DOC_TYPE_SCAM_SUSPECT = "doc_type_scam_suspect"
    AMOUNT_NOT_POSITIVE = "amount_not_positive"
    AMOUNT_OVER_CAP = "amount_over_cap"
    AMOUNT_OVER_BALANCE = "amount_over_balance"
    DUE_DATE_MISSING = "due_date_missing"
    DUE_DATE_OUT_OF_RANGE = "due_date_out_of_range"
    EVIDENCE_MISSING = "evidence_missing"
    NOT_A_BILL = "not_a_bill"
    TOKEN_INVALID = "token_invalid"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_REUSED = "token_reused"
    ALREADY_PAID = "already_paid"
    PROPOSAL_NOT_FOUND = "proposal_not_found"
    PROPOSAL_REJECTED = "proposal_rejected"
    PAYMENT_FAILED = "payment_failed"


# ------------------------------------------------- untrusted: reader output


class ReaderOutput(BaseModel):
    """What the vision model extracted from one letter. Untrusted data.

    Parse the model's JSON with `ReaderOutput.model_validate_json(text)`.
    The model is strict, so `model_validate(dict)` rejects an ISO date string
    for `due_date` (it wants a real `date`); JSON mode accepts the string.

    Length, pattern and range limits are checked in validators (code), because
    Gemini's structured output ignores maxLength/pattern in the JSON schema.

    `payee_candidate` may be "" when the letter names no payee (for example a
    notice). An empty payee can never match a merchant, so it can never be paid.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    doc_type: DocType
    payee_candidate: str
    amount_cents: int
    currency: Literal["USD"]
    due_date: date | None
    scam_signals: list[ScamSignal]
    confidence: Confidence
    raw_text: str  # transcription; stays on the reader side only

    @field_validator("payee_candidate")
    @classmethod
    def _check_payee(cls, value: str) -> str:
        if value == "":
            return value
        if len(value) > MAX_PAYEE_CHARS:
            raise ValueError(f"payee_candidate longer than {MAX_PAYEE_CHARS} chars")
        if not PAYEE_PATTERN.fullmatch(value):
            raise ValueError("payee_candidate contains disallowed characters")
        return value

    @field_validator("amount_cents")
    @classmethod
    def _check_amount(cls, value: int) -> int:
        if not 0 <= value <= MAX_AMOUNT_CENTS:
            raise ValueError(f"amount_cents must be 0..{MAX_AMOUNT_CENTS}")
        return value

    @field_validator("scam_signals")
    @classmethod
    def _check_signals(cls, value: list[str]) -> list[str]:
        if len(value) > MAX_SCAM_SIGNALS:
            raise ValueError(f"more than {MAX_SCAM_SIGNALS} scam_signals")
        return value

    @field_validator("raw_text")
    @classmethod
    def _check_raw_text(cls, value: str) -> str:
        if len(value) > MAX_RAW_TEXT_CHARS:
            raise ValueError(f"raw_text longer than {MAX_RAW_TEXT_CHARS} chars")
        return value

    def without_raw_text(self) -> dict[str, Any]:
        """Return the fields as a JSON-ready dict minus raw_text (for the audit log)."""
        return self.model_dump(mode="json", exclude={"raw_text"})


# --------------------------------------------- trusted: crosses to the payer


class PaymentIntent(BaseModel):
    """The ONLY object that crosses to the controller/payer. No free text.

    Built by policy code from Python values (real `UUID` and `date` objects).
    `merchant_id` comes from Nessie's merchant list, never from a model.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    proposal_id: UUID
    letter_id: UUID
    merchant_id: str
    amount_cents: int
    due_date: date

    @field_validator("merchant_id")
    @classmethod
    def _check_merchant_id(cls, value: str) -> str:
        if not MERCHANT_ID_PATTERN.fullmatch(value):
            raise ValueError("merchant_id must be 1-64 chars of A-Z a-z 0-9 _ -")
        return value

    @field_validator("amount_cents")
    @classmethod
    def _check_amount(cls, value: int) -> int:
        if not 1 <= value <= MAX_AMOUNT_CENTS:
            raise ValueError(f"amount_cents must be 1..{MAX_AMOUNT_CENTS}")
        return value


# ------------------------------------------------------------- API models


class ScamReason(BaseModel):
    """One scam signal plus a short quote from the letter that triggered it."""

    reason_id: ScamSignal
    quote: str = Field(max_length=MAX_QUOTE_CHARS)  # untrusted text, display only


class ScamResult(BaseModel):
    """Scam check result for one letter."""

    risk: RiskLevel
    reasons: list[ScamReason] = []


class Proposal(BaseModel):
    """The single action proposed for a letter."""

    id: UUID
    action: ProposalAction
    payee_name: str | None = None  # trusted merchant name from Nessie, or null
    amount_cents: int | None = None
    due_date: date | None = None
    expires_at: datetime | None = None
    token: str | None = None
    block_reason: ReasonId | None = None


class LetterSummary(BaseModel):
    """Key facts as the reader saw them. Untrusted: for display to the user only.

    These never decide anything. Payment details come from `Proposal`.
    """

    doc_type: DocType
    sender: str  # the reader's payee_candidate; may be ""
    amount_cents: int | None = None
    due_date: date | None = None


class LetterResponse(BaseModel):
    """Response of POST /letters."""

    letter_id: UUID
    language: LanguageCode
    explanation: str
    summary: LetterSummary
    scam: ScamResult
    proposal: Proposal


class ConfirmRequest(BaseModel):
    """Body of POST /proposals/{id}/confirm. Token only: no amount, no payee."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)


class Receipt(BaseModel):
    """Proof of a completed mock payment. Every field comes from our own records."""

    nessie_id: str            # id of the purchase at the mock bank
    payee_name: str           # trusted merchant name
    amount_cents: int
    new_balance_cents: int    # from our own ledger


class ConfirmResponse(BaseModel):
    """Response of POST /proposals/{id}/confirm."""

    status: Literal["paid", "blocked"]
    receipt: Receipt | None = None
    block_reason: ReasonId | None = None


class RejectResponse(BaseModel):
    """Response of POST /proposals/{id}/reject."""

    status: Literal["rejected"] = "rejected"


class BillSummary(BaseModel):
    """One bill on the demo account."""

    bill_id: str
    payee: str
    amount_cents: int
    due_date: date | None = None
    status: str


class PaymentSummary(BaseModel):
    """One past payment (a Nessie purchase) on the demo account."""

    purchase_id: str
    merchant_name: str
    amount_cents: int
    paid_on: date | None = None


class AccountResponse(BaseModel):
    """Response of GET /account."""

    balance_cents: int
    bills: list[BillSummary] = []
    recent_payments: list[PaymentSummary] = []


class AuditEvent(BaseModel):
    """One entry in the hash-chained audit log (loose for now)."""

    ts: datetime
    letter_id: str | None = None
    proposal_id: str | None = None
    actor: AuditActor
    event: str
    prev_hash: str
    hash: str
    data: dict[str, Any] = {}


class AuditResponse(BaseModel):
    """Response of GET /audit."""

    events: list[AuditEvent] = []
