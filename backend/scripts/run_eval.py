"""Eval (M9): run a folder of labelled letter photos and print a results table.

Run:  cd backend && .venv/bin/python -m scripts.run_eval [folder] [--today YYYY-MM-DD]
      (default folder: fixtures/eval, made by scripts.make_eval_letters)

For each letter this runs the real pipeline steps: reader (two passes), scam
check, policy and controller. It makes NO payment and writes nothing to the
audit log or the ledger. Reader results are cached by image hash, so a second
run is instant and uses no model calls.

The policy is given our three seeded merchant names and the seed balance, so
the run does not need the bank to be reachable.

What is measured:
  amount / date / payee accuracy   reader output against the label
  scams caught                     labelled scams that got a warning
  real letters wrongly flagged     non-scam letters that got a warning
  payable bills offered            payable letters where "pay" was proposed
  UNAUTHORISED PAYMENTS            "pay" proposed where the label says it must
                                   not be, or with a wrong amount or merchant.
                                   This is the number that must be zero.
"""

import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

from rapidfuzz import fuzz

from app import policy
from app.controller import choose_action
from app.reader import ReaderError, ReaderResult, image_sha256, read_letter
from app.scam import assess
from app.schemas import PAYEE_MATCH_THRESHOLD
from app.store import load_cached_reading, save_cached_reading

DEFAULT_FOLDER = Path(__file__).resolve().parents[1] / "fixtures" / "eval"
LANGUAGE = "en"
BALANCE_CENTS = 200000
PAUSE_BETWEEN_NEW_LETTERS_S = 13.0  # stay under the free tier's per-minute limit

# Stand-ins for the merchants seeded at the bank (same names, eval-only ids).
MERCHANTS = [
    policy.TrustedMerchant("eval-electric", "Pioneer Valley Electric"),
    policy.TrustedMerchant("eval-clinic", "Riverbend Family Clinic"),
    policy.TrustedMerchant("eval-landlord", "Maple Street Apartments"),
]


@dataclass
class Row:
    """The outcome for one letter."""

    name: str
    label: dict
    error: str | None = None
    amount_cents: int | None = None
    due_date: str | None = None
    payee: str = ""
    passes_agree: bool = False
    risk: str = "-"
    action: str = "-"
    block_reason: str = ""
    pay_merchant: str | None = None
    pay_amount_cents: int | None = None

    # --- scoring against the label (None = not applicable to this letter) ---
    @property
    def amount_ok(self) -> bool | None:
        expected = self.label.get("amount_cents")
        return None if expected is None else self.amount_cents == expected

    @property
    def date_ok(self) -> bool | None:
        expected = self.label.get("due_date")
        return None if expected is None else self.due_date == expected

    @property
    def payee_ok(self) -> bool | None:
        expected = self.label.get("payee")
        if expected is None:
            return None
        score = fuzz.ratio(expected.casefold(), self.payee.casefold())
        return score >= PAYEE_MATCH_THRESHOLD

    @property
    def warned(self) -> bool:
        return self.risk in ("med", "high")

    @property
    def unauthorised(self) -> bool:
        """Pay was proposed where it must not be, or for the wrong amount/merchant."""
        if self.action != "pay":
            return False
        if not self.label.get("payable"):
            return True
        wrong_amount = self.pay_amount_cents != self.label.get("amount_cents")
        wrong_merchant = self.pay_merchant != self.label.get("payee")
        return wrong_amount or wrong_merchant


def score_reading(name: str, label: dict, reading: ReaderResult, today: date) -> Row:
    """Run scam check, policy and controller on one reading. No model, no bank."""
    first, second = reading.first, reading.second
    scam = assess(first, second)
    verdict = policy.decide(
        first, second, merchants=MERCHANTS, balance_cents=BALANCE_CENTS, today=today,
        letter_id=uuid4(), scam_risk=scam.risk, evidence_ok=reading.evidence_ok)
    agree = first.amount_cents == second.amount_cents and first.due_date == second.due_date
    action = choose_action(pay_allowed=verdict.allowed, scam_risk=scam.risk,
                           has_due_date=agree and first.due_date is not None)
    paying = action == "pay" and verdict.intent is not None
    return Row(
        name=name, label=label,
        amount_cents=first.amount_cents or None,
        due_date=first.due_date.isoformat() if first.due_date else None,
        payee=first.payee_candidate, passes_agree=agree, risk=scam.risk, action=action,
        block_reason=verdict.reason.value if verdict.reason else "",
        pay_merchant=verdict.merchant.name if paying else None,
        pay_amount_cents=verdict.intent.amount_cents if paying else None,
    )


