"""History: the list of letters you have read, rebuilt from the audit log.

There is no separate table. Every fact here was already recorded as an audit
event, so the history can never disagree with the log. The same photo read
twice (or reopened) shows once, with its latest state.

Status:
  paid      a payment was made for this letter
  flagged   the scam check raised a warning
  declined  you said "No, don't pay"
  open      a payment was offered and you have not decided
  info      nothing to pay (a notice, an unknown payee, a date to remember)
"""

from datetime import date, datetime

from app.schemas import HistoryItem


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def build_history(events: list[dict]) -> list[HistoryItem]:
    """Turn audit events (oldest first) into history items (newest first)."""
    paid_images: set[str] = set()
    rejected_letters: set[str] = set()
    letters: dict[str, dict] = {}

    for event in events:
        letter_id = event.get("letter_id")
        data = event.get("data") or {}
        kind = event.get("event")
        if kind == "payment_executed" and data.get("image_sha256"):
            paid_images.add(data["image_sha256"])
        elif kind == "proposal_rejected" and letter_id:
            rejected_letters.add(letter_id)
        elif kind == "letter_read" and letter_id:
            letters[letter_id] = {"read": event, "ts": event["ts"], "letter_id": letter_id}
        elif kind == "scam_checked" and letter_id in letters:
            letters[letter_id]["risk"] = data.get("risk", "low")
        elif kind == "policy_decided" and letter_id in letters:
            letters[letter_id]["action"] = data.get("controller_action")

    # One item per photo and language: keep the latest time it was read.
    latest: dict[tuple[str, str], dict] = {}
    rejected_images: set[str] = set()
    for letter in letters.values():
        data = letter["read"]["data"]
        key = (data.get("image_sha256", ""), data.get("language", "en"))
        if letter["letter_id"] in rejected_letters:
            rejected_images.add(key[0])
        if key not in latest or letter["ts"] >= latest[key]["ts"]:
            latest[key] = letter

    items = []
    for (sha, language), letter in latest.items():
        first = letter["read"]["data"].get("first", {})
        risk = letter.get("risk", "low")
        if sha in paid_images:
            status = "paid"
        elif risk != "low":
            status = "flagged"
        elif sha in rejected_images:
            status = "declined"
        elif letter.get("action") == "pay":
            status = "open"
        else:
            status = "info"
        due = first.get("due_date")
        items.append(HistoryItem(
            letter_id=letter["letter_id"], language=language, ts=_parse_time(letter["ts"]),
            sender=first.get("payee_candidate", ""), doc_type=first.get("doc_type", "other"),
            amount_cents=first.get("amount_cents") or None,
            due_date=date.fromisoformat(due) if due else None,
            risk=risk, status=status))
    return sorted(items, key=lambda item: item.ts, reverse=True)
