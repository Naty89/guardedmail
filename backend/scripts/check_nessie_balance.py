"""Experiment: does POSTing a purchase to Nessie change the account balance?

Run from the backend folder:

    .venv/bin/python -m scripts.check_nessie_balance

It never touches the demo account. Every run creates its own throwaway
customer and checking account (balance 100), makes a 1.00 purchase, and reads
the balance back a few times. It also creates a bill and marks it "completed"
to confirm that PUT works. All money is mock money. The script ends with a
RESULT / CONCLUSION block that tells the team what we learned.
"""

import asyncio
import sys
from datetime import date

from app.nessie import NessieError, get_write_client
from app.nessie_mock import MockNessieRead
from scripts.seed_nessie import require_key_or_offline

TEST_MERCHANT_NAME = "Guarded Balance Check Merchant"
TEST_ADDRESS = {
    "street_number": "1",
    "street_name": "Test Street",
    "city": "Amherst",
    "state": "MA",
    "zip": "01002",
}
TEST_GEOCODE = {"lat": 42.3732, "lng": -72.5199}
START_BALANCE = 100      # dollars
PURCHASE_AMOUNT = 1.00   # dollars
BILL_AMOUNT = 2.00       # dollars (different from the purchase so they can be told apart)
POLL_SECONDS = (2, 5, 10)  # re-read the balance this long after the purchase

LEDGER_REMINDER = (
    "Either way, the app keeps its own ledger (seed balance minus executed "
    "payments) and displays that."
)


def _money(value) -> str:
    """Format a balance for printing (100 -> '100', 99.5 -> '99.5')."""
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


async def run_check(client, poll_seconds=POLL_SECONDS, sleep=asyncio.sleep,
                    out=print) -> dict:
    """Run the experiment with the given write client and return the findings.

    Each step catches NessieError, so one failure still yields a verdict for
    the rest. `poll_seconds` and `sleep` are parameters so tests can run fast.
    """
    is_mock = isinstance(client, MockNessieRead)
    result = {
        "mock": is_mock,
        "purchase_post_works": False,
        "purchase_status": None,             # right after create
        "purchase_status_after_wait": None,  # after the last balance poll
        "balance_before": None,
        "balance_after": None,
        "balance_changed": None,             # True / False / None (unknown)
        "bill_put_works": False,
        "balance_after_bill_completed": None,
        "errors": [],
    }

    async def step(method: str, path: str, call):
        """Run one client call, print it, and return its value (None on error)."""
        try:
            value = await call
        except NessieError as err:
            out(f"  {method:<4} {path}  -> FAILED (status {err.status_code}): {err.message}")
            result["errors"].append(f"{method} {path}: status {err.status_code}: {err.message}")
            return None
        # The client records the real path and HTTP status of its last call.
        meta = getattr(client, "last_response_meta", None) or {}
        if meta.get("method") == method and meta.get("status"):
            out(f"  {method:<4} {meta.get('path', path)}  -> {meta['status']}")
        else:
            out(f"  {method:<4} {path}  -> ok")
        return value

    if is_mock:
        out("*** OFFLINE MOCK: this run uses the in-memory mock, not Nessie. ***")
        out("*** It proves NOTHING about how the real Nessie API behaves.    ***")
    out("Each line is one HTTP call: method, path, status (the API key is never printed).")
    today = date.today().isoformat()

    # --- Setup: our own throwaway customer + account, and a test merchant -----
    out("Setup (throwaway data, the demo account is not touched):")
    account_id = None
    customer = await step("POST", "/customers", client.create_customer(
        "BalanceCheck", "Throwaway", TEST_ADDRESS))
    if customer:
        account = await step(
            "POST", f"/customers/{customer['_id']}/accounts",
            client.create_account(customer["_id"], "Checking",
                                  "Guarded balance check (throwaway)", START_BALANCE))
        account_id = account["_id"] if account else None

    merchant = None
    merchants = await step("GET", "/merchants", client.list_merchants())
    for candidate in merchants or []:
        if isinstance(candidate, dict) and candidate.get("name") == TEST_MERCHANT_NAME:
            merchant = candidate
            break
    if merchant is None:
        merchant = await step("POST", "/merchants", client.create_merchant(
            TEST_MERCHANT_NAME, ["test"], TEST_ADDRESS, TEST_GEOCODE))

    # --- Experiment 1: purchase, then watch the balance ------------------------
    out("Experiment 1: does a purchase change the balance?")
    if account_id and merchant:
        before = await step("GET", f"/accounts/{account_id}", client.get_account(account_id))
        if before:
            result["balance_before"] = before.get("balance")
            out(f"       balance before purchase: {_money(result['balance_before'])}")

        purchase = await step(
            "POST", f"/accounts/{account_id}/purchases",
            client.create_purchase(account_id, merchant["_id"], PURCHASE_AMOUNT, today,
                                   "Guarded balance check", medium="balance"))
        purchase_id = purchase.get("_id") if purchase else None
        result["purchase_post_works"] = bool(purchase_id)

        if purchase_id:
            result["purchase_status"] = await _purchase_status(
                client, account_id, purchase_id, step, fallback=purchase.get("status"))
            out(f"       purchase status after create: {result['purchase_status']}")

            # Read the balance now, then again after each wait (Nessie may
            # process purchases in the background). Stop as soon as it moves.
            waited = 0
            for target in (0, *poll_seconds):
                if target > waited:
                    await sleep(target - waited)
                    waited = target
                after = await step("GET", f"/accounts/{account_id}",
                                   client.get_account(account_id))
                if after is None:
                    continue
                result["balance_after"] = after.get("balance")
                out(f"       balance {waited}s after purchase: {_money(result['balance_after'])}")
                if result["balance_before"] is not None:
                    result["balance_changed"] = (
                        result["balance_after"] != result["balance_before"])
                if result["balance_changed"]:
                    break

            result["purchase_status_after_wait"] = await _purchase_status(
                client, account_id, purchase_id, step, fallback=None)
            out(f"       purchase status at the end: {result['purchase_status_after_wait']}")
    else:
        out("  skipped: setup failed, there is no account or merchant to test with")

    # --- Experiment 2: create a bill and PUT status=completed ------------------
    out("Experiment 2: can a bill be marked completed with PUT?")
    if account_id:
        bill = await step(
            "POST", f"/accounts/{account_id}/bills",
            client.create_bill(account_id, "pending", TEST_MERCHANT_NAME, today,
                               BILL_AMOUNT, nickname="Guarded balance check bill"))
        if bill and bill.get("_id"):
            bill_id = bill["_id"]
            await step("PUT", f"/bills/{bill_id}",
                       client.update_bill_status(bill_id, "completed"))
            read_back = await step("GET", f"/bills/{bill_id}", client.get_bill(bill_id))
            if read_back:
                out(f"       bill status read back: {read_back.get('status')}")
                result["bill_put_works"] = read_back.get("status") == "completed"
            after_bill = await step("GET", f"/accounts/{account_id}",
                                    client.get_account(account_id))
            if after_bill:
                result["balance_after_bill_completed"] = after_bill.get("balance")
                out(f"       balance after bill completed: "
                    f"{_money(result['balance_after_bill_completed'])}")
    else:
        out("  skipped: setup failed, there is no account to test with")

    result["conclusion"] = _conclusion(result)
    for line in verdict_lines(result):
        out(line)
    return result


