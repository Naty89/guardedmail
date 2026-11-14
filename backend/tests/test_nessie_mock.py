"""Tests for the in-memory Nessie mock, including parity with the real client."""

import asyncio
import inspect
import re
from datetime import date, timedelta

import pytest

from app.nessie import NessieError, NessieReadClient, NessieWriteClient
from app.nessie_mock import (MOCK_ACCOUNT_ID, MOCK_CUSTOMER_ID, STORE, MockNessieRead,
                             MockNessieWrite, MockStore)

run = asyncio.run
ID_RE = re.compile(r"^[0-9a-f]{24}$")


@pytest.fixture(autouse=True)
def fresh_store():
    MockStore.reset()
    yield
    MockStore.reset()


def test_seed_customer_and_account_match_contract():
    mock = MockNessieRead()
    customers = run(mock.list_customers())
    assert len(customers) == 1
    assert customers[0]["_id"] == MOCK_CUSTOMER_ID
    assert (customers[0]["first_name"], customers[0]["last_name"]) == ("Demo", "User")
    assert set(customers[0]["address"]) == {"street_number", "street_name", "city",
                                            "state", "zip"}
    accounts = run(mock.list_customer_accounts(MOCK_CUSTOMER_ID))
    assert len(accounts) == 1
    account = accounts[0]
    assert account["_id"] == MOCK_ACCOUNT_ID
    assert account["type"] == "Checking"
    assert account["nickname"] == "Guarded Demo Checking"
    assert account["balance"] == 2000
    assert account["rewards"] == 0
    assert account["customer_id"] == MOCK_CUSTOMER_ID
    assert run(mock.get_account(MOCK_ACCOUNT_ID)) == account
    assert run(mock.get_customer(MOCK_CUSTOMER_ID)) == customers[0]


def test_seed_merchants_and_bills_match_contract():
    mock = MockNessieRead()
    merchants = run(mock.list_merchants())
    assert [(m["name"], m["category"]) for m in merchants] == [
        ("Pioneer Valley Electric", ["utilities"]),
        ("Riverbend Family Clinic", ["health"]),
        ("Maple Street Apartments", ["rent"]),
    ]
    bills = run(mock.list_account_bills(MOCK_ACCOUNT_ID))
    assert [(b["payee"], b["payment_amount"], b["status"]) for b in bills] == [
        ("Pioneer Valley Electric", 84.12, "pending"),
        ("Riverbend Family Clinic", 45.00, "pending"),
        ("Maple Street Apartments", 450.00, "pending"),
    ]
    today = date.today()
    for bill in bills:
        due = date.fromisoformat(bill["payment_date"])
        assert today <= due <= today + timedelta(days=30)
        assert bill["account_id"] == MOCK_ACCOUNT_ID
        assert run(mock.get_bill(bill["_id"])) == bill
    assert run(mock.get_merchant(merchants[0]["_id"])) == merchants[0]
    assert run(mock.list_account_purchases(MOCK_ACCOUNT_ID)) == []


def test_ids_are_deterministic_24_char_hex():
    def all_ids():
        return [record["_id"] for table in (STORE.customers, STORE.accounts,
                                            STORE.merchants, STORE.bills)
                for record in table.values()]
    first = all_ids()
    assert len(first) == 8 and len(set(first)) == 8
    assert all(ID_RE.match(i) for i in first)
    MockStore.reset()
    assert all_ids() == first


def test_purchase_reduces_balance_and_is_listed():
    mock = MockNessieWrite()
    merchant = run(mock.list_merchants())[0]
    purchase = run(mock.create_purchase(MOCK_ACCOUNT_ID, merchant["_id"], 84.12,
                                        "2026-11-14", "Electric bill"))
    assert ID_RE.match(purchase["_id"])
    assert purchase["merchant_id"] == merchant["_id"]
    assert purchase["payer_id"] == MOCK_ACCOUNT_ID
    assert purchase["amount"] == 84.12
    assert purchase["medium"] == "balance"
    assert purchase["description"] == "Electric bill"
    assert run(mock.get_account(MOCK_ACCOUNT_ID))["balance"] == 1915.88
    assert run(mock.list_account_purchases(MOCK_ACCOUNT_ID)) == [purchase]
    assert mock.last_response_meta["status"] == 200  # last call was the list


