"""Guidance for the user: how sure are we, and what should they do next.

Everything here is plain code on the reader's two readings and the scam
result. It never calls a model, and it never decides a payment: it only picks
the honest wording ("possible scam", "we can't tell", "no warning signs") and
which notes to show (time-sensitive, legal, medical).

"No warning signs found" is never "safe". A false sense of safety is the worst
way this app can fail, so uncertainty is its own state, not a quiet "low".
"""

import re
from datetime import date, timedelta

from app.schemas import CheckState, Notice, ReaderOutput

TIME_SENSITIVE_DAYS = 7  # due within a week (or already overdue) counts as time-sensitive

_LEGAL = re.compile(
    r"\b(evict\w*|notice to quit|summons|court|lawsuit|sue|sued|foreclos\w*|garnish\w*|"
    r"collection agency|debt collector|attorney|lawyer|judg(?:e)?ment|legal action|subpoena|"
    r"bankruptcy|repossess\w*)\b", re.IGNORECASE)
_MEDICAL = re.compile(
    r"\b(diagnos\w*|prescription|medical|patient|procedure|test results?|lab results?|"
    r"treatment|explanation of benefits|insurance claim|clinic|hospital|physician|"
    r"copay|co-pay|deductible)\b", re.IGNORECASE)
_PRESSURE = re.compile(
    r"\b(final notice|past due|overdue|last chance|deadline|disconnect\w*|shut off|"
    r"late fee)\b", re.IGNORECASE)


def check_state(*, scam_risk: str, first: ReaderOutput, second: ReaderOutput,
                evidence_ok: bool) -> CheckState:
    """The honest label for the scam check.

    possible_scam    high risk: strong signs such as gift cards, wire or crypto
    cannot_tell      some signs (medium risk), OR the letter was hard to read, OR
                     the two readings disagree, OR the numbers could not be found
                     in the text: we are not sure and say so
    no_warning_signs nothing found, and the reading looked clean
    """
    if scam_risk == "high":
        return "possible_scam"
    if scam_risk == "med":
        return "cannot_tell"
    unsure = (
        "low" in (first.confidence, second.confidence)
        or first.amount_cents != second.amount_cents
        or first.due_date != second.due_date
        or evidence_ok is not True
    )
    return "cannot_tell" if unsure else "no_warning_signs"


def detect_notices(first: ReaderOutput, second: ReaderOutput, state: CheckState,
                   today: date) -> list[Notice]:
    """Notes to show beside the explanation. Empty for a possible scam.

    A scam letter that says "act now" must not be echoed back to the user as
    "this is time-sensitive", so notices are skipped when it looks like a scam.
    """
    if state == "possible_scam":
        return []
    text = f"{first.raw_text}\n{second.raw_text}"
    notices: list[Notice] = []
    if _LEGAL.search(text):
        notices.append("legal")
    if _MEDICAL.search(text):
        notices.append("medical")

    due = first.due_date if first.due_date == second.due_date else None
    soon = due is not None and due <= today + timedelta(days=TIME_SENSITIVE_DAYS)
    if "legal" in notices or soon or _PRESSURE.search(text):
        notices.append("time_sensitive")
    return notices
