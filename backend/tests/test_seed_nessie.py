"""Tests for the Nessie seed and balance-check scripts (offline mock, no network).

Every test writes its env file under pytest's tmp_path, never the real .env.
"""

import asyncio
from datetime import date, timedelta

import pytest
from dotenv import dotenv_values

from app.config import ENV_PATH
from app.nessie_mock import (MOCK_ACCOUNT_ID, MOCK_CUSTOMER_ID, MockNessieWrite,
                             MockStore)
from scripts import seed_nessie
from scripts.check_nessie_balance import LEDGER_REMINDER, run_check
from scripts.seed_nessie import MERCHANTS, seed, upsert_env

MERCHANT_NAMES = ["Pioneer Valley Electric", "Riverbend Family Clinic",
                  "Maple Street Apartments"]
BILL_AMOUNTS = {"Pioneer Valley Electric": 84.12, "Riverbend Family Clinic": 45.00,
                "Maple Street Apartments": 450.00}


@pytest.fixture(autouse=True)
def fresh_store():
    """Start each test from the pre-seeded mock store and leave it that way."""
    MockStore.reset()
    yield
    MockStore.reset()


@pytest.fixture(autouse=True)
def real_env_untouched():
    """Fail loudly if a test changes (or creates) the real repo .env file."""
    before = ENV_PATH.read_bytes() if ENV_PATH.exists() else None
    yield
    after = ENV_PATH.read_bytes() if ENV_PATH.exists() else None
    assert before == after, "a test modified the real .env file"


def empty_the_store():
    """Remove the pre-seeded data so the mock looks like a brand-new Nessie key."""
    MockStore.customers.clear()
    MockStore.accounts.clear()
    MockStore.merchants.clear()
    MockStore.bills.clear()
    MockStore.purchases.clear()


def store_counts() -> dict:
    return {name: len(getattr(MockStore, name))
            for name in ("customers", "accounts", "merchants", "bills", "purchases")}


# --- seed ----------------------------------------------------------------------

def test_seed_creates_everything_on_an_empty_store(tmp_path):
    empty_the_store()
    env_path = tmp_path / ".env"

    result = asyncio.run(seed(MockNessieWrite(), env_path))

    assert store_counts() == {"customers": 1, "accounts": 1, "merchants": 3,
                              "bills": 3, "purchases": 0}
    assert len(result["created"]) == 8
    assert result["reused"] == []

    customer = MockStore.customers[result["customer_id"]]
    assert (customer["first_name"], customer["last_name"]) == ("Demo", "User")
    account = MockStore.accounts[result["account_id"]]
    assert account["type"] == "Checking"
    assert account["nickname"] == "Guarded Demo Checking"
    assert account["balance"] == 2000
    assert account["rewards"] == 0
    assert account["customer_id"] == result["customer_id"]

    # Merchants come back in the contract order: utility, clinic, landlord.
    names = [MockStore.merchants[m]["name"] for m in result["merchant_ids"]]
    assert names == MERCHANT_NAMES
    categories = [MockStore.merchants[m]["category"] for m in result["merchant_ids"]]
    assert categories == [["utilities"], ["health"], ["rent"]]

    saved = dotenv_values(env_path)
    assert saved == {
        "NESSIE_CUSTOMER_ID": result["customer_id"],
        "NESSIE_ACCOUNT_ID": result["account_id"],
        "NESSIE_MERCHANT_IDS": ",".join(result["merchant_ids"]),
        "SEED_BALANCE_CENTS": "200000",
    }


def test_seed_bills_match_merchants_and_contract_amounts(tmp_path):
    empty_the_store()

    result = asyncio.run(seed(MockNessieWrite(), tmp_path / ".env"))

    bills = [MockStore.bills[b] for b in result["bill_ids"]]
    assert [b["payee"] for b in bills] == MERCHANT_NAMES
    assert [b["payee"] for b in bills] == [m["name"] for m in MERCHANTS]
    today = date.today()
    for bill in bills:
        assert bill["payment_amount"] == BILL_AMOUNTS[bill["payee"]]
        assert bill["status"] == "pending"
        assert bill["account_id"] == result["account_id"]
        due = date.fromisoformat(bill["payment_date"])
        assert today < due <= today + timedelta(days=30)


def test_seed_reuses_the_preseeded_mock_without_saved_ids(tmp_path):
    # Store state: pre-seeded by MockStore.reset(); the env file does not exist.
    before = store_counts()

    result = asyncio.run(seed(MockNessieWrite(), tmp_path / ".env"))

    assert result["created"] == []
    assert len(result["reused"]) == 8
    assert store_counts() == before
    assert result["customer_id"] == MOCK_CUSTOMER_ID
    assert result["account_id"] == MOCK_ACCOUNT_ID
    assert [MockStore.merchants[m]["name"] for m in result["merchant_ids"]] == MERCHANT_NAMES


