"""Put the demo bank back to its starting state before a demo run.

Run:  cd backend && .venv/bin/python -m scripts.reset_demo

Sets every bill on the demo account back to "pending". Our own ledger (the
balance the app shows) lives in the server's memory, so restart the server as
well to return the balance to the seed amount.
"""

import asyncio
import sys

from app.letters import demo_account_id
from app.nessie import NessieError, get_write_client


async def reset() -> int:
    account_id = demo_account_id()
    if not account_id:
        print("NESSIE_ACCOUNT_ID is not set. Run scripts.seed_nessie first.")
        return 2
    client = get_write_client()
    try:
        for bill in await client.list_account_bills(account_id):
            if bill.get("status") != "pending":
                await client.update_bill_status(bill["_id"], "pending")
                print(f"  reset to pending: {bill.get('payee')}")
            else:
                print(f"  already pending:  {bill.get('payee')}")
    except NessieError as exc:
        print(f"Reset failed: {exc}")
        return 1
    finally:
        await client.aclose()
    print("Done. Restart the server to reset the balance shown in the app.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(reset()))
