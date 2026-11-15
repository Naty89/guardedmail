"""Tests for payer.py and the confirm / reject / account routes. No network."""

import ast
import asyncio
import io
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config, letters, payer, policy, store
from app.main import app
from app.nessie import NessieError
from app.nessie_mock import MOCK_ACCOUNT_ID, MockNessieWrite, MockStore
from app.schemas import PaymentIntent, ReaderOutput, ReasonId

NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
DUE = date(2026, 11, 24)
SECRET = "test-secret-0123456789abcdef"
RAW = "Pioneer Valley Electric. TOTAL AMOUNT DUE: $84.12. DUE: November 24, 2026."


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "missing.env")
    for name in ("NESSIE_API_KEY", "NESSIE_MERCHANT_IDS", "NESSIE_ACCOUNT_ID",
                 "GEMINI_API_KEY", "SEED_BALANCE_CENTS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEMO_OFFLINE", "1")
    monkeypatch.setenv("TOKEN_SECRET", SECRET)
    monkeypatch.setattr(store, "FIXTURES_DIR", tmp_path / "fixtures")
    monkeypatch.setattr(payer, "USED_TOKENS", policy.UsedTokens())
    store.STORE.reset()
    letters.reset_merchant_cache()
    MockStore.reset()
    yield
    store.STORE.reset()
    letters.reset_merchant_cache()


def electric_id() -> str:
    merchants = asyncio.run(MockNessieWrite().list_merchants())
    return next(m["_id"] for m in merchants if m["name"] == "Pioneer Valley Electric")


def make_intent(**changes) -> PaymentIntent:
    fields = dict(proposal_id=uuid4(), letter_id=uuid4(), merchant_id=electric_id(),
                  amount_cents=8412, due_date=DUE)
    fields.update(changes)
    return PaymentIntent(**fields)


def run_pay(intent, token=None, *, expires_at=None, now=NOW, balance=200000, used=None):
    expires_at = expires_at if expires_at is not None else policy.expiry_for(NOW)
    if token is None:
        token = policy.sign_token(intent, expires_at, SECRET)
    return asyncio.run(payer.pay(
        intent, token, expires_at=expires_at, now=now, secret=SECRET,
        account_id=MOCK_ACCOUNT_ID, balance_cents=balance,
        used=used if used is not None else policy.UsedTokens()))


def purchases() -> list[dict]:
    return asyncio.run(MockNessieWrite().list_account_purchases(MOCK_ACCOUNT_ID))


def bills() -> dict[str, str]:
    rows = asyncio.run(MockNessieWrite().list_account_bills(MOCK_ACCOUNT_ID))
    return {row["payee"]: row["status"] for row in rows}


# ------------------------------------------------------------------- payer


def test_valid_payment_creates_one_purchase_and_completes_the_bill():
    intent = make_intent()
    result = run_pay(intent)
    assert result.paid is True and result.reason is None
    made = purchases()
    assert len(made) == 1
    assert made[0]["_id"] == result.nessie_id
    assert made[0]["merchant_id"] == intent.merchant_id
    assert made[0]["amount"] == 84.12
    assert made[0]["description"] == f"Guarded Mail bill payment {intent.proposal_id}"
    assert result.bill_marked is True
    assert bills()["Pioneer Valley Electric"] == "completed"
    assert bills()["Riverbend Family Clinic"] == "pending"   # other bills untouched


def test_reused_token_pays_only_once():
    intent = make_intent()
    used = policy.UsedTokens()
    expires_at = policy.expiry_for(NOW)
    token = policy.sign_token(intent, expires_at, SECRET)
    assert run_pay(intent, token, used=used).paid is True
    second = run_pay(intent, token, used=used)
    assert second.paid is False and second.reason == ReasonId.TOKEN_REUSED
    assert len(purchases()) == 1


@pytest.mark.parametrize("token", ["", "0" * 64, "not-a-token"])
def test_bad_token_never_reaches_the_bank(token):
    result = run_pay(make_intent(), token)
    assert result.paid is False and result.reason == ReasonId.TOKEN_INVALID
    assert purchases() == []


def test_expired_token_never_reaches_the_bank():
    result = run_pay(make_intent(), now=NOW + timedelta(minutes=6))
    assert result.reason == ReasonId.TOKEN_EXPIRED and purchases() == []


def test_token_for_one_amount_cannot_pay_another():
    intent = make_intent()
    expires_at = policy.expiry_for(NOW)
    token = policy.sign_token(intent, expires_at, SECRET)
    bigger = intent.model_copy(update={"amount_cents": 50000})
    result = run_pay(bigger, token, expires_at=expires_at)
    assert result.reason == ReasonId.TOKEN_INVALID and purchases() == []


def test_balance_is_rechecked_at_payment_time():
    result = run_pay(make_intent(), balance=8411)
    assert result.reason == ReasonId.AMOUNT_OVER_BALANCE and purchases() == []