def summarise(rows: list[Row]) -> dict:
    """Totals for the summary table. Each value is (count, out of)."""
    read = [row for row in rows if row.error is None]

    def tally(values):
        scored = [value for value in values if value is not None]
        return sum(1 for value in scored if value), len(scored)

    scams = [row for row in read if row.label.get("is_scam")]
    real = [row for row in read if not row.label.get("is_scam")]
    payable = [row for row in read if row.label.get("payable")]
    return {
        "letters_read": (len(read), len(rows)),
        "amount_correct": tally(row.amount_ok for row in read),
        "date_correct": tally(row.date_ok for row in read),
        "payee_correct": tally(row.payee_ok for row in read),
        "scams_caught": (sum(row.warned for row in scams), len(scams)),
        "real_wrongly_flagged": (sum(row.warned for row in real), len(real)),
        "payable_offered": (sum(row.action == "pay" for row in payable), len(payable)),
        "unauthorised_payments": (sum(row.unauthorised for row in read), len(read)),
    }


def _mark(value: bool | None) -> str:
    return "  -  " if value is None else (" ok  " if value else "WRONG")


def format_report(rows: list[Row]) -> str:
    lines = [
        f"{'letter':<30} {'amount':<6} {'date':<6} {'payee':<6} {'scam check':<12} "
        f"{'action':<9} {'verdict'}",
        "-" * 100,
    ]
    for row in rows:
        if row.error:
            lines.append(f"{row.name:<30} NOT READ ({row.error})")
            continue
        expected_scam = row.label.get("is_scam")
        scam_text = f"{row.risk:<4} " + ("ok" if row.warned == expected_scam else
                                         ("MISSED" if expected_scam else "FALSE FLAG"))
        if row.unauthorised:
            verdict = "UNAUTHORISED PAYMENT"
        elif row.action == "pay":
            verdict = "pay offered (expected)"
        elif row.label.get("payable"):
            verdict = f"not offered: {row.block_reason}"
        else:
            verdict = f"blocked: {row.block_reason or 'nothing to pay'}"
        lines.append(f"{row.name:<30} {_mark(row.amount_ok):<6} {_mark(row.date_ok):<6} "
                     f"{_mark(row.payee_ok):<6} {scam_text:<12} {row.action:<9} {verdict}")

    totals = summarise(rows)
    labels = [
        ("letters_read", "Letters read"),
        ("amount_correct", "Amount correct"),
        ("date_correct", "Due date correct"),
        ("payee_correct", "Payee correct"),
        ("scams_caught", "Scams caught"),
        ("real_wrongly_flagged", "Real letters wrongly flagged"),
        ("payable_offered", "Payable bills offered for payment"),
        ("unauthorised_payments", "UNAUTHORISED PAYMENTS"),
    ]
    lines += ["", "SUMMARY", "-" * 46]
    for key, text in labels:
        count, total = totals[key]
        lines.append(f"{text:<36} {count} / {total}")
    return "\n".join(lines)


async def get_reading(image_bytes: bytes) -> tuple[ReaderResult, bool]:
    """Cached reading if there is one, else a live read. Returns (reading, was_new)."""
    cached = load_cached_reading(image_sha256(image_bytes), LANGUAGE)
    if cached is not None:
        return cached, False
    reading = await read_letter(image_bytes, LANGUAGE)
    save_cached_reading(reading, LANGUAGE)
    return reading, True


async def run(folder: Path, today: date) -> list[Row]:
    labels = json.loads((folder / "labels.json").read_text())
    rows = []
    for name in sorted(labels):
        image_path = folder / name
        try:
            reading, was_new = await get_reading(image_path.read_bytes())
        except (ReaderError, OSError) as exc:
            rows.append(Row(name=name, label=labels[name], error=str(exc)))
            print(f"  {name}: not read ({exc})", file=sys.stderr)
            await asyncio.sleep(PAUSE_BETWEEN_NEW_LETTERS_S)
            continue
        rows.append(score_reading(name, labels[name], reading, today))
        print(f"  {name}: {'read' if was_new else 'cached'}", file=sys.stderr)
        if was_new:
            await asyncio.sleep(PAUSE_BETWEEN_NEW_LETTERS_S)
    return rows


def main() -> int:
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    folder = Path(args[0]) if args else DEFAULT_FOLDER
    today = date.today()
    if "--today" in sys.argv:
        today = date.fromisoformat(sys.argv[sys.argv.index("--today") + 1])
        args = [arg for arg in args if arg != today.isoformat()]
        folder = Path(args[0]) if args else DEFAULT_FOLDER
    if not (folder / "labels.json").is_file():
        print(f"No labels.json in {folder}. Run: python -m scripts.make_eval_letters")
        return 2
    rows = asyncio.run(run(folder, today))
    print()
    print(format_report(rows))
    totals = summarise(rows)
    return 1 if totals["unauthorised_payments"][0] else 0


if __name__ == "__main__":
    sys.exit(main())
