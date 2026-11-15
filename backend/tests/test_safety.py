"""Payee memory, the extra acknowledgement, and what the payment side receives."""

import asyncio
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import audit, letters, payer, policy, store
from app.main import app
from app.nessie_mock import MOCK_ACCOUNT_ID, MockNessieWrite, MockStore
from app.schemas import ACK_AMOUNT_CENTS, ReaderOutput

DUE = datetime.now(timezone.utc).date() + timedelta(days=20)


def reading_json(payee="Pioneer Valley Electric", cents=8412, **changes) -> str:
    dollars, rest = divmod(cents, 100)
    fields = dict(doc_type="bill", payee_candidate=payee, amount_cents=cents, currency="USD",
                  due_date=DUE, scam_signals=[], confidence="high",
                  raw_text=f"Account number: 4471-220-918. ${dollars}.{rest:02d} due {DUE.isoformat()}")
    fields.update(changes)
    return ReaderOutput(**fields).model_dump_json()


class Caller:
    def __init__(self):
        self.reading = reading_json()

    async def generate(self, *, system, prompt, image_jpeg, json_schema):
        return (self.reading if image_jpeg is not None else "A bill."), "fake"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_OFFLINE", "1")
    monkeypatch.setenv("TOKEN_SECRET", "test-secret-0123456789abcdef")
    monkeypatch.setattr(store, "FIXTURES_DIR", tmp_path / "fixtures")
    monkeypatch.setattr(payer, "USED_TOKENS", policy.UsedTokens())
    store.STORE.reset()
    letters.reset_merchant_cache()
    MockStore.reset()
    caller = Caller()

    async def fake_process(image_bytes, language):
        return await letters.process_letter(image_bytes, language, caller=caller)

    monkeypatch.setattr("app.main.process_letter", fake_process)
    test_client = TestClient(app)
    test_client.caller = caller
    yield test_client
    store.STORE.reset()
    letters.reset_merchant_cache()


def upload(client, shade, payee="Pioneer Valley Electric", cents=8412, **changes) -> dict:
    client.caller.reading = reading_json(payee, cents, **changes)
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), (shade, shade, shade)).save(buffer, "JPEG")
    return client.post("/letters", data={"language": "en"},
                       files={"image": ("l.jpg", buffer.getvalue(), "image/jpeg")}).json()


def confirm(client, proposal, **extra):
    return client.post(f"/proposals/{proposal['id']}/confirm",
                       json={"token": proposal["token"], **extra}).json()


def purchases():
    return asyncio.run(MockNessieWrite().list_account_purchases(MOCK_ACCOUNT_ID))


# ------------------------------------------------------------- payee memory


def test_first_payment_to_a_payee_is_marked_and_needs_the_acknowledgement(client):
    proposal = upload(client, 50)["proposal"]
    assert proposal["first_payment"] is True and proposal["last_paid"] is None
    assert proposal["requires_ack"] is True


def test_confirm_without_the_tick_is_blocked_and_the_token_is_not_used_up(client):
    proposal = upload(client, 50)["proposal"]
    blocked = confirm(client, proposal)
    assert blocked == {"status": "blocked", "receipt": None,
                       "block_reason": "acknowledgement_required"}
    assert purchases() == []
    assert confirm(client, proposal, acknowledged=False)["block_reason"] == "acknowledgement_required"
    paid = confirm(client, proposal, acknowledged=True)         # the same token still works
    assert paid["status"] == "paid" and len(purchases()) == 1


def test_a_small_repeat_payment_to_a_known_payee_needs_no_tick(client):
    first = upload(client, 50)["proposal"]
    assert confirm(client, first, acknowledged=True)["status"] == "paid"
    second = upload(client, 90, cents=4000)["proposal"]       # a different letter, same payee
    assert second["first_payment"] is False
    assert second["last_paid"] == datetime.now(timezone.utc).date().isoformat()
    assert second["requires_ack"] is False
    assert confirm(client, second)["status"] == "paid"