def test_second_run_creates_nothing_and_returns_the_same_ids(tmp_path):
    empty_the_store()
    env_path = tmp_path / ".env"

    first = asyncio.run(seed(MockNessieWrite(), env_path))
    counts_after_first = store_counts()
    env_after_first = env_path.read_text()
    second = asyncio.run(seed(MockNessieWrite(), env_path))

    assert second["created"] == []
    assert len(second["reused"]) == 8
    assert store_counts() == counts_after_first
    for key in ("customer_id", "account_id", "merchant_ids", "bill_ids"):
        assert second[key] == first[key]
    assert env_path.read_text() == env_after_first


def test_seed_prefers_saved_merchant_ids_over_same_named_junk(tmp_path):
    """The global merchant list may hold other teams' merchants with our names."""
    empty_the_store()
    env_path = tmp_path / ".env"
    first = asyncio.run(seed(MockNessieWrite(), env_path))

    # Junk: a duplicate of our utility with a lower id, plus lots of unrelated rows.
    MockStore.merchants["0junk"] = {"_id": "0junk", "name": "Pioneer Valley Electric",
                                    "category": ["junk"]}
    for number in range(500):
        MockStore.merchants[f"9junk{number}"] = {"_id": f"9junk{number}",
                                                 "name": f"Junk {number}"}
    second = asyncio.run(seed(MockNessieWrite(), env_path))

    assert second["merchant_ids"] == first["merchant_ids"]
    assert second["created"] == []


def test_seed_recreates_objects_when_saved_ids_no_longer_exist(tmp_path):
    empty_the_store()
    env_path = tmp_path / ".env"
    env_path.write_text("NESSIE_CUSTOMER_ID=1ffffffffffffffffffffff9\n"
                        "NESSIE_ACCOUNT_ID=2ffffffffffffffffffffff9\n"
                        "NESSIE_MERCHANT_IDS=3ffffffffffffffffffffff9,not-an-id\n")

    result = asyncio.run(seed(MockNessieWrite(), env_path))

    assert len(result["created"]) == 8
    assert result["customer_id"] in MockStore.customers
    assert dotenv_values(env_path)["NESSIE_CUSTOMER_ID"] == result["customer_id"]


