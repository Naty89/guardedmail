"""Seed the Nessie mock bank with the demo customer, account, merchants and bills.

Run from the backend folder:

    .venv/bin/python -m scripts.seed_nessie

It is safe to run again and again: anything that already exists is reused, so
the second run creates nothing. The ids are saved to the repo-root .env file.
All money here is mock money and all names are invented test data.
"""

import argparse
import asyncio
import os
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from dotenv import dotenv_values

from app.config import ENV_PATH, get_settings
from app.nessie import NessieError, get_write_client

# --- Seed data (must match the contract and the offline mock exactly) ---------

CUSTOMER_FIRST_NAME = "Demo"
CUSTOMER_LAST_NAME = "User"
CUSTOMER_ADDRESS = {
    "street_number": "12",
    "street_name": "Juniper Lane",
    "city": "Amherst",
    "state": "MA",
    "zip": "01002",
}

ACCOUNT_TYPE = "Checking"
ACCOUNT_NICKNAME = "Guarded Demo Checking"
ACCOUNT_BALANCE = 2000  # dollars (Nessie uses dollars)
SEED_BALANCE_CENTS = ACCOUNT_BALANCE * 100  # our own code uses integer cents

# Order matters: NESSIE_MERCHANT_IDS is saved as utility, clinic, landlord.
MERCHANTS = [
    {
        "name": "Pioneer Valley Electric",
        "category": ["utilities"],
        "address": {"street_number": "400", "street_name": "Mill River Road",
                    "city": "Northampton", "state": "MA", "zip": "01060"},
        "geocode": {"lat": 42.3251, "lng": -72.6412},
        "bill_amount": 84.12,
        "due_in_days": 10,
    },
    {
        "name": "Riverbend Family Clinic",
        "category": ["health"],
        "address": {"street_number": "27", "street_name": "Riverbend Way",
                    "city": "Hadley", "state": "MA", "zip": "01035"},
        "geocode": {"lat": 42.3418, "lng": -72.5884},
        "bill_amount": 45.00,
        "due_in_days": 14,
    },
    {
        "name": "Maple Street Apartments",
        "category": ["rent"],
        "address": {"street_number": "88", "street_name": "Maple Street",
                    "city": "Amherst", "state": "MA", "zip": "01002"},
        "geocode": {"lat": 42.3732, "lng": -72.5199},
        "bill_amount": 450.00,
        "due_in_days": 21,
    },
]

MISSING_KEY_MESSAGE = """\
NESSIE_API_KEY is not set, so this script cannot talk to the Nessie mock bank.

How to fix it:
  1. Open https://api.nessieisreal.com and sign in with GitHub.
  2. Copy the API key from your profile page.
  3. Put it in the .env file at the repo root:  NESSIE_API_KEY=<your key>
     ({env_path})

Or, to try the script without a key against the built-in offline mock, run it
with DEMO_OFFLINE=1 (that proves nothing about the real Nessie API).
"""


# --- .env helper --------------------------------------------------------------

def upsert_env(path, values: dict[str, str]) -> None:
    """Set KEY=value lines in a .env file without disturbing anything else.

    Existing keys are updated in place, missing keys are appended, and every
    other line (comments, blank lines, other keys) is kept exactly as it was.
    The file is created if missing. The write is atomic (temp file + replace).
    """
    path = Path(path)
    lines = path.read_text().splitlines(keepends=True) if path.exists() else []

    remaining = dict(values)  # keys we have not written yet
    new_lines = []
    for line in lines:
        key = _env_line_key(line)
        if key in values:
            ending = "\n" if line.endswith("\n") else ""
            new_lines.append(f"{key}={values[key]}{ending}")
            remaining.pop(key, None)
        else:
            new_lines.append(line)

    if remaining:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        for key, value in remaining.items():
            new_lines.append(f"{key}={value}\n")

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as tmp:
            tmp.write("".join(new_lines))
        if path.exists():
            os.chmod(tmp_name, path.stat().st_mode & 0o777)  # keep permissions
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _env_line_key(line: str) -> str | None:
    """Return the key of a `KEY=value` line, or None for comments/other lines."""
    match = _ENV_LINE.match(line)
    return match.group(1) if match else None


