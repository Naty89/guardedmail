"""Tests for guidance.py (honest wording and notes) and the low-confidence rule."""

from datetime import date, timedelta

import pytest

from app import guidance, policy
from app.schemas import ReaderOutput, ReasonId

TODAY = date(2026, 11, 14)
DUE = date(2026, 12, 20)   # far enough away to not count as "soon"


def reading(**changes) -> ReaderOutput:
    fields = dict(doc_type="bill", payee_candidate="Pioneer Valley Electric", amount_cents=8412,
                  currency="USD", due_date=DUE, scam_signals=[], confidence="high",
                  raw_text="Pioneer Valley Electric. Account number 4471-220-918. Total $84.12.")
    fields.update(changes)
    return ReaderOutput(**fields)


def state(first=None, second=None, risk="low", evidence=True):
    first = first or reading()
    return guidance.check_state(scam_risk=risk, first=first, second=second or first,
                                evidence_ok=evidence)


# ----------------------------------------------------------------- check state


def test_a_clean_clear_letter_has_no_warning_signs_never_safe():
    assert state() == "no_warning_signs"


def test_high_risk_is_a_possible_scam():
    assert state(risk="high") == "possible_scam"


def test_medium_risk_is_honestly_uncertain_not_a_scam_verdict():
    assert state(risk="med") == "cannot_tell"


@pytest.mark.parametrize("first,second,evidence", [
    (reading(confidence="low"), None, True),                       # hard to read
    (reading(), reading(confidence="low"), True),
    (reading(), reading(amount_cents=8421), True),                 # readings disagree
    (reading(), reading(due_date=DUE + timedelta(days=1)), True),
    (reading(), None, False),                                      # numbers not in the text
])
def test_low_risk_but_unsure_is_cannot_tell(first, second, evidence):
    assert state(first, second, evidence=evidence) == "cannot_tell"


def test_a_clean_score_alone_never_becomes_reassurance_when_something_is_off():
    assert state(reading(confidence="low"), risk="low") != "no_warning_signs"


# --------------------------------------------------------------------- notices


def notices(text="", today=TODAY, due=DUE, st="no_warning_signs"):
    r = reading(raw_text=text or "Plain letter.", due_date=due)
    return guidance.detect_notices(r, r, st, today)


def test_ordinary_bill_far_from_due_has_no_notices():
    assert notices("Electricity bill. Total $84.12.") == []


@pytest.mark.parametrize("text", [
    "NOTICE TO QUIT. You must vacate or face eviction.",
    "You are named in a lawsuit. A summons has been issued by the court.",
    "Your account was sent to a collection agency.",
    "Foreclosure proceedings have begun.",
])
def test_legal_letters_are_flagged_legal_and_time_sensitive(text):
    assert notices(text) == ["legal", "time_sensitive"]


@pytest.mark.parametrize("text", [
    "Your lab results are ready. Copay due $40.",
    "Explanation of benefits: this is not a bill.",
    "Prescription refill notice from the clinic.",
])
def test_health_letters_get_the_medical_note(text):
    assert "medical" in notices(text)


def test_due_within_a_week_is_time_sensitive_and_so_is_overdue():
    assert notices(due=TODAY + timedelta(days=7)) == ["time_sensitive"]
    assert notices(due=TODAY + timedelta(days=8)) == []
    assert notices(due=TODAY - timedelta(days=5)) == ["time_sensitive"]


def test_pressure_wording_counts_as_time_sensitive():
    assert "time_sensitive" in notices("FINAL NOTICE: your account is past due.")


def test_possible_scams_get_no_notices_so_urgency_is_not_echoed_back():
    assert notices("FINAL NOTICE: pay now or face a lawsuit and eviction.", st="possible_scam") == []


def test_disagreeing_due_dates_do_not_count_as_a_due_date():
    first, second = reading(due_date=TODAY + timedelta(days=2)), reading(due_date=DUE)
    assert guidance.detect_notices(first, second, "cannot_tell", TODAY) == []


# ------------------------------------------------- low-confidence policy rule


def decide(first, second=None):
    merchants = [policy.TrustedMerchant("m1", "Pioneer Valley Electric")]
    from uuid import uuid4
    return policy.decide(first, second or first, merchants=merchants, balance_cents=200000,
                         today=TODAY, letter_id=uuid4(), scam_risk="low", evidence_ok=True)


def test_clear_reading_is_still_allowed():
    assert decide(reading()).allowed


@pytest.mark.parametrize("first,second", [
    (reading(confidence="low"), None),
    (reading(), reading(confidence="low")),
])
def test_a_low_confidence_reading_is_never_offered_for_payment(first, second):
    verdict = decide(first, second)
    assert not verdict.allowed and verdict.reasons == (ReasonId.LOW_CONFIDENCE,)


def test_medium_confidence_is_fine():
    assert decide(reading(confidence="med")).allowed
