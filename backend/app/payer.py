"""Payer: the only application module that may move (mock) money.

- This is the ONLY app module that imports the Nessie WRITE client.
- It accepts a `PaymentIntent` plus a confirmation token, nothing else. There is
  no parameter here that could carry text from a letter or a value from the
  browser: the amount and merchant come from the intent the SERVER stored.
- The token is checked (valid, not expired, not used) before any bank call.
"""

from dataclasses import dataclass
from datetime import datetime

from app import policy
from app.nessie import NessieError, get_write_client
from app.schemas import PaymentIntent, ReasonId

# Sent to the bank as the purchase description. A fixed phrase plus our own
# proposal id, which makes it the idempotency key for this proposal.
DESCRIPTION_PREFIX = "Guarded Mail bill payment "

USED_TOKENS = policy.UsedTokens()


@dataclass(frozen=True)
class PayResult:
    """Outcome of one payment attempt."""

    paid: bool
    reason: ReasonId | None = None      # why not, when paid is False
    nessie_id: str | None = None        # purchase id at the bank
    bill_marked: bool = False           # the matching bill was set to "completed"
    steps: tuple[dict, ...] = ()        # bank calls made, for the audit log


def _description(intent: PaymentIntent) -> str:
    return f"{DESCRIPTION_PREFIX}{intent.proposal_id}"


async def _find_existing_purchase(client, account_id: str, intent: PaymentIntent) -> str | None:
    """Look for a purchase this proposal already made (after an unclear failure)."""
    try:
        purchases = await client.list_account_purchases(account_id)
    except NessieError:
        return None
    for purchase in purchases:
        if purchase.get("description") == _description(intent):
            return purchase.get("_id")
    return None


async def _mark_bill_completed(client, account_id: str, intent: PaymentIntent,
                               steps: list[dict]) -> bool:
    """Set the merchant's pending bill to "completed". Best effort: never fails a payment."""
    try:
        merchant = await client.get_merchant(intent.merchant_id)
        bills = await client.list_account_bills(account_id)
        for bill in bills:
            if bill.get("payee") == merchant.get("name") and bill.get("status") == "pending":
                await client.update_bill_status(bill["_id"], "completed")
                steps.append(_step(client, "bill_completed"))
                return True
    except NessieError as exc:
        steps.append({"step": "bill_completed", "error": exc.message})
    return False


def _step(client, name: str) -> dict:
    meta = getattr(client, "last_response_meta", None) or {}
    return {"step": name, **{k: meta.get(k) for k in
                             ("method", "path", "status", "elapsed_ms", "request_id")}}


async def pay(
    intent: PaymentIntent,
    token: str,
    *,
    expires_at: int,
    now: datetime,
    secret: str,
    account_id: str,
    balance_cents: int,
    used: policy.UsedTokens | None = None,
) -> PayResult:
    """Execute one confirmed payment.

    intent, expires_at  the copies the server stored when it made the proposal
    token               what the user sent back
    balance_cents       from our own ledger, checked again right before paying
    """
    used = used if used is not None else USED_TOKENS

    # 1. Token first. A valid token is marked used here, so a second call with
    #    the same token stops at this line (single use / idempotent).
    problem = policy.verify_token(token, intent, expires_at, now=now, secret=secret, used=used)
    if problem is not None:
        return PayResult(paid=False, reason=problem)

    # 2. The balance may have changed since the proposal was made.
    if intent.amount_cents > balance_cents:
        return PayResult(paid=False, reason=ReasonId.AMOUNT_OVER_BALANCE)

    steps: list[dict] = []
    client = get_write_client()
    try:
        try:
            purchase = await client.create_purchase(
                account_id, intent.merchant_id, intent.amount_cents / 100,
                now.date().isoformat(), _description(intent))
            nessie_id = purchase.get("_id")
            steps.append(_step(client, "purchase_created"))
        except NessieError as exc:
            steps.append({"step": "purchase_created", "error": exc.message,
                          "status": exc.status_code})
            # The client never re-sends a purchase after a timeout, so the bank
            # may or may not have it. Look before reporting a failure.
            nessie_id = await _find_existing_purchase(client, account_id, intent)
        if not nessie_id:
            return PayResult(paid=False, reason=ReasonId.PAYMENT_FAILED, steps=tuple(steps))

        bill_marked = await _mark_bill_completed(client, account_id, intent, steps)
        return PayResult(paid=True, nessie_id=str(nessie_id), bill_marked=bill_marked,
                         steps=tuple(steps))
    finally:
        await client.aclose()