class FailingWrite(MockNessieWrite):
    """A bank whose purchase call fails. `lands` = the purchase went through anyway."""

    lands = False

    async def create_purchase(self, *args, **kwargs):
        if self.lands:
            await super().create_purchase(*args, **kwargs)
        raise NessieError(None, "timed out waiting for POST /accounts/x/purchases")


def test_bank_failure_reports_payment_failed(monkeypatch):
    monkeypatch.setattr(payer, "get_write_client", lambda: FailingWrite())
    result = run_pay(make_intent())
    assert result.paid is False and result.reason == ReasonId.PAYMENT_FAILED
    assert purchases() == []


def test_timeout_after_the_bank_accepted_is_found_and_counted_as_paid(monkeypatch):
    client_class = type("Lands", (FailingWrite,), {"lands": True})
    monkeypatch.setattr(payer, "get_write_client", lambda: client_class())
    result = run_pay(make_intent())
    assert result.paid is True and result.nessie_id
    assert len(purchases()) == 1


def test_bill_update_failure_does_not_undo_the_payment(monkeypatch):
    class NoBillUpdate(MockNessieWrite):
        async def update_bill_status(self, *args, **kwargs):
            raise NessieError(500, "boom")

    monkeypatch.setattr(payer, "get_write_client", lambda: NoBillUpdate())
    result = run_pay(make_intent())
    assert result.paid is True and result.bill_marked is False


def test_only_payer_and_scripts_import_the_write_client():
    app_dir = Path(payer.__file__).parent
    offenders = []
    for path in app_dir.glob("*.py"):
        if path.name in ("payer.py", "nessie.py", "nessie_mock.py"):
            continue
        source = path.read_text()
        if "get_write_client" in source or "NessieWriteClient" in source \
                or "MockNessieWrite" in source:
            offenders.append(path.name)
    assert offenders == []


def test_pay_has_no_parameter_for_text_or_client_values():
    tree = ast.parse(Path(payer.__file__).read_text())
    pay = next(n for n in ast.walk(tree)
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "pay")
    names = [a.arg for a in pay.args.args + pay.args.kwonlyargs]
    assert names == ["intent", "token", "expires_at", "now", "secret", "account_id",
                     "balance_cents", "used"]
    source = Path(payer.__file__).read_text()
    for banned in ("raw_text", "payee_candidate", "explanation", "ReaderOutput", "genai"):
        assert banned not in source


# ------------------------------------------------------------------ routes


def reading_json(**changes) -> str:
    fields = dict(doc_type="bill", payee_candidate="Pioneer Valley Electric",
                  amount_cents=8412, currency="USD", due_date=DUE, scam_signals=[],
                  confidence="high", raw_text=RAW)
    fields.update(changes)
    return ReaderOutput(**fields).model_dump_json()


class FakeCaller:
    def __init__(self, reading=None):
        self.reading = reading or reading_json()

    async def generate(self, *, system, prompt, image_jpeg, json_schema):
        return (self.reading if image_jpeg is not None else "A bill for $84.12."), "fake"


def photo(shade=200) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), (shade, shade, shade)).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def client(monkeypatch):
    today = datetime.now(timezone.utc).date()
    caller = FakeCaller(reading_json(
        due_date=today + timedelta(days=10),
        raw_text=RAW + " " + (today + timedelta(days=10)).isoformat()))

    async def fake_process(image_bytes, language):
        return await letters.process_letter(image_bytes, language, caller=caller)

    monkeypatch.setattr("app.main.process_letter", fake_process)
    return TestClient(app)


def new_proposal(client, shade=200) -> dict:
    response = client.post("/letters", data={"language": "en"},
                           files={"image": ("letter.jpg", photo(shade), "image/jpeg")})
    assert response.status_code == 200
    return response.json()


def confirm(client, proposal_id, **body):
    # Most tests are about the payment itself, so they tick the acknowledgement box.
    return client.post(f"/proposals/{proposal_id}/confirm", json={"acknowledged": True, **body})


def test_confirm_pays_and_returns_a_receipt(client):
    letter = new_proposal(client)
    proposal = letter["proposal"]
    assert proposal["action"] == "pay"
    response = confirm(client, proposal["id"], token=proposal["token"])
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "paid" and body["block_reason"] is None
    assert body["receipt"]["payee_name"] == "Pioneer Valley Electric"
    assert body["receipt"]["amount_cents"] == 8412
    assert body["receipt"]["new_balance_cents"] == 200000 - 8412
    assert len(purchases()) == 1