async def _purchase_status(client, account_id: str, purchase_id: str, step, fallback):
    """Read the purchase back from the account's purchase list; return its status."""
    purchases = await step("GET", f"/accounts/{account_id}/purchases",
                           client.list_account_purchases(account_id))
    for purchase in purchases or []:
        if purchase.get("_id") == purchase_id:
            return purchase.get("status", fallback)
    return fallback


def _conclusion(result: dict) -> str:
    """One sentence telling the team what to do, always with the ledger reminder."""
    if result["balance_changed"] is True:
        finding = ("Purchases DO reduce the balance here, so the Nessie balance can "
                   "be used as a cross-check.")
    elif result["balance_changed"] is False:
        finding = ("Purchases did NOT change the balance here, so never show the "
                   "Nessie balance as the result of a payment.")
    else:
        finding = ("We could not tell whether purchases change the balance, so "
                   "assume they do not.")
    if result["mock"]:
        finding = ("This was the OFFLINE MOCK, so nothing is known about real Nessie "
                   "yet: rerun with a real NESSIE_API_KEY. " + finding)
    return f"{finding} {LEDGER_REMINDER}"


def verdict_lines(result: dict) -> list[str]:
    """Build the final RESULT / CONCLUSION block."""
    before, after = _money(result["balance_before"]), _money(result["balance_after"])
    if result["balance_changed"] is True:
        balance = f"yes ({before} -> {after})"
    elif result["balance_changed"] is False:
        balance = f"no (stayed {before})"
    else:
        reason = result["errors"][0] if result["errors"] else "balance could not be read"
        balance = f"unknown ({reason})"

    lines = ["", "=" * 70]
    if result["mock"]:
        lines.append("MOCK RUN - these results describe the offline mock, NOT real Nessie.")
    lines += [
        f"RESULT: purchase POST path works: {'yes' if result['purchase_post_works'] else 'no'}",
        f"RESULT: purchase status after create: {result['purchase_status'] or 'unknown'}",
        f"RESULT: purchase status after waiting: "
        f"{result['purchase_status_after_wait'] or 'unknown'}",
        f"RESULT: balance changed after purchase: {balance}",
        f"RESULT: bill PUT status=completed works: {'yes' if result['bill_put_works'] else 'no'}",
        f"RESULT: balance after bill marked completed: "
        f"{_money(result['balance_after_bill_completed']) if result['balance_after_bill_completed'] is not None else 'unknown'}",
        f"CONCLUSION: {result['conclusion']}",
        "=" * 70,
    ]
    return lines


async def _run() -> dict:
    client = get_write_client()
    try:
        return await run_check(client)
    finally:
        close = getattr(client, "aclose", None)
        if close is not None:
            await close()


def main() -> int:
    require_key_or_offline()
    result = asyncio.run(_run())
    # Exit 1 if a step failed, so a broken run is obvious in scripts too.
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
