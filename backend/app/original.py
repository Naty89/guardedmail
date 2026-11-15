"""The original text next to the explanation: which words back each claim.

The reader transcribes the photo. We show that text to the user (it is their own
letter) and mark the amount, the due date and the sender, so they can see where
each claim came from and spot a misread or mistranslated detail.

Marking is plain pattern matching on the reader's own claims. This text goes to
the user's screen only; it never goes to a model, the controller or the payer.
"""

import re

from app.reader import amount_span, date_span
from app.schemas import OriginalHighlight, ReaderOutput

MAX_ORIGINAL_CHARS = 6000


def highlights(reading: ReaderOutput, text: str) -> list[OriginalHighlight]:
    """Non-overlapping marks for the amount, due date and sender found in `text`."""
    found: list[OriginalHighlight] = []

    def add(kind: str, span: tuple[int, int] | None) -> None:
        if span and 0 <= span[0] < span[1] <= len(text):
            found.append(OriginalHighlight(start=span[0], end=span[1], kind=kind))

    if reading.amount_cents > 0:
        add("amount", amount_span(reading.amount_cents, text))
    if reading.due_date is not None:
        add("due_date", date_span(reading.due_date, text))
    sender = reading.payee_candidate.strip()
    if sender:
        match = re.search(re.escape(sender), text, re.IGNORECASE)
        add("sender", match.span() if match else None)

    found.sort(key=lambda mark: mark.start)
    kept: list[OriginalHighlight] = []
    for mark in found:              # drop a mark that overlaps the one before it
        if not kept or mark.start >= kept[-1].end:
            kept.append(mark)
    return kept