def test_account_shows_our_ledger_bills_and_payments(client):
    before = client.get("/account").json()
    assert before["balance_cents"] == 200000 and before["recent_payments"] == []
    assert {b["payee"]: b["amount_cents"] for b in before["bills"]} == {
        "Pioneer Valley Electric": 8412, "Riverbend Family Clinic": 4500,
        "Maple Street Apartments": 45000}
    proposal = new_proposal(client)["proposal"]
    confirm(client, proposal["id"], token=proposal["token"])
    after = client.get("/account").json()
    assert after["balance_cents"] == 191588
    assert len(after["recent_payments"]) == 1
    assert after["recent_payments"][0]["merchant_name"] == "Pioneer Valley Electric"
    statuses = {b["payee"]: b["status"] for b in after["bills"]}
    assert statuses["Pioneer Valley Electric"] == "completed"


def test_second_confirm_with_the_same_token_is_blocked(client):
    proposal = new_proposal(client)["proposal"]
    assert confirm(client, proposal["id"], token=proposal["token"]).json()["status"] == "paid"
    again = confirm(client, proposal["id"], token=proposal["token"]).json()
    assert again["status"] == "blocked" and again["block_reason"] == "token_reused"
    assert len(purchases()) == 1


def test_wrong_token_is_blocked_and_nothing_is_paid(client):
    proposal = new_proposal(client)["proposal"]
    body = confirm(client, proposal["id"], token="0" * 64).json()
    assert body == {"status": "blocked", "receipt": None, "block_reason": "token_invalid"}
    assert purchases() == []
    # The real token still works afterwards: a wrong guess burns nothing.
    assert confirm(client, proposal["id"], token=proposal["token"]).json()["status"] == "paid"


@pytest.mark.parametrize("extra", [
    {"amount_cents": 1}, {"payee_name": "Attacker"}, {"merchant_id": "attacker"},
    {"amount": 500.0}, {"intent": {"amount_cents": 50000}},
])
def test_confirm_rejects_any_amount_or_payee_from_the_client(client, extra):
    proposal = new_proposal(client)["proposal"]
    response = confirm(client, proposal["id"], token=proposal["token"], **extra)
    assert response.status_code == 422
    assert purchases() == []


def test_confirm_needs_a_token(client):
    proposal = new_proposal(client)["proposal"]
    assert confirm(client, proposal["id"]).status_code == 422
    assert confirm(client, proposal["id"], token="").status_code == 422


def test_unknown_proposal_is_blocked(client):
    body = confirm(client, str(uuid4()), token="x" * 64).json()
    assert body["status"] == "blocked" and body["block_reason"] == "proposal_not_found"
    assert client.post("/proposals/not-a-uuid/confirm", json={"acknowledged": True, "token": "x"}).status_code == 422


def test_token_from_one_proposal_cannot_confirm_another(client):
    first = new_proposal(client, shade=100)["proposal"]
    second = new_proposal(client, shade=150)["proposal"]
    body = confirm(client, second["id"], token=first["token"]).json()
    assert body["block_reason"] == "token_invalid" and purchases() == []


def test_rejected_proposal_cannot_be_confirmed(client):
    proposal = new_proposal(client)["proposal"]
    assert client.post(f"/proposals/{proposal['id']}/reject").json() == {"status": "rejected"}
    body = confirm(client, proposal["id"], token=proposal["token"]).json()
    assert body["block_reason"] == "proposal_rejected" and purchases() == []


def test_reject_unknown_proposal_is_404(client):
    assert client.post(f"/proposals/{uuid4()}/reject").status_code == 404


def test_same_letter_cannot_be_paid_twice_even_with_a_fresh_proposal(client):
    first = new_proposal(client)["proposal"]
    second = new_proposal(client)["proposal"]       # same image, new proposal + token
    assert second["action"] == "pay" and second["id"] != first["id"]
    assert confirm(client, first["id"], token=first["token"]).json()["status"] == "paid"
    body = confirm(client, second["id"], token=second["token"]).json()
    assert body["status"] == "blocked" and body["block_reason"] == "already_paid"
    assert len(purchases()) == 1
    # And reading it again no longer offers to pay at all.
    third = new_proposal(client)["proposal"]
    assert third["action"] != "pay" and third["block_reason"] == "already_paid"


def test_flagged_letter_has_nothing_to_confirm(client, monkeypatch):
    scam = FakeCaller(reading_json(doc_type="scam_suspect", scam_signals=["gift_card"]))

    async def fake_process(image_bytes, language):
        return await letters.process_letter(image_bytes, language, caller=scam)

    monkeypatch.setattr("app.main.process_letter", fake_process)
    proposal = new_proposal(client, shade=30)["proposal"]
    assert proposal["action"] == "flag" and proposal["token"] is None
    body = confirm(client, proposal["id"], token="0" * 64).json()
    assert body["block_reason"] == "proposal_not_found" and purchases() == []


def test_letter_image_route_returns_a_small_jpeg(client):
    letter = new_proposal(client)
    response = client.get(f"/letters/{letter['letter_id']}/image")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert max(Image.open(io.BytesIO(response.content)).size) <= 600
    assert client.get(f"/letters/{uuid4()}/image").status_code == 404