def read_saved_ids(env_path) -> dict:
    """Read ids saved by an earlier run from the .env file (empty if none)."""
    env_path = Path(env_path)
    saved = dotenv_values(env_path) if env_path.exists() else {}
    merchant_ids = [m.strip() for m in (saved.get("NESSIE_MERCHANT_IDS") or "").split(",")]
    return {
        "customer_id": (saved.get("NESSIE_CUSTOMER_ID") or "").strip(),
        "account_id": (saved.get("NESSIE_ACCOUNT_ID") or "").strip(),
        "merchant_ids": [m for m in merchant_ids if m],
    }


# --- Seeding ------------------------------------------------------------------

async def _get_or_none(getter, object_id: str) -> dict | None:
    """Fetch an object by id; None if the id is empty or Nessie says it is gone."""
    if not object_id or not object_id.isalnum():  # empty or garbage in .env
        return None
    try:
        return await getter(object_id)
    except NessieError as err:
        if err.status_code in (400, 404):  # bad or unknown id -> treat as missing
            return None
        raise


async def _find_or_create_customer(client, saved_id: str, result: dict) -> dict:
    customer = await _get_or_none(client.get_customer, saved_id)
    if customer is None:
        # No usable saved id: look for a demo customer made by an earlier run.
        for candidate in await client.list_customers():
            if (candidate.get("first_name") == CUSTOMER_FIRST_NAME
                    and candidate.get("last_name") == CUSTOMER_LAST_NAME):
                customer = candidate
                break
    if customer is not None:
        result["reused"].append(f"customer {customer['_id']}")
        return customer
    customer = await client.create_customer(
        CUSTOMER_FIRST_NAME, CUSTOMER_LAST_NAME, CUSTOMER_ADDRESS)
    result["created"].append(f"customer {customer['_id']}")
    return customer


async def _find_or_create_account(client, customer_id: str, saved_id: str,
                                  result: dict) -> dict:
    account = await _get_or_none(client.get_account, saved_id)
    if account is not None and account.get("customer_id") not in (None, customer_id):
        account = None  # saved account belongs to a different customer
    if account is None:
        for candidate in await client.list_customer_accounts(customer_id):
            if candidate.get("nickname") == ACCOUNT_NICKNAME:
                account = candidate
                break
    if account is not None:
        result["reused"].append(f"account {account['_id']}")
        return account
    account = await client.create_account(
        customer_id, ACCOUNT_TYPE, ACCOUNT_NICKNAME, ACCOUNT_BALANCE, rewards=0)
    result["created"].append(f"account {account['_id']}")
    return account


async def _find_or_create_merchants(client, saved_ids: list[str], result: dict) -> list[dict]:
    """Return the three merchants in seed order, reusing by saved id then name."""
    found: dict[str, dict] = {}

    # 1. Prefer merchants whose id we saved earlier (cheap: one GET each).
    for saved_id in saved_ids:
        merchant = await _get_or_none(client.get_merchant, saved_id)
        if merchant is not None:
            found.setdefault(merchant.get("name"), merchant)

    # 2. Otherwise look for an exact name match in the shared, global merchant
    #    list. That list can be huge and full of other teams' junk, so we fetch
    #    it once, only if needed, and pick the lowest id so the choice is stable.
    wanted = [m["name"] for m in MERCHANTS if m["name"] not in found]
    if wanted:
        by_name: dict[str, dict] = {}
        for merchant in await client.list_merchants():
            name = merchant.get("name") if isinstance(merchant, dict) else None
            if name in wanted and merchant.get("_id"):
                best = by_name.get(name)
                if best is None or str(merchant["_id"]) < str(best["_id"]):
                    by_name[name] = merchant
        found.update(by_name)

    merchants = []
    for spec in MERCHANTS:
        merchant = found.get(spec["name"])
        if merchant is not None:
            result["reused"].append(f"merchant {spec['name']} {merchant['_id']}")
        else:
            merchant = await client.create_merchant(
                spec["name"], spec["category"], spec["address"], spec["geocode"])
            result["created"].append(f"merchant {spec['name']} {merchant['_id']}")
        merchants.append(merchant)
    return merchants