def test_store_is_shared_between_clients():
    writer, reader = MockNessieWrite(), MockNessieRead()
    merchant = run(reader.list_merchants())[1]
    run(writer.create_purchase(MOCK_ACCOUNT_ID, merchant["_id"], 45, "2026-11-14", "Clinic"))
    assert run(reader.get_account(MOCK_ACCOUNT_ID))["balance"] == 1955


def test_purchase_over_balance_is_refused_and_changes_nothing():
    mock = MockNessieWrite()
    merchant = run(mock.list_merchants())[2]
    with pytest.raises(NessieError) as caught:
        run(mock.create_purchase(MOCK_ACCOUNT_ID, merchant["_id"], 2000.01,
                                 "2026-11-14", "Too much"))
    assert caught.value.status_code == 400
    assert run(mock.get_account(MOCK_ACCOUNT_ID))["balance"] == 2000
    assert run(mock.list_account_purchases(MOCK_ACCOUNT_ID)) == []
    # Spending exactly the whole balance is allowed.
    run(mock.create_purchase(MOCK_ACCOUNT_ID, merchant["_id"], 2000, "2026-11-14", "All"))
    assert run(mock.get_account(MOCK_ACCOUNT_ID))["balance"] == 0


def test_bill_status_update():
    mock = MockNessieWrite()
    bill = run(mock.list_account_bills(MOCK_ACCOUNT_ID))[0]
    reply = run(mock.update_bill_status(bill["_id"], "completed"))
    assert reply["code"] == 202
    assert run(mock.get_bill(bill["_id"]))["status"] == "completed"
    assert run(mock.get_account(MOCK_ACCOUNT_ID))["balance"] == 2000  # status only
    with pytest.raises(NessieError):
        run(mock.update_bill_status(bill["_id"], "paid"))


def test_create_methods_return_created_objects():
    mock = MockNessieWrite()
    address = {"street_number": "9", "street_name": "New St", "city": "Testville",
               "state": "MA", "zip": "01101"}
    customer = run(mock.create_customer("Ada", "Example", address))
    assert customer["first_name"] == "Ada" and ID_RE.match(customer["_id"])
    account = run(mock.create_account(customer["_id"], "Savings", "Rainy day", 50))
    assert account["balance"] == 50 and account["customer_id"] == customer["_id"]
    assert run(mock.list_customer_accounts(customer["_id"])) == [account]
    merchant = run(mock.create_merchant("Test Shop", ["food"], address, {"lat": 1, "lng": 2}))
    assert run(mock.get_merchant(merchant["_id"])) == merchant
    bill = run(mock.create_bill(account["_id"], "pending", "Test Shop", "2026-12-01", 12.5))
    assert run(mock.list_account_bills(account["_id"])) == [bill]
    assert mock.last_response_meta["method"] == "GET"


def test_reset_restores_seed_data():
    mock = MockNessieWrite()
    merchant = run(mock.list_merchants())[0]
    bill = run(mock.list_account_bills(MOCK_ACCOUNT_ID))[0]
    run(mock.create_purchase(MOCK_ACCOUNT_ID, merchant["_id"], 100, "2026-11-14", "x"))
    run(mock.update_bill_status(bill["_id"], "completed"))
    run(mock.create_customer("Extra", "Person", {}))
    STORE.reset()
    assert run(mock.get_account(MOCK_ACCOUNT_ID))["balance"] == 2000
    assert run(mock.get_bill(bill["_id"]))["status"] == "pending"
    assert run(mock.list_account_purchases(MOCK_ACCOUNT_ID)) == []
    assert len(run(mock.list_customers())) == 1


