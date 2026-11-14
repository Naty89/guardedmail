"""Storage for letters and proposals, plus the on-disk cache of reader results.

- Letters and proposals live in memory for now (they only need to outlast one
  demo session). M7 adds the audit log for anything that must be kept.
- Reader results are cached as JSON files in backend/fixtures, named by the
  SHA-256 of the uploaded image and the language. The same photo is never sent
  to the model twice, and DEMO_OFFLINE can run from these files alone.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from app.reader import ReaderResult
from app.schemas import LetterResponse, PaymentIntent, ReaderOutput

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLES_DIR = FIXTURES_DIR / "samples"
SAMPLE_IDS = ("electric_bill", "suspicious_letter")


# ------------------------------------------------------------ reader cache


def _cache_path(image_sha256: str, language: str, directory: Path) -> Path:
    return directory / f"{image_sha256}_{language}.json"


def load_cached_reading(image_sha256: str, language: str,
                        directory: Path | None = None) -> ReaderResult | None:
    """Return the cached reader result for this image and language, if any."""
    path = _cache_path(image_sha256, language, directory or FIXTURES_DIR)
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


def save_cached_reading(result: ReaderResult, language: str,
                        directory: Path | None = None) -> None:
    directory = directory or FIXTURES_DIR
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
    debug: dict = field(default_factory=dict)


class Store:
    """In-memory records, looked up by letter id or proposal id."""

    def __init__(self) -> None:
        self._by_letter: dict[UUID, LetterRecord] = {}
        self._by_proposal: dict[UUID, LetterRecord] = {}
        self._paid_images: set[str] = set()

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

    def mark_paid(self, image_sha256: str) -> None:
        self._paid_images.add(image_sha256)

    def paid_total_cents(self) -> int:
        return sum(r.intent.amount_cents for r in self._by_letter.values()
                   if r.status == "paid" and r.intent is not None)

    def reset(self) -> None:
        self.__init__()


STORE = Store()
