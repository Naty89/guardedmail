"""Tests for history.py and the /history routes. No network."""

import asyncio
import io
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import audit, letters, payer, policy, store
from app.history import build_history
from app.main import app
from app.nessie_mock import MockStore
from app.schemas import ReaderOutput

SHA_A, SHA_B, SHA_C, SHA_D = "a" * 64, "b" * 64, "c" * 64, "d" * 64


def lid(n: int) -> str:
    """A letter id (they are UUIDs)."""
    return f"00000000-0000-0000-0000-{n:012d}"


def read_event(n, ts, sha=SHA_A, language="en", sender="Pioneer Valley Electric",
               amount=8412, due="2026-11-24", doc_type="bill"):
    return {"letter_id": lid(n), "ts": ts, "actor": "reader", "event": "letter_read",
            "data": {"image_sha256": sha, "language": language,
                     "first": {"payee_candidate": sender, "amount_cents": amount,
                               "due_date": due, "doc_type": doc_type}}}


def scam_event(n, risk="low"):
    return {"letter_id": lid(n), "actor": "reader", "event": "scam_checked",
            "ts": "2026-11-14T10:00:01+00:00", "data": {"risk": risk, "reason_ids": []}}


def policy_event(n, action):
    return {"letter_id": lid(n), "actor": "policy", "event": "policy_decided",
            "ts": "2026-11-14T10:00:02+00:00", "data": {"controller_action": action}}


def paid_event(n, sha):
    return {"letter_id": lid(n), "ts": "2026-11-14T10:05:00+00:00", "actor": "payer",
            "event": "payment_executed", "data": {"image_sha256": sha}}


def rejected_event(n):
    return {"letter_id": lid(n), "ts": "2026-11-14T10:06:00+00:00", "actor": "user",
            "event": "proposal_rejected", "data": {}}


T1, T2, T3, T4 = ("2026-11-14T10:00:00+00:00", "2026-11-14T11:00:00+00:00",
                  "2026-11-14T12:00:00+00:00", "2026-11-14T13:00:00+00:00")


def history_of(*events):
    return build_history(list(events))


# --------------------------------------------------------------- build_history


def test_open_letter_shows_facts_and_status_open():
    [item] = history_of(read_event(1, T1), scam_event(1), policy_event(1, "pay"))
    assert item.sender == "Pioneer Valley Electric" and item.amount_cents == 8412
    assert item.due_date.isoformat() == "2026-11-24" and item.doc_type == "bill"
    assert item.status == "open" and item.risk == "low" and str(item.letter_id) == lid(1)


def test_each_status_is_derived_from_the_events():
    items = history_of(
        read_event(1, T1, sha=SHA_A), scam_event(1), policy_event(1, "pay"), paid_event(1, SHA_A),
        read_event(2, T2, sha=SHA_B, sender="Fast Cash"), scam_event(2, "high"), policy_event(2, "flag"),
        read_event(3, T3, sha=SHA_C), scam_event(3), policy_event(3, "pay"), rejected_event(3),
        read_event(4, T4, sha=SHA_D, doc_type="notice", amount=0, due=None),
        scam_event(4), policy_event(4, "ask_user"))
    status = {str(i.letter_id): i.status for i in items}
    assert status == {lid(1): "paid", lid(2): "flagged", lid(3): "declined", lid(4): "info"}
    assert [str(i.letter_id) for i in items] == [lid(4), lid(3), lid(2), lid(1)]   # newest first


def test_paid_beats_flagged_and_flagged_beats_declined():
    [paid] = history_of(read_event(1, T1), scam_event(1, "high"), paid_event(1, SHA_A))
    assert paid.status == "paid"
    [flagged] = history_of(read_event(1, T1), scam_event(1, "med"), rejected_event(1))
    assert flagged.status == "flagged"


def test_same_photo_read_twice_appears_once_with_the_latest_state():
    items = history_of(read_event(1, T1), scam_event(1), policy_event(1, "pay"),
                       read_event(2, T3), scam_event(2), policy_event(2, "pay"))
    assert len(items) == 1 and str(items[0].letter_id) == lid(2)


def test_same_photo_in_two_languages_is_two_items():
    items = history_of(read_event(1, T1, language="en"), read_event(2, T2, language="es"))
    assert {i.language for i in items} == {"en", "es"}


def test_a_payment_makes_every_reading_of_that_photo_paid():
    [item] = history_of(read_event(1, T1), policy_event(1, "pay"),
                        read_event(2, T2), policy_event(2, "pay"), paid_event(2, SHA_A),
                        read_event(3, T3), policy_event(3, "calendar"))
    assert item.status == "paid" and str(item.letter_id) == lid(3)


def test_declining_one_reading_counts_for_the_photo():
    [item] = history_of(read_event(1, T1), policy_event(1, "pay"), rejected_event(1),
                        read_event(2, T2), policy_event(2, "pay"))
    assert item.status == "declined"


def test_empty_log_and_unrelated_events():
    assert history_of() == []
    assert history_of({"letter_id": lid(1), "ts": T1, "event": "question_asked", "data": {}}) == []


def test_missing_amount_and_date_are_none():
    [item] = history_of(read_event(1, T1, amount=0, due=None))
    assert item.amount_cents is None and item.due_date is None


# --------------------------------------------------------------------- routes


def reading_json(**changes) -> str:
    due = datetime.now(timezone.utc).date() + timedelta(days=10)
    fields = dict(doc_type="bill", payee_candidate="Pioneer Valley Electric", amount_cents=8412,
                  currency="USD", due_date=due, scam_signals=[], confidence="high",
                  raw_text=f"Account number: 4471-220-918 $84.12 {due.isoformat()}")
    fields.update(changes)
    return ReaderOutput(**fields).model_dump_json()