async def _find_or_create_bills(client, account_id: str, result: dict) -> list[dict]:
    """Return one bill per merchant (payee = merchant name), reusing by payee."""
    existing = await client.list_account_bills(account_id)
    bills = []
    for spec in MERCHANTS:
        matches = [b for b in existing if b.get("payee") == spec["name"]]
        pending = [b for b in matches if b.get("status") == "pending"]
        if matches:
            bill = (pending or matches)[0]
            result["reused"].append(f"bill {spec['name']} {bill['_id']}")
            if bill.get("status") != "pending":
                result["warnings"].append(
                    f"bill for {spec['name']} already has status "
                    f"{bill.get('status')!r} (not pending)")
        else:
            due = date.today() + timedelta(days=spec["due_in_days"])
            bill = await client.create_bill(
                account_id, "pending", spec["name"], due.isoformat(),
                spec["bill_amount"], nickname=f"{spec['name']} bill")
            result["created"].append(f"bill {spec['name']} {bill['_id']}")
        bills.append(bill)
    return bills


async def seed(client, env_path) -> dict:
    """Create (or reuse) the demo data and save the ids to the .env file.

    Returns the ids plus lists describing what was created and what was reused.
    """
    saved = read_saved_ids(env_path)
    result = {"created": [], "reused": [], "warnings": []}

    customer = await _find_or_create_customer(client, saved["customer_id"], result)
    account = await _find_or_create_account(
        client, customer["_id"], saved["account_id"], result)
    merchants = await _find_or_create_merchants(client, saved["merchant_ids"], result)
    bills = await _find_or_create_bills(client, account["_id"], result)

    if account.get("balance") != ACCOUNT_BALANCE:
        result["warnings"].append(
            f"account balance at Nessie is {account.get('balance')}, not "
            f"{ACCOUNT_BALANCE}; the app shows its own ledger starting from "
            f"SEED_BALANCE_CENTS={SEED_BALANCE_CENTS}")

    result.update({
        "customer_id": customer["_id"],
        "account_id": account["_id"],
        "merchant_ids": [m["_id"] for m in merchants],
        "bill_ids": [b["_id"] for b in bills],
        "account_balance": account.get("balance"),
        "env_path": str(env_path),
    })
    upsert_env(env_path, {
        "NESSIE_CUSTOMER_ID": result["customer_id"],
        "NESSIE_ACCOUNT_ID": result["account_id"],
        "NESSIE_MERCHANT_IDS": ",".join(result["merchant_ids"]),
        "SEED_BALANCE_CENTS": str(SEED_BALANCE_CENTS),
    })
    return result


# --- Command line -------------------------------------------------------------

def require_key_or_offline() -> bool:
    """Return True if offline (mock) mode is on; exit with help if no key is set."""
    settings = get_settings()
    if settings.demo_offline:
        return True
    if not settings.nessie_api_key:
        print(MISSING_KEY_MESSAGE.format(env_path=ENV_PATH), file=sys.stderr)
        raise SystemExit(2)
    return False


def print_summary(result: dict, offline: bool) -> None:
    print("Nessie seed summary" + (" (OFFLINE MOCK - nothing was sent to Nessie)" if offline else ""))
    print(f"  customer id:  {result['customer_id']}")
    print(f"  account id:   {result['account_id']}  (balance at Nessie: {result['account_balance']})")
    for spec, merchant_id, bill_id in zip(MERCHANTS, result["merchant_ids"], result["bill_ids"]):
        print(f"  merchant:     {spec['name']}  id={merchant_id}  "
              f"bill={bill_id} (${spec['bill_amount']:.2f})")
    print(f"  created ({len(result['created'])}):")
    for item in result["created"] or ["nothing - everything already existed"]:
        print(f"    + {item}")
    print(f"  reused ({len(result['reused'])}):")
    for item in result["reused"] or ["nothing"]:
        print(f"    = {item}")
    for warning in result["warnings"]:
        print(f"  WARNING: {warning}")
    print(f"  saved NESSIE_CUSTOMER_ID, NESSIE_ACCOUNT_ID, NESSIE_MERCHANT_IDS and "
          f"SEED_BALANCE_CENTS to {result['env_path']}")


async def _run(env_path: Path) -> dict:
    client = get_write_client()
    try:
        return await seed(client, env_path)
    finally:
        close = getattr(client, "aclose", None)
        if close is not None:
            await close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Nessie with the Guarded demo data.")
    parser.add_argument("--env-path", type=Path, default=ENV_PATH,
                        help="where to read/save the ids (default: repo-root .env)")
    args = parser.parse_args(argv)

    offline = require_key_or_offline()
    try:
        result = asyncio.run(_run(args.env_path))
    except NessieError as err:
        print(f"Seeding failed: Nessie error (status {err.status_code}): {err.message}",
              file=sys.stderr)
        return 1
    print_summary(result, offline)
    return 0


if __name__ == "__main__":
    sys.exit(main())
