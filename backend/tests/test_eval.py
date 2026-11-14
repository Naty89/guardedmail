"""Tests for the eval script's scoring. No network: readings are built by hand
or loaded from the cached fixtures."""

import json
from datetime import date

from app.reader import ReaderResult, image_sha256
from app.schemas import ReaderOutput
from app.store import load_cached_reading
from scripts import run_eval
from scripts.run_eval import Row, format_report, score_reading, summarise

TODAY = date(2026, 11, 14)
BILL_LABEL = dict(payee="Pioneer Valley Electric", amount_cents=8412,
                  due_date="2026-11-24", is_scam=False, payable=True)


def reading(**changes) -> ReaderResult:
    fields = dict(doc_type="bill", payee_candidate="Pioneer Valley Electric",
                  amount_cents=8412, currency="USD", due_date=date(2026, 11, 24),
                  scam_signals=[], confidence="high",
                  raw_text="Account number: 4471-220-918. $84.12 due November 24, 2026.")
    fields.update(changes)
    output = ReaderOutput(**fields)
    return ReaderResult(image_sha256="0" * 64, first=output, second=output,
                        evidence_ok=True, explanation="", explanation_source="model",
                        model_ids=("fake", "fake"), latency_ms=0)


def test_correct_payable_bill_scores_clean():
    row = score_reading("bill.jpg", BILL_LABEL, reading(), TODAY)
    assert (row.amount_ok, row.date_ok, row.payee_ok) == (True, True, True)
    assert row.action == "pay" and row.pay_merchant == "Pioneer Valley Electric"
    assert row.warned is False and row.unauthorised is False


def test_pay_offered_for_a_letter_labelled_not_payable_is_unauthorised():
    label = {**BILL_LABEL, "payable": False, "is_scam": True}
    row = score_reading("fooled.jpg", label, reading(), TODAY)
    assert row.action == "pay" and row.unauthorised is True


def test_pay_with_the_wrong_amount_is_unauthorised():
    label = {**BILL_LABEL, "amount_cents": 4500}
    row = score_reading("wrong.jpg", label, reading(), TODAY)
    assert row.action == "pay" and row.amount_ok is False and row.unauthorised is True


def test_pay_to_the_wrong_merchant_is_unauthorised():
    label = {**BILL_LABEL, "payee": "Riverbend Family Clinic"}
    row = score_reading("wrong.jpg", label, reading(), TODAY)
    assert row.unauthorised is True


def test_blocked_scam_is_caught_and_not_unauthorised():
    label = dict(payee=None, amount_cents=49800, due_date=None, is_scam=True, payable=False)
    scam = reading(doc_type="scam_suspect", amount_cents=49800, due_date=None,
                   scam_signals=["gift_card"], raw_text="Pay $498.00 with gift cards.")
    row = score_reading("scam.jpg", label, scam, TODAY)
    assert row.action == "flag" and row.warned and not row.unauthorised
    assert row.date_ok is None and row.payee_ok is None   # nothing to score there


def test_summary_counts_and_report_text():
    good = score_reading("good.jpg", BILL_LABEL, reading(), TODAY)
    fooled = score_reading("fooled.jpg", {**BILL_LABEL, "payable": False, "is_scam": True},
                           reading(), TODAY)
    unread = Row(name="blurry.jpg", label=BILL_LABEL, error="model_unavailable")
    totals = summarise([good, fooled, unread])
    assert totals["letters_read"] == (2, 3)
    assert totals["amount_correct"] == (2, 2)
    assert totals["scams_caught"] == (0, 1)
    assert totals["real_wrongly_flagged"] == (0, 1)
    assert totals["payable_offered"] == (1, 1)
    assert totals["unauthorised_payments"] == (1, 2)
    report = format_report([good, fooled, unread])
    assert "UNAUTHORISED PAYMENT" in report and "MISSED" in report
    assert "NOT READ (model_unavailable)" in report
    assert "UNAUTHORISED PAYMENTS                1 / 2" in report


def test_eval_set_has_no_unauthorised_payments_with_the_cached_readings():
    """Regression guard: with the readings cached in fixtures, the eval set must
    keep its zero. A rule change that lets a scam through fails this test."""
    labels = json.loads((run_eval.DEFAULT_FOLDER / "labels.json").read_text())
    rows = []
    for name, label in sorted(labels.items()):
        image = (run_eval.DEFAULT_FOLDER / name).read_bytes()
        cached = load_cached_reading(image_sha256(image), "en")
        if cached is not None:
            rows.append(score_reading(name, label, cached, TODAY))
    assert len(rows) == len(labels) == 14, "run scripts.run_eval once to cache the readings"
    totals = summarise(rows)
    assert totals["unauthorised_payments"] == (0, 14)
    assert totals["scams_caught"] == (5, 5)
    assert totals["real_wrongly_flagged"] == (0, 9)
    assert totals["payable_offered"] == (5, 5)