class Caller:
    def __init__(self):
        self.calls = 0

    async def generate(self, *, system, prompt, image_jpeg, json_schema):
        self.calls += 1
        return (reading_json() if image_jpeg is not None else "A bill for $84.12."), "fake"


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


def upload(client, shade=60, language="en") -> dict:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), (shade, shade, shade)).save(buffer, "JPEG")
    return client.post("/letters", data={"language": language},
                       files={"image": ("l.jpg", buffer.getvalue(), "image/jpeg")}).json()


def test_history_lists_letters_newest_first_with_status(client):
    first = upload(client, 50)
    second = upload(client, 120)
    items = client.get("/history").json()["items"]
    assert [i["letter_id"] for i in items] == [second["letter_id"], first["letter_id"]]
    assert items[0]["sender"] == "Pioneer Valley Electric" and items[0]["amount_cents"] == 8412
    assert {i["status"] for i in items} == {"open"}


def test_paying_a_letter_marks_it_paid_in_history(client):
    letter = upload(client)
    proposal = letter["proposal"]
    client.post(f"/proposals/{proposal['id']}/confirm", json={"acknowledged": True, "token": proposal["token"]})
    [item] = client.get("/history").json()["items"]
    assert item["status"] == "paid"


def test_declining_marks_it_declined(client):
    letter = upload(client)
    client.post(f"/proposals/{letter['proposal']['id']}/reject")
    assert client.get("/history").json()["items"][0]["status"] == "declined"


def test_history_survives_a_restart_because_it_is_rebuilt_from_the_log(client):
    upload(client)
    store.STORE.reset()
    assert len(client.get("/history").json()["items"]) == 1


def test_reopen_gives_a_fresh_result_without_calling_the_model_again(client):
    letter = upload(client)
    calls_before = client.caller.calls
    reopened = client.post(f"/history/{letter['letter_id']}/open")
    assert reopened.status_code == 200
    body = reopened.json()
    assert client.caller.calls == calls_before                  # no photo, no model
    assert body["letter_id"] != letter["letter_id"]
    assert body["proposal"]["action"] == "pay"
    assert body["proposal"]["id"] != letter["proposal"]["id"]    # a NEW proposal ...
    assert body["proposal"]["token"] != letter["proposal"]["token"]   # ... and a new token
    assert body["explanation"] == letter["explanation"]
    assert len(client.get("/history").json()["items"]) == 1     # still one entry


def test_reopened_letter_can_be_paid_with_its_new_token(client):
    letter = upload(client)
    body = client.post(f"/history/{letter['letter_id']}/open").json()
    result = client.post(f"/proposals/{body['proposal']['id']}/confirm",
                         json={"acknowledged": True, "token": body["proposal"]["token"]}).json()
    assert result["status"] == "paid"


def test_reopening_a_paid_letter_cannot_pay_again(client):
    letter = upload(client)
    proposal = letter["proposal"]
    client.post(f"/proposals/{proposal['id']}/confirm", json={"acknowledged": True, "token": proposal["token"]})
    body = client.post(f"/history/{letter['letter_id']}/open").json()
    assert body["proposal"]["action"] != "pay" and body["proposal"]["token"] is None
    assert body["proposal"]["block_reason"] == "already_paid"


def test_reopen_after_a_restart_works_and_keeps_the_thumbnail(client):
    letter = upload(client)
    store.STORE.reset()
    body = client.post(f"/history/{letter['letter_id']}/open").json()
    assert client.get(f"/letters/{body['letter_id']}/image").status_code == 200


def test_reopen_unknown_or_missing_text(client):
    assert client.post(f"/history/{uuid4()}/open").status_code == 404
    letter = upload(client)
    for path in store.readings_dir().glob("*.json"):
        path.unlink()
    response = client.post(f"/history/{letter['letter_id']}/open")
    assert response.status_code == 404 and response.json()["detail"]["error"] == "letter_text_unavailable"
    assert client.post("/history/not-a-uuid/open").status_code == 422


def test_reopen_is_marked_in_the_audit_log_and_text_is_not_logged_twice(client):
    letter = upload(client)
    client.post(f"/history/{letter['letter_id']}/open")
    events = [e for e in asyncio.run(audit.get_log().events()) if e["event"] == "letter_read"]
    assert [e["data"]["reopened"] for e in events] == [False, True]
    quarantine = (audit.DATA_DIR / audit.QUARANTINE_FILE).read_text().strip().splitlines()
    assert len(quarantine) == 1


def test_new_uploads_are_cached_in_the_data_folder_not_in_the_repo_fixtures(client, tmp_path):
    upload(client)
    assert list(store.readings_dir().glob("*.json")) and list(store.thumbs_dir().glob("*.jpg"))
    assert not (tmp_path / "fixtures").exists() or not list((tmp_path / "fixtures").glob("*.json"))


def test_committed_fixtures_are_still_found(client, tmp_path):
    letter = upload(client)
    sha = asyncio.run(audit.get_log().events())[0]["data"]["image_sha256"]
    # Move the cached reading into the (fixtures) folder, as the demo samples are.
    for path in store.readings_dir().glob("*.json"):
        target = store.FIXTURES_DIR / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        path.rename(target)
    assert store.load_cached_reading(sha, "en") is not None
    assert client.post(f"/history/{letter['letter_id']}/open").status_code == 200
