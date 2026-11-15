"""Tests for audit.py and the audit trail left by the letter and payment flows."""

import asyncio
import io
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import audit, letters, payer, policy, store
from app.main import app
from app.nessie_mock import MockStore
from app.schemas import ReaderOutput

SECRET = "test-secret-0123456789abcdef"
SECRET_TEXT = "TRANSCRIPTION-MARKER-9931 Pioneer Valley Electric $84.12"


def run(coroutine):
    return asyncio.run(coroutine)


def make_log(tmp_path) -> audit.AuditLog:
    return audit.AuditLog(audit.JsonlBackend(tmp_path / "log"))


# ------------------------------------------------------------- hash chain


def test_events_are_chained_from_the_genesis_hash(tmp_path):
    log = make_log(tmp_path)
    first = run(log.record("reader", "letter_read", letter_id="a", latency_ms=5))
    second = run(log.record("policy", "policy_decided", letter_id="a", allowed=True))
    assert first["prev_hash"] == audit.GENESIS_HASH and first["seq"] == 0
    assert second["prev_hash"] == first["hash"] and second["seq"] == 1
    assert first["hash"] == audit.compute_hash(first)
    assert run(log.chain_ok()) == (True, None)


def test_chain_continues_after_a_restart(tmp_path):
    run(make_log(tmp_path).record("reader", "one"))
    again = make_log(tmp_path)                      # a new process reading the same file
    second = run(again.record("reader", "two"))
    events = run(again.events())
    assert [e["event"] for e in events] == ["one", "two"]
    assert second["prev_hash"] == events[0]["hash"]
    assert run(again.chain_ok()) == (True, None)


def _rewrite(tmp_path, change):
    path = tmp_path / "log" / audit.AUDIT_FILE
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows = change(rows)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


@pytest.mark.parametrize("change,bad_index", [
    (lambda rows: [{**rows[0], "data": {"allowed": True}}, *rows[1:]], 0),   # edit content
    (lambda rows: [rows[0], {**rows[1], "actor": "user"}, rows[2]], 1),      # edit actor
    (lambda rows: [rows[0], rows[2]], 1),                                    # delete one
    (lambda rows: [rows[1], rows[0], rows[2]], 0),                           # reorder
    (lambda rows: rows[1:], 0),                                              # drop the first
])
def test_tampering_is_detected(tmp_path, change, bad_index):
    log = make_log(tmp_path)
    for name in ("one", "two", "three"):
        run(log.record("policy", name, allowed=False))
    _rewrite(tmp_path, change)
    assert run(make_log(tmp_path).chain_ok()) == (False, bad_index)


def test_edit_with_recomputed_hash_still_breaks_the_next_link(tmp_path):
    log = make_log(tmp_path)
    for name in ("one", "two"):
        run(log.record("policy", name, amount_cents=100))

    def forge(rows):
        rows[0]["data"]["amount_cents"] = 99999
        rows[0]["hash"] = audit.compute_hash(rows[0])   # attacker fixes this event's hash
        return rows

    _rewrite(tmp_path, forge)
    assert run(make_log(tmp_path).chain_ok()) == (False, 1)


def test_unknown_actor_is_refused(tmp_path):
    with pytest.raises(ValueError):
        run(make_log(tmp_path).record("model", "anything"))


def test_raw_text_is_refused_in_the_audit_log(tmp_path):
    with pytest.raises(ValueError):
        run(make_log(tmp_path).record("reader", "letter_read", first={"raw_text": "hello"}))


def test_events_can_be_filtered_by_letter(tmp_path):
    log = make_log(tmp_path)
    run(log.record("reader", "a1", letter_id="A"))
    run(log.record("reader", "b1", letter_id="B"))
    run(log.record("policy", "a2", letter_id="A"))
    assert [e["event"] for e in run(log.events("A"))] == ["a1", "a2"]
    assert len(run(log.events())) == 3


def test_concurrent_writes_keep_one_unbroken_chain(tmp_path):
    log = make_log(tmp_path)

    async def many():
        await asyncio.gather(*[log.record("policy", f"e{i}", n=i) for i in range(40)])

    run(many())
    events = run(log.events())
    assert [e["seq"] for e in events] == list(range(40))
    assert run(log.chain_ok()) == (True, None)


def test_storage_failure_does_not_raise_from_the_helper(monkeypatch):
    class Broken:
        async def record(self, *args, **kwargs):
            raise OSError("disk full")

    monkeypatch.setattr(audit, "get_log", lambda: Broken())
    assert run(audit.record("reader", "letter_read")) is None


# ------------------------------------------------ trail left by the app flows


def reading_json(due: date) -> str:
    return ReaderOutput(
        doc_type="bill", payee_candidate="Pioneer Valley Electric", amount_cents=8412,
        currency="USD", due_date=due, scam_signals=[], confidence="high",
        raw_text=f"{SECRET_TEXT} Account number: 4471-220-918. Due {due.isoformat()}",
    ).model_dump_json()


class FakeCaller:
    def __init__(self, due):
        self.due = due

    async def generate(self, *, system, prompt, image_jpeg, json_schema):
        return (reading_json(self.due) if image_jpeg is not None else "A bill."), "fake-model"


