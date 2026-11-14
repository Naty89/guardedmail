"""Audit log: an append-only, hash-chained record of every decision.

Each event stores the hash of the event before it (`prev_hash`) and its own
`hash`, which covers everything in the event including `prev_hash`. Changing or
removing any earlier event breaks every hash after it, and `verify_chain`
finds the first broken link.

Storage: MongoDB when MONGODB_URI is set, otherwise a local JSONL file under
backend/data/ (also used with DEMO_OFFLINE=1). Events are only ever appended.

Transcriptions (`raw_text`) never go into the audit log. They are written to a
separate quarantine store that no model call and no other module reads.
"""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
AUDIT_FILE = "audit.jsonl"
QUARANTINE_FILE = "quarantine_raw_text.jsonl"
GENESIS_HASH = "0" * 64  # prev_hash of the very first event

ACTORS = ("reader", "policy", "user", "payer")


def compute_hash(event: dict) -> str:
    """SHA-256 over the event (without its own `hash`), with keys in a fixed order."""
    body = {key: value for key, value in event.items() if key != "hash"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_chain(events: list[dict]) -> tuple[bool, int | None]:
    """Check a full log, oldest first. Returns (ok, index of the first bad event)."""
    previous = GENESIS_HASH
    for index, event in enumerate(events):
        if event.get("prev_hash") != previous or event.get("hash") != compute_hash(event):
            return False, index
        previous = event["hash"]
    return True, None


# ---------------------------------------------------------------- backends


class JsonlBackend:
    """One JSON object per line, appended to a local file."""

    def __init__(self, directory: Path):
        self.directory = directory

    def _read(self, name: str) -> list[dict]:
        path = self.directory / name
        if not path.is_file():
            return []
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def _append(self, name: str, row: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    async def all_events(self) -> list[dict]:
        return self._read(AUDIT_FILE)

    async def append_event(self, event: dict) -> None:
        self._append(AUDIT_FILE, event)

    async def append_quarantine(self, row: dict) -> None:
        self._append(QUARANTINE_FILE, row)


class MongoBackend:
    """Same interface on MongoDB (collections `audit` and `quarantine_raw_text`).

    NOT yet tried against a real MongoDB Atlas cluster.
    """

    def __init__(self, uri: str, database: str = "guarded_mail"):
        from motor.motor_asyncio import AsyncIOMotorClient

        self._db = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)[database]

    async def all_events(self) -> list[dict]:
        cursor = self._db.audit.find({}, {"_id": 0}).sort("seq", 1)
        return [event async for event in cursor]

    async def append_event(self, event: dict) -> None:
        await self._db.audit.insert_one(dict(event))

    async def append_quarantine(self, row: dict) -> None:
        await self._db.quarantine_raw_text.insert_one(dict(row))


# --------------------------------------------------------------------- log


class AuditLog:
    """Appends events and keeps the hash chain. One instance per process."""

    def __init__(self, backend):
        self._backend = backend
        self._lock = asyncio.Lock()   # one writer at a time keeps the chain in order
        self._last_hash: str | None = None
        self._next_seq = 0

    async def _load_tail(self) -> None:
        if self._last_hash is None:
            events = await self._backend.all_events()
            self._last_hash = events[-1]["hash"] if events else GENESIS_HASH
            self._next_seq = len(events)

    async def record(self, actor: str, event: str, *, letter_id: UUID | str | None = None,
                     proposal_id: UUID | str | None = None, **data: Any) -> dict:
        """Append one event. `data` must be JSON-ready and must not hold raw_text."""
        if actor not in ACTORS:
            raise ValueError(f"unknown actor {actor!r}")
        if "raw_text" in json.dumps(data, default=str):
            raise ValueError("raw_text must go to the quarantine store, not the audit log")
        async with self._lock:
            await self._load_tail()
            entry = {
                "seq": self._next_seq,
                "ts": datetime.now(timezone.utc).isoformat(),
                "letter_id": str(letter_id) if letter_id else None,
                "proposal_id": str(proposal_id) if proposal_id else None,
                "actor": actor,
                "event": event,
                "data": json.loads(json.dumps(data, default=str)),
                "prev_hash": self._last_hash,
            }
            entry["hash"] = compute_hash(entry)
            await self._backend.append_event(entry)
            self._last_hash = entry["hash"]
            self._next_seq += 1
            return entry

    async def events(self, letter_id: UUID | str | None = None) -> list[dict]:
        """All events, oldest first, or only those for one letter."""
        events = await self._backend.all_events()
        if letter_id is None:
            return events
        return [event for event in events if event.get("letter_id") == str(letter_id)]

    async def chain_ok(self) -> tuple[bool, int | None]:
        return verify_chain(await self._backend.all_events())

    async def quarantine_raw_text(self, letter_id: UUID | str, image_sha256: str,
                                  texts: list[str]) -> None:
        """Store transcriptions apart from everything else. Nothing reads them back."""
        await self._backend.append_quarantine({
            "ts": datetime.now(timezone.utc).isoformat(),
            "letter_id": str(letter_id),
            "image_sha256": image_sha256,
            "raw_texts": texts,
        })


_log: AuditLog | None = None


def get_log() -> AuditLog:
    """The process-wide audit log, created on first use from the settings."""
    global _log
    if _log is None:
        from app.config import get_settings

        settings = get_settings()
        if settings.mongodb_uri and not settings.demo_offline:
            _log = AuditLog(MongoBackend(settings.mongodb_uri))
        else:
            _log = AuditLog(JsonlBackend(DATA_DIR))
    return _log


def reset_log() -> None:
    """Forget the cached log object (tests, or after the files were moved)."""
    global _log
    _log = None


async def record(actor: str, event: str, **fields: Any) -> dict | None:
    """Append an event; a storage failure must never break the user's request."""
    try:
        return await get_log().record(actor, event, **fields)
    except ValueError:
        raise  # programming error (bad actor, raw_text): fail loudly
    except Exception:
        return None