def test_returned_dicts_are_copies():
    mock = MockNessieRead()
    account = run(mock.get_account(MOCK_ACCOUNT_ID))
    account["balance"] = 999999
    assert run(mock.get_account(MOCK_ACCOUNT_ID))["balance"] == 2000


@pytest.mark.parametrize("method_name, args", [
    ("get_customer", ("ffffffffffffffffffffffff",)),
    ("list_customer_accounts", ("ffffffffffffffffffffffff",)),
    ("get_account", ("ffffffffffffffffffffffff",)),
    ("get_merchant", ("ffffffffffffffffffffffff",)),
    ("list_account_bills", ("ffffffffffffffffffffffff",)),
    ("get_bill", ("ffffffffffffffffffffffff",)),
    ("list_account_purchases", ("ffffffffffffffffffffffff",)),
    ("create_account", ("ffffffffffffffffffffffff", "Checking", "Nick", 1)),
    ("create_bill", ("ffffffffffffffffffffffff", "pending", "Payee", "2026-12-01", 5.0)),
    ("create_purchase", ("ffffffffffffffffffffffff", "300000000000000000000001", 5.0,
                         "2026-11-14", "x")),
    ("create_purchase", (MOCK_ACCOUNT_ID, "ffffffffffffffffffffffff", 5.0,
                         "2026-11-14", "x")),
    ("update_bill_status", ("ffffffffffffffffffffffff", "completed")),
])
def test_unknown_ids_raise_404(method_name, args):
    mock = MockNessieWrite()
    with pytest.raises(NessieError) as caught:
        run(getattr(mock, method_name)(*args))
    assert caught.value.status_code == 404


def test_mock_validates_input_like_the_real_client():
    mock = MockNessieWrite()
    merchant_id = run(mock.list_merchants())[0]["_id"]
    for bad_amount in (0, -1, float("nan"), "5"):
        with pytest.raises(NessieError) as caught:
            run(mock.create_purchase(MOCK_ACCOUNT_ID, merchant_id, bad_amount,
                                     "2026-11-14", "x"))
        assert caught.value.status_code is None
    with pytest.raises(NessieError):
        run(mock.get_account("../x"))
    assert run(mock.get_account(MOCK_ACCOUNT_ID))["balance"] == 2000


def test_mock_works_as_async_context_manager():
    async def scenario():
        async with MockNessieWrite() as mock:
            return await mock.get_account(MOCK_ACCOUNT_ID)
    assert run(scenario())["balance"] == 2000


def _public_async_methods(cls) -> dict:
    return {name: member for name, member in inspect.getmembers(cls)
            if not name.startswith("_") and inspect.iscoroutinefunction(member)}


@pytest.mark.parametrize("real, mock", [(NessieReadClient, MockNessieRead),
                                        (NessieWriteClient, MockNessieWrite)])
def test_mock_has_same_interface_as_real_client(real, mock):
    real_methods = _public_async_methods(real)
    mock_methods = _public_async_methods(mock)
    assert len(real_methods) >= 10
    assert set(mock_methods) == set(real_methods)
    for name, method in real_methods.items():
        real_params = inspect.signature(method).parameters
        mock_params = inspect.signature(mock_methods[name]).parameters
        assert list(mock_params) == list(real_params), name
        for param_name, param in real_params.items():
            assert mock_params[param_name].default == param.default, (name, param_name)


def test_mock_read_class_has_no_write_methods():
    assert not hasattr(MockNessieRead, "create_purchase")
    assert not hasattr(MockNessieRead, "update_bill_status")


def test_mock_module_does_no_networking():
    import app.nessie_mock as module
    source = inspect.getsource(module)
    assert "import httpx" not in source and "AsyncClient" not in source