def photo(shade=200) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), (shade, shade, shade)).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def client(monkeypatch, tmp_path):
    for name in ("NESSIE_API_KEY", "NESSIE_MERCHANT_IDS", "SEED_BALANCE_CENTS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEMO_OFFLINE", "1")
    monkeypatch.setenv("TOKEN_SECRET", SECRET)
    monkeypatch.setattr(store, "FIXTURES_DIR", tmp_path / "fixtures")
    monkeypatch.setattr(payer, "USED_TOKENS", policy.UsedTokens())
    store.STORE.reset()
    letters.reset_merchant_cache()
    MockStore.reset()
    caller = FakeCaller(datetime.now(timezone.utc).date() + timedelta(days=10))

    async def fake_process(image_bytes, language):
        return await letters.process_letter(image_bytes, language, caller=caller)

    monkeypatch.setattr("app.main.process_letter", fake_process)
    yield TestClient(app)
    store.STORE.reset()
    letters.reset_merchant_cache()


def upload(client, shade=200) -> dict:
    return client.post("/letters", data={"language": "en"},
                       files={"image": ("l.jpg", photo(shade), "image/jpeg")}).json()


def test_paying_a_letter_leaves_a_complete_verified_trail(client):
    letter = upload(client)
    proposal = letter["proposal"]
    client.post(f"/proposals/{proposal['id']}/confirm", json={"acknowledged": True, "token": proposal["token"]})

    body = client.get(f"/audit?letter_id={letter['letter_id']}").json()
    assert body["chain_ok"] is True
    events = body["events"]
    assert [(e["actor"], e["event"]) for e in events] == [
        ("reader", "letter_read"), ("reader", "scam_checked"), ("policy", "policy_decided"),
        ("user", "confirm_requested"), ("payer", "payment_executed")]
    read, scam_event, decided, _, paid = (e["data"] for e in events)
    assert len(read["image_sha256"]) == 64
    assert read["first"]["amount_cents"] == 8412 and read["model_ids"] == ["fake-model"] * 2
    assert scam_event["risk"] == "low"
    assert decided["allowed"] is True and decided["rule_ids"] == []
    assert decided["controller_action"] == "pay" and decided["merchant_name"]
    assert paid["amount_cents"] == 8412 and paid["nessie_id"]
    assert paid["tool_calls"][0]["step"] == "purchase_created"
    assert all(e["proposal_id"] == proposal["id"] for e in events[2:])


def test_transcription_goes_to_quarantine_and_never_to_the_audit_log(client):
    letter = upload(client)
    assert SECRET_TEXT not in client.get("/audit").text
    assert SECRET_TEXT not in json.dumps(letter)
    directory = audit.DATA_DIR
    assert SECRET_TEXT not in (directory / audit.AUDIT_FILE).read_text()
    quarantine = (directory / audit.QUARANTINE_FILE).read_text()
    assert SECRET_TEXT in quarantine and letter["letter_id"] in quarantine


def test_blocked_and_rejected_actions_are_logged_with_reason_ids(client):
    letter = upload(client)
    proposal = letter["proposal"]
    client.post(f"/proposals/{proposal['id']}/confirm", json={"acknowledged": True, "token": "0" * 64})
    client.post(f"/proposals/{proposal['id']}/reject")
    client.post(f"/proposals/{proposal['id']}/confirm", json={"acknowledged": True, "token": proposal["token"]})
    events = client.get(f"/audit?letter_id={letter['letter_id']}").json()["events"]
    blocked = [e["data"]["reason"] for e in events if e["event"] == "payment_blocked"]
    assert blocked == ["token_invalid", "proposal_rejected"]
    assert ("user", "proposal_rejected") in [(e["actor"], e["event"]) for e in events]


def test_audit_filter_and_bad_ids(client):
    one, two = upload(client, 100), upload(client, 150)
    assert len(client.get("/audit").json()["events"]) == 6
    assert len(client.get(f"/audit?letter_id={one['letter_id']}").json()["events"]) == 3
    assert client.get("/audit?letter_id=not-a-uuid").status_code == 422
    assert two["letter_id"] != one["letter_id"]


def test_tampered_log_is_reported_by_the_api(client):
    upload(client)
    path = audit.DATA_DIR / audit.AUDIT_FILE
    path.write_text(path.read_text().replace('"allowed": true', '"allowed": false'))
    assert client.get("/audit").json()["chain_ok"] is False


def test_ledger_survives_a_restart(client):
    letter = upload(client)
    proposal = letter["proposal"]
    client.post(f"/proposals/{proposal['id']}/confirm", json={"acknowledged": True, "token": proposal["token"]})
    assert client.get("/account").json()["balance_cents"] == 191588

    # "Restart": memory is wiped, then the app replays the audit log.
    store.STORE.reset()
    payer.USED_TOKENS = policy.UsedTokens()
    assert client.get("/account").json()["balance_cents"] == 200000
    assert run(letters.restore_from_audit()) == 1

    account = client.get("/account").json()
    assert account["balance_cents"] == 191588
    assert account["recent_payments"][0]["merchant_name"] == "Pioneer Valley Electric"
    again = upload(client)                       # the same letter image
    assert again["proposal"]["action"] != "pay"
    assert again["proposal"]["block_reason"] == "already_paid"
    assert payer.USED_TOKENS.is_used(__import__("uuid").UUID(proposal["id"]))
