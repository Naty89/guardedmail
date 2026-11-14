"""In-memory stand-in for the Nessie clients, used when DEMO_OFFLINE is on.

Same async method names, parameters and return shapes as ``app.nessie``, but it
never touches the network: everything lives in one shared ``MockStore``.

Choices made here (the real API's behaviour is UNVERIFIED for all three):
- A purchase reduces the account balance straight away and has status "executed".
- A purchase larger than the balance is REFUSED with ``NessieError(400, ...)``
  and nothing changes. Real Nessie may well accept it, so callers must check
  the balance themselves and not rely on this.
- ``update_bill_status`` returns ``{"code": 202, "message": ...}``, not the bill.

All money is mock money and all data is invented.
"""

import copy
from datetime import date, timedelta

from app.nessie import (BILL_STATUSES, PURCHASE_MEDIUMS, NessieError, check_amount,
                        check_balance, check_choice, check_date, check_id, check_text)

# Deterministic 24-character ids: first digit = kind, the rest = a counter.
_KIND_DIGIT = {"customer": "1", "account": "2", "merchant": "3", "bill": "4", "purchase": "5"}

MOCK_CUSTOMER_ID = "100000000000000000000001"
MOCK_ACCOUNT_ID = "200000000000000000000001"

SEED_CUSTOMER = {
    "first_name": "Demo",
    "last_name": "User",
    "address": {"street_number": "12", "street_name": "Example Lane",
                "city": "Springfield", "state": "MA", "zip": "01101"},
}
SEED_ACCOUNT = {"type": "Checking", "nickname": "Guarded Demo Checking",
                "balance": 2000, "rewards": 0}
# (merchant name, category, bill amount in dollars)
SEED_MERCHANTS = [
    ("Pioneer Valley Electric", ["utilities"], 84.12),
    ("Riverbend Family Clinic", ["health"], 45.00),
    ("Maple Street Apartments", ["rent"], 450.00),
]
SEED_BILL_DUE_IN_DAYS = 14


class MockStore:
    """All mock bank data, shared by every mock client.

    The data lives on the class itself, so there is exactly one store and
    ``MockStore.reset()`` (or ``STORE.reset()``) puts the seed data back.
    """

    customers: dict[str, dict] = {}
    accounts: dict[str, dict] = {}
    merchants: dict[str, dict] = {}
    bills: dict[str, dict] = {}
    purchases: dict[str, dict] = {}
    _counters: dict[str, int] = {}

    @classmethod
    def reset(cls) -> None:
        cls.customers = {}
        cls.accounts = {}
        cls.merchants = {}
        cls.bills = {}
        cls.purchases = {}
        cls._counters = {kind: 0 for kind in _KIND_DIGIT}
        cls._seed()

    @classmethod
    def new_id(cls, kind: str) -> str:
        cls._counters[kind] += 1
        return f"{_KIND_DIGIT[kind]}{cls._counters[kind]:023x}"

    @classmethod
    def _seed(cls) -> None:
        customer_id = cls.new_id("customer")
        cls.customers[customer_id] = {"_id": customer_id, **copy.deepcopy(SEED_CUSTOMER)}
        account_id = cls.new_id("account")
        cls.accounts[account_id] = {"_id": account_id, **SEED_ACCOUNT,
                                    "customer_id": customer_id}
        today = date.today()
        due = (today + timedelta(days=SEED_BILL_DUE_IN_DAYS)).isoformat()
        for number, (name, category, amount) in enumerate(SEED_MERCHANTS, start=1):
            merchant_id = cls.new_id("merchant")
            cls.merchants[merchant_id] = {
                "_id": merchant_id,
                "name": name,
                "category": list(category),
                "address": {"street_number": str(100 * number), "street_name": "Sample Road",
                            "city": "Springfield", "state": "MA", "zip": "01101"},
                "geocode": {"lat": 42.1, "lng": -72.59},
            }
            bill_id = cls.new_id("bill")
            cls.bills[bill_id] = {
                "_id": bill_id,
                "status": "pending",
                "payee": name,
                "nickname": f"{name} bill",
                "creation_date": today.isoformat(),
                "payment_date": due,
                "recurring_date": 1,
                "payment_amount": amount,
                "account_id": account_id,
            }


STORE = MockStore  # alias: the one shared store
MockStore.reset()


def _find(table: dict[str, dict], name: str, value: str) -> dict:
    """Return the stored record or raise the same kind of 404 Nessie would."""
    check_id(name, value)
    if value not in table:
        raise NessieError(404, f"{name} not found")
    return table[value]