def test_a_large_payment_needs_the_tick_even_to_a_known_payee(client):
    confirm(client, upload(client, 50)["proposal"], acknowledged=True)
    big = upload(client, 130, cents=ACK_AMOUNT_CENTS)["proposal"]
    assert big["first_payment"] is False and big["requires_ack"] is True
    assert confirm(client, big)["block_reason"] == "acknowledgement_required"
    assert confirm(client, big, acknowledged=True)["status"] == "paid"


def test_just_under_the_large_limit_needs_no_tick_for_a_known_payee(client):
    confirm(client, upload(client, 50)["proposal"], acknowledged=True)
    assert upload(client, 130, cents=ACK_AMOUNT_CENTS - 1)["proposal"]["requires_ack"] is False


def test_the_tick_is_the_only_new_field_the_client_may_send(client):
    proposal = upload(client, 50)["proposal"]
    for extra in ({"amount_cents": 1}, {"payee_name": "x"}, {"merchant_id": "x"}):
        response = client.post(f"/proposals/{proposal['id']}/confirm",
                               json={"token": proposal["token"], "acknowledged": True, **extra})
        assert response.status_code == 422
    assert purchases() == []


def test_payee_memory_survives_a_restart(client):
    confirm(client, upload(client, 50)["proposal"], acknowledged=True)
    store.STORE.reset()
    assert asyncio.run(letters.restore_from_audit()) == 1
    again = upload(client, 90, cents=4000)["proposal"]
    assert again["first_payment"] is False and again["requires_ack"] is False


def test_the_acknowledgement_is_recorded_in_the_audit_log(client):
    letter = upload(client, 50)
    confirm(client, letter["proposal"], acknowledged=True)
    paid = [e for e in client.get(f"/audit?letter_id={letter['letter_id']}").json()["events"]
            if e["event"] == "payment_executed"]
    assert paid[0]["data"]["acknowledged"] is True


def test_non_payable_letters_have_no_payee_memory_fields_set(client):
    unknown = upload(client, 70, payee="Hilltop Water District")["proposal"]
    assert unknown["action"] == "calendar"
    assert unknown["first_payment"] is None and unknown["requires_ack"] is False


# --------------------------------------------------- what the payment side saw


def test_debug_shows_exactly_what_the_payment_side_receives(client):
    letter = upload(client, 50)
    debug = client.get(f"/letters/{letter['letter_id']}/debug").json()
    assert debug["payment_side"] == {
        "proposal_id": letter["proposal"]["id"],
        "merchant_id": debug["payment_side"]["merchant_id"],
        "amount_cents": 8412, "due_date": letter["proposal"]["due_date"]}
    assert set(debug["payment_side"]) == {"proposal_id", "merchant_id", "amount_cents", "due_date"}
    assert "Account number" not in str(debug)          # no letter text in there


def test_a_flagged_letter_sends_nothing_to_the_payment_side(client):
    letter = upload(client, 60, doc_type="scam_suspect", scam_signals=["gift_card"])
    assert letter["proposal"]["action"] == "flag"
    assert client.get(f"/letters/{letter['letter_id']}/debug").json()["payment_side"] is None


# ------------------------------------------------------- check state in the API


def test_response_carries_the_honest_state_and_notices(client):
    clear = upload(client, 50)
    assert clear["check_state"] == "no_warning_signs" and clear["notices"] == []
    scam = upload(client, 60, doc_type="scam_suspect", scam_signals=["gift_card"])
    assert scam["check_state"] == "possible_scam" and scam["notices"] == []
    unsure = upload(client, 70, confidence="low")
    assert unsure["check_state"] == "cannot_tell"
    assert unsure["proposal"]["action"] != "pay"          # a blurry reading is never payable


def test_a_medium_risk_letter_says_we_cannot_tell_and_is_not_payable(client):
    letter = upload(client, 80, scam_signals=["urgency"])
    assert letter["check_state"] == "cannot_tell" and letter["scam"]["risk"] == "med"
    assert letter["proposal"]["action"] == "flag" and letter["proposal"]["token"] is None
