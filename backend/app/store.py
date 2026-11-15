"""Storage for letters and proposals, plus the on-disk cache of reader results.

- Letters and proposals live in memory for now (they only need to outlast one
  demo session). M7 adds the audit log for anything that must be kept.
- Reader results are cached as JSON files in backend/fixtures, named by the
  SHA-256 of the uploaded image and the language. The same photo is never sent
  to the model twice, and DEMO_OFFLINE can run from these files alone.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from app import audit
from app.reader import ReaderResult
from app.schemas import LetterResponse, PaymentIntent, ReaderOutput

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLES_DIR = FIXTURES_DIR / "samples"
SAMPLE_IDS = ("electric_bill", "suspicious_letter")


# ------------------------------------------------------------ reader cache
#
# New results go to backend/data/readings (git-ignored), never into the
# committed fixtures folder. Lookups check data/ first, then fixtures/, so the
# demo sample letters (committed on purpose) still work.


def readings_dir() -> Path:
    return audit.DATA_DIR / "readings"


def thumbs_dir() -> Path:
    return audit.DATA_DIR / "thumbs"


def _cache_path(image_sha256: str, language: str, directory: Path) -> Path:
    return directory / f"{image_sha256}_{language}.json"


def _load_from(path: Path, image_sha256: str) -> ReaderResult | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ReaderResult(
            image_sha256=image_sha256,
            # Re-validated on every load: a cache file is not trusted either.
            first=ReaderOutput.model_validate_json(json.dumps(data["first"])),
            second=ReaderOutput.model_validate_json(json.dumps(data["second"])),
            evidence_ok=data["evidence_ok"] is True,
            explanation=str(data["explanation"]),
            explanation_source=str(data["explanation_source"]),
            model_ids=tuple(data["model_ids"]),
            latency_ms=0,
        )
    except (ValueError, KeyError, TypeError):
        return None  # unreadable cache file: behave as if there were none


def load_cached_reading(image_sha256: str, language: str,
                        directory: Path | None = None) -> ReaderResult | None:
    """Return the cached reader result for this image and language, if any.

    With no `directory`, looks in backend/data/readings and then in the committed
    fixtures folder.
    """
    for folder in ([directory] if directory else [readings_dir(), FIXTURES_DIR]):
        found = _load_from(_cache_path(image_sha256, language, folder), image_sha256)
        if found is not None:
            return found
    return None


def save_cached_reading(result: ReaderResult, language: str,
                        directory: Path | None = None) -> None:
    """Save a reader result. Defaults to backend/data/readings, not the repo."""
    directory = directory or readings_dir()
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "first": result.first.model_dump(mode="json"),
        "second": result.second.model_dump(mode="json"),
        "evidence_ok": result.evidence_ok,
        "explanation": result.explanation,
        "explanation_source": result.explanation_source,
        "model_ids": list(result.model_ids),
    }
    _cache_path(result.image_sha256, language, directory).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


_SHA_RE = re.compile(r"[0-9a-f]{64}")


def save_thumbnail(image_sha256: str, jpeg: bytes) -> None:
    """Keep a small picture of the letter so an old letter can be reopened."""
    if not _SHA_RE.fullmatch(image_sha256):
        return
    thumbs_dir().mkdir(parents=True, exist_ok=True)
    (thumbs_dir() / f"{image_sha256}.jpg").write_bytes(jpeg)


def delete_letter_files(image_sha256: str) -> int:
    """Delete the saved readings (every language) and the picture of a letter.

    Only touches backend/data. The committed demo fixtures are never deleted.
    Returns how many files were removed.
    """
    if not _SHA_RE.fullmatch(image_sha256):
        return 0
    removed = 0
    paths = list(readings_dir().glob(f"{image_sha256}_*.json")) + [thumbs_dir() / f"{image_sha256}.jpg"]
    for path in paths:
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def load_thumbnail(image_sha256: str) -> bytes | None:
    if not _SHA_RE.fullmatch(image_sha256):  # never build a path from unchecked text
        return None
    path = thumbs_dir() / f"{image_sha256}.jpg"
    return path.read_bytes() if path.is_file() else None


def sample_image_bytes(sample_id: str) -> bytes | None:
    """The bytes of a built-in sample letter, or None for an unknown id."""
    if sample_id not in SAMPLE_IDS:  # fixed list: never build a path from user text
        return None
    path = SAMPLES_DIR / f"{sample_id}.jpg"
    return path.read_bytes() if path.is_file() else None


# ----------------------------------------------------- letters and proposals


@dataclass
class LetterRecord:
    """What the server remembers about one processed letter."""

    response: LetterResponse           # what the client was sent
    image_sha256: str
    intent: PaymentIntent | None       # set only when the proposal is "pay"
    expires_at: int | None             # token expiry (unix seconds)
    status: str = "proposed"           # proposed / paid / rejected
    payee_name: str | None = None      # trusted merchant name, for "pay" only
    receipt: dict | None = None        # set once paid
    thumbnail_jpeg: bytes | None = None
    requires_ack: bool = False         # the confirm call must carry acknowledged=true
    answers: list[str] = field(default_factory=list)  # answers given by /ask, for read-aloud
    debug: dict = field(default_factory=dict)


class Store:
    """In-memory records, looked up by letter id or proposal id."""

    def __init__(self) -> None:
        self._by_letter: dict[UUID, LetterRecord] = {}
        self._by_proposal: dict[UUID, LetterRecord] = {}
        self._paid_images: set[str] = set()
        self._payments: list[dict] = []

    def add(self, record: LetterRecord) -> None:
        self._by_letter[record.response.letter_id] = record
        self._by_proposal[record.response.proposal.id] = record

    def by_letter(self, letter_id: UUID) -> LetterRecord | None:
        return self._by_letter.get(letter_id)

    def by_proposal(self, proposal_id: UUID) -> LetterRecord | None:
        return self._by_proposal.get(proposal_id)

    def is_paid(self, image_sha256: str) -> bool:
        """True if this exact letter image already had a payment (one per letter)."""
        return image_sha256 in self._paid_images

    def record_payment(self, image_sha256: str, payment: dict) -> None:
        """Remember an executed payment: {nessie_id, payee_name, amount_cents, paid_on}."""
        self._paid_images.add(image_sha256)
        self._payments.append(payment)

    def payments(self) -> list[dict]:
        return list(self._payments)

    def payee_history(self, merchant_id: str) -> tuple[int, str | None]:
        """How many times we paid this merchant, and the date of the last payment."""
        paid = [p for p in self._payments if p.get("merchant_id") == merchant_id]
        last = max((p.get("paid_on") or "" for p in paid), default="") or None
        return len(paid), last

    def paid_total_cents(self) -> int:
        return sum(payment["amount_cents"] for payment in self._payments)

    def forget_image(self, image_sha256: str) -> None:
        """Drop the in-memory letters for this photo. The ledger (payments, and the
        "already paid" memory) is kept: deleting a letter must not undo a payment."""
        for letter_id, record in list(self._by_letter.items()):
            if record.image_sha256 == image_sha256:
                del self._by_letter[letter_id]
                self._by_proposal.pop(record.response.proposal.id, None)

    def reset(self) -> None:
        self.__init__()


STORE = Store()