class MockNessieRead:
    """Offline version of NessieReadClient."""

    def __init__(self):
        self.store = MockStore  # the single shared store
        self.last_response_meta: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        return None

    def _done(self, method: str, path: str, status: int, result):
        """Record the same audit details as the real client and copy the result
        so callers cannot change the store by editing what they got back."""
        self.last_response_meta = {"method": method, "path": path, "status": status,
                                   "elapsed_ms": 0, "attempts": 1, "request_id": None}
        return copy.deepcopy(result)

    async def get_customer(self, customer_id: str) -> dict:
        customer = _find(self.store.customers, "customer_id", customer_id)
        return self._done("GET", f"/customers/{customer_id}", 200, customer)

    async def list_customers(self) -> list[dict]:
        return self._done("GET", "/customers", 200, list(self.store.customers.values()))

    async def list_customer_accounts(self, customer_id: str) -> list[dict]:
        _find(self.store.customers, "customer_id", customer_id)
        accounts = [a for a in self.store.accounts.values() if a["customer_id"] == customer_id]
        return self._done("GET", f"/customers/{customer_id}/accounts", 200, accounts)

    async def get_account(self, account_id: str) -> dict:
        account = _find(self.store.accounts, "account_id", account_id)
        return self._done("GET", f"/accounts/{account_id}", 200, account)

    async def list_merchants(self) -> list[dict]:
        return self._done("GET", "/merchants", 200, list(self.store.merchants.values()))

    async def get_merchant(self, merchant_id: str) -> dict:
        merchant = _find(self.store.merchants, "merchant_id", merchant_id)
        return self._done("GET", f"/merchants/{merchant_id}", 200, merchant)

    async def list_account_bills(self, account_id: str) -> list[dict]:
        _find(self.store.accounts, "account_id", account_id)
        bills = [b for b in self.store.bills.values() if b["account_id"] == account_id]
        return self._done("GET", f"/accounts/{account_id}/bills", 200, bills)

    async def get_bill(self, bill_id: str) -> dict:
        bill = _find(self.store.bills, "bill_id", bill_id)
        return self._done("GET", f"/bills/{bill_id}", 200, bill)

    async def list_account_purchases(self, account_id: str) -> list[dict]:
        _find(self.store.accounts, "account_id", account_id)
        purchases = [p for p in self.store.purchases.values() if p["payer_id"] == account_id]
        return self._done("GET", f"/accounts/{account_id}/purchases", 200, purchases)


class MockNessieWrite(MockNessieRead):
    """Offline version of NessieWriteClient."""

    async def create_customer(self, first_name: str, last_name: str, address: dict) -> dict:
        customer = {
            "_id": self.store.new_id("customer"),
            "first_name": check_text("first_name", first_name),
            "last_name": check_text("last_name", last_name),
            "address": copy.deepcopy(address),
        }
        self.store.customers[customer["_id"]] = customer
        return self._done("POST", "/customers", 201, customer)

    async def create_account(self, customer_id: str, account_type: str, nickname: str,
                             balance: int, rewards: int = 0) -> dict:
        _find(self.store.customers, "customer_id", customer_id)
        account = {
            "_id": self.store.new_id("account"),
            "type": check_text("account_type", account_type),
            "nickname": check_text("nickname", nickname),
            "rewards": check_balance("rewards", rewards),
            "balance": check_balance("balance", balance),
            "customer_id": customer_id,
        }
        self.store.accounts[account["_id"]] = account
        return self._done("POST", f"/customers/{customer_id}/accounts", 201, account)

    async def create_merchant(self, name: str, category: list[str], address: dict,
                              geocode: dict) -> dict:
        merchant = {
            "_id": self.store.new_id("merchant"),
            "name": check_text("name", name),
            "category": list(category),
            "address": copy.deepcopy(address),
            "geocode": copy.deepcopy(geocode),
        }
        self.store.merchants[merchant["_id"]] = merchant
        return self._done("POST", "/merchants", 201, merchant)

    async def create_bill(self, account_id: str, status: str, payee: str,
                          payment_date: str, payment_amount: float,
                          nickname: str = "", recurring_date: int = 1) -> dict:
        _find(self.store.accounts, "account_id", account_id)
        bill = {
            "_id": self.store.new_id("bill"),
            "status": check_choice("status", status, BILL_STATUSES),
            "payee": check_text("payee", payee),
            "nickname": nickname,
            "creation_date": date.today().isoformat(),
            "payment_date": check_date("payment_date", payment_date),
            "recurring_date": recurring_date,
            "payment_amount": check_amount("payment_amount", payment_amount),
            "account_id": account_id,
        }
        self.store.bills[bill["_id"]] = bill
        return self._done("POST", f"/accounts/{account_id}/bills", 201, bill)

    async def create_purchase(self, account_id: str, merchant_id: str, amount: float,
                              purchase_date: str, description: str,
                              medium: str = "balance") -> dict:
        account = _find(self.store.accounts, "account_id", account_id)
        _find(self.store.merchants, "merchant_id", merchant_id)
        check_choice("medium", medium, PURCHASE_MEDIUMS)
        check_date("purchase_date", purchase_date)
        check_amount("amount", amount)
        pot = "balance" if medium == "balance" else "rewards"
        if amount > account[pot]:
            # Mock-only rule, see the module docstring.
            raise NessieError(400, f"insufficient {pot} for this purchase (mock rule)")
        account[pot] = round(account[pot] - amount, 2)
        purchase = {
            "_id": self.store.new_id("purchase"),
            "type": "merchant",
            "merchant_id": merchant_id,
            "payer_id": account_id,
            "purchase_date": purchase_date,
            "amount": amount,
            "status": "executed",
            "medium": medium,
            "description": description,
        }
        self.store.purchases[purchase["_id"]] = purchase
        return self._done("POST", f"/accounts/{account_id}/purchases", 201, purchase)

    async def update_bill_status(self, bill_id: str, status: str) -> dict:
        bill = _find(self.store.bills, "bill_id", bill_id)
        bill["status"] = check_choice("status", status, BILL_STATUSES)
        return self._done("PUT", f"/bills/{bill_id}", 202,
                          {"code": 202, "message": "Accepted bill modification"})
