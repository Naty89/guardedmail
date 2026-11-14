"""Put the demo bank back to its starting state before a demo run.

Run:  cd backend && .venv/bin/python -m scripts.reset_demo

1. Sets every bill on the demo account back to "pending".
2. Moves the local audit log aside (renamed with a timestamp, never deleted),
   because the app rebuilds its ledger from that log on startup.

Restart the server afterwards: the balance returns to the seed amount.
(With MONGODB_URI set, the audit log lives in MongoDB and is not touched here.)
"""

import asyncio
import sys
from datetime import datetime

from app import audit
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
    for name in (audit.AUDIT_FILE, audit.QUARANTINE_FILE):
        path = audit.DATA_DIR / name
        if path.is_file():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            archived = path.with_name(f"{path.stem}.{stamp}{path.suffix}")
            path.rename(archived)
            print(f"  archived {name} -> {archived.name}")
    print("Done. Restart the server to reset the balance shown in the app.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(reset()))