def test_seed_keeps_other_lines_of_the_env_file(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("# my settings\nNESSIE_API_KEY=invented-test-value\n")

    asyncio.run(seed(MockNessieWrite(), env_path))

    text = env_path.read_text()
    assert text.startswith("# my settings\nNESSIE_API_KEY=invented-test-value\n")
    assert f"NESSIE_ACCOUNT_ID={MOCK_ACCOUNT_ID}\n" in text


# --- upsert_env ----------------------------------------------------------------

def test_upsert_env_creates_a_missing_file(tmp_path):
    env_path = tmp_path / "new" / ".env"

    upsert_env(env_path, {"A": "1", "B": "two"})

    assert env_path.read_text() == "A=1\nB=two\n"


def test_upsert_env_updates_in_place_and_preserves_everything_else(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# Guarded settings\n"
        "GEMINI_API_KEY=invented-gemini\n"
        "\n"
        "# NESSIE_ACCOUNT_ID=commented-out\n"
        "NESSIE_ACCOUNT_ID=old-account   \n"
        "OTHER = spaced value # trailing comment\n"
        "NESSIE_CUSTOMER_ID=old-customer"  # no newline at the end of the file
    )

    upsert_env(env_path, {"NESSIE_CUSTOMER_ID": "c1", "NESSIE_ACCOUNT_ID": "a1",
                          "SEED_BALANCE_CENTS": "200000"})

    assert env_path.read_text() == (
        "# Guarded settings\n"
        "GEMINI_API_KEY=invented-gemini\n"
        "\n"
        "# NESSIE_ACCOUNT_ID=commented-out\n"
        "NESSIE_ACCOUNT_ID=a1\n"
        "OTHER = spaced value # trailing comment\n"
        "NESSIE_CUSTOMER_ID=c1\n"
        "SEED_BALANCE_CENTS=200000\n"
    )


def test_upsert_env_is_idempotent_and_leaves_no_temp_files(tmp_path):
    env_path = tmp_path / ".env"
    values = {"NESSIE_MERCHANT_IDS": "m1,m2,m3", "SEED_BALANCE_CENTS": "200000"}

    upsert_env(env_path, values)
    once = env_path.read_text()
    upsert_env(env_path, values)

    assert env_path.read_text() == once
    assert [p.name for p in tmp_path.iterdir()] == [".env"]


# --- command line --------------------------------------------------------------

def test_main_exits_with_help_when_there_is_no_key(monkeypatch, capsys, tmp_path):
    # Set to "" (not deleted) so a key in a real .env file cannot be loaded.
    monkeypatch.setenv("NESSIE_API_KEY", "")
    monkeypatch.setenv("DEMO_OFFLINE", "")

    with pytest.raises(SystemExit) as exit_info:
        seed_nessie.main(["--env-path", str(tmp_path / ".env")])

    assert exit_info.value.code != 0
    message = capsys.readouterr().err
    assert "NESSIE_API_KEY" in message
    assert "https://api.nessieisreal.com" in message
    assert "GitHub" in message
    assert not (tmp_path / ".env").exists()


def test_main_offline_writes_only_the_given_env_path(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("DEMO_OFFLINE", "1")
    env_path = tmp_path / ".env"

    assert seed_nessie.main(["--env-path", str(env_path)]) == 0

    assert dotenv_values(env_path)["NESSIE_CUSTOMER_ID"] == MOCK_CUSTOMER_ID
    assert "OFFLINE MOCK" in capsys.readouterr().out


# --- balance check -------------------------------------------------------------

def test_run_check_against_the_mock(tmp_path):
    lines = []
    demo_account_before = dict(MockStore.accounts[MOCK_ACCOUNT_ID])
    demo_bills_before = {k: dict(v) for k, v in MockStore.bills.items()}

    result = asyncio.run(run_check(MockNessieWrite(), poll_seconds=(), out=lines.append))

    assert result["mock"] is True
    assert result["purchase_post_works"] is True
    assert result["purchase_status"] == "executed"
    assert result["balance_before"] == 100
    assert result["balance_after"] == 99
    assert result["balance_changed"] is True
    assert result["bill_put_works"] is True
    assert result["errors"] == []
    assert LEDGER_REMINDER in result["conclusion"]

    output = "\n".join(lines)
    assert "MOCK" in output
    assert "RESULT: purchase POST path works: yes" in output
    assert "RESULT: balance changed after purchase: yes (100 -> 99)" in output
    assert "RESULT: bill PUT status=completed works: yes" in output
    assert "CONCLUSION:" in output

    # The demo account and its bills were not touched.
    assert MockStore.accounts[MOCK_ACCOUNT_ID] == demo_account_before
    for bill_id, bill in demo_bills_before.items():
        assert MockStore.bills[bill_id] == bill


def test_run_check_reports_no_change_when_the_balance_stays(tmp_path):
    """Simulates a bank where a purchase is recorded but the balance never moves."""

    class NoDeductionClient(MockNessieWrite):
        async def create_purchase(self, account_id, *args, **kwargs):
            purchase = await super().create_purchase(account_id, *args, **kwargs)
            self.store.accounts[account_id]["balance"] = 100  # undo the mock's deduction
            self.store.purchases[purchase["_id"]]["status"] = "pending"
            return {**purchase, "status": "pending"}

    lines, waits = [], []

    async def fake_sleep(seconds):
        waits.append(seconds)

    result = asyncio.run(run_check(NoDeductionClient(), poll_seconds=(2, 5, 10),
                                   sleep=fake_sleep, out=lines.append))

    assert result["balance_changed"] is False
    assert result["purchase_status"] == "pending"
    assert waits == [2, 3, 5]  # polled at 2s, 5s and 10s after the purchase
    assert "RESULT: balance changed after purchase: no (stayed 100)" in "\n".join(lines)
    assert LEDGER_REMINDER in result["conclusion"]


def test_run_check_still_gives_a_verdict_when_the_purchase_fails(tmp_path):
    from app.nessie import NessieError

    class BrokenPurchaseClient(MockNessieWrite):
        async def create_purchase(self, *args, **kwargs):
            raise NessieError(404, "no such path")

    lines = []
    result = asyncio.run(run_check(BrokenPurchaseClient(), poll_seconds=(),
                                   out=lines.append))

    assert result["purchase_post_works"] is False
    assert result["balance_changed"] is None
    assert result["bill_put_works"] is True  # later steps still ran
    output = "\n".join(lines)
    assert "RESULT: purchase POST path works: no" in output
    assert "RESULT: balance changed after purchase: unknown (" in output
    assert LEDGER_REMINDER in result["conclusion"]
