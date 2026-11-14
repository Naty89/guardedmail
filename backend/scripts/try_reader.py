"""Run the reader on one image with the real Gemini API and print the result.

Run:  cd backend && .venv/bin/python -m scripts.try_reader [image] [language]
      (defaults: fixtures/samples/electric_bill.jpg, en)

Needs GEMINI_API_KEY in .env. Use invented letters only.
"""

import asyncio
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

from app.policy import TrustedMerchant, decide
from app.reader import ReaderError, read_letter

DEFAULT_IMAGE = Path(__file__).resolve().parents[1] / "fixtures/samples/electric_bill.jpg"

# Stand-in merchants so this script can show the policy verdict without Nessie.
DEMO_MERCHANTS = [
    TrustedMerchant("demo-electric", "Pioneer Valley Electric"),
    TrustedMerchant("demo-clinic", "Riverbend Family Clinic"),
    TrustedMerchant("demo-landlord", "Maple Street Apartments"),
]


async def run(image_path: Path, language: str) -> int:
    try:
        result = await read_letter(image_path.read_bytes(), language)
    except ReaderError as exc:
        print(f"READER FAILED: {exc}")
        return 1
    print(f"image sha256:   {result.image_sha256}")
    print(f"latency:        {result.latency_ms} ms   models: {result.model_ids}")
    print(f"pass A:         {result.first.without_raw_text()}")
    print(f"pass B:         {result.second.without_raw_text()}")
    print(f"evidence ok:    {result.evidence_ok}")
    print(f"explanation ({result.explanation_source}, {language}):")
    print(f"  {result.explanation}")
    verdict = decide(result.first, result.second, merchants=DEMO_MERCHANTS,
                     balance_cents=200000, today=date.today(), letter_id=uuid4(),
                     evidence_ok=result.evidence_ok)
    reasons = [reason.value for reason in verdict.reasons]
    print(f"policy verdict: {'ALLOW' if verdict.allowed else 'BLOCK'} {reasons}")
    return 0


def main() -> None:
    image = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMAGE
    language = sys.argv[2] if len(sys.argv) > 2 else "en"
    sys.exit(asyncio.run(run(image, language)))


if __name__ == "__main__":
    main()
