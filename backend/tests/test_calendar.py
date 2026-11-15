"""Tests for calendar_export.py and GET /letters/{id}/calendar.ics. No network."""

import io
import re
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import calendar_export as cal
from app import letters, payer, policy, store
from app.main import app
from app.nessie_mock import MockStore
from app.schemas import LANGUAGES, ReaderOutput

DUE = date(2026, 11, 24)
NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
LETTER = UUID("11111111-1111-1111-1111-111111111111")


def build(**changes) -> str:
    args = dict(letter_id=LETTER, language="en", due=DUE, name="Pioneer Valley Electric",
                amount_cents=8412, now=NOW)
    args.update(changes)
    return cal.build_ics(**args)


def properties(ics: str) -> list[str]:
    """Unfold the file and return its lines."""
    return ics.replace("\r\n ", "").split("\r\n")[:-1]


def test_file_is_a_well_formed_all_day_event_with_three_reminders():
    lines = properties(build())
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-1] == "END:VCALENDAR"
    assert "VERSION:2.0" in lines and "BEGIN:VEVENT" in lines and "END:VEVENT" in lines
    assert "DTSTART;VALUE=DATE:20261124" in lines and "DTEND;VALUE=DATE:20261125" in lines
    assert f"UID:{LETTER}@guarded-mail" in lines
    assert "DTSTAMP:20261114T120000Z" in lines
    assert lines.count("BEGIN:VALARM") == lines.count("END:VALARM") == 3
    # A week before, the day before, and on the day, all at 9:00.
    assert "TRIGGER:-P6DT15H" in lines and "TRIGGER:-PT15H" in lines and "TRIGGER:PT9H" in lines
    assert lines.count("ACTION:DISPLAY") == 3


def test_lines_end_with_crlf_and_are_at_most_75_bytes():
    ics = build(name="A very long company name " * 6)
    assert ics.endswith("\r\n") and "\n" not in ics.replace("\r\n", "")
    for line in ics.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, line


def test_folding_never_cuts_a_multibyte_character():
    ics = build(language="te", name="పయనీర్ వ్యాలీ ఎలక్ట్రిక్ " * 5)
    for line in ics.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    ics.encode("utf-8").decode("utf-8")  # still valid UTF-8 after folding
    unfolded = ics.replace("\r\n ", "")
    assert "పయనీర్" in unfolded


@pytest.mark.parametrize("hostile", [
    "Evil\r\nATTACH:http://attacker.example/x",
    "Evil\nBEGIN:VALARM\nTRIGGER:-PT1M",
    "Evil ORGANIZER:mailto:x@y.z",
    "semi;colon, comma \\ backslash",
    "tab\there\x00nul\x1bescape",
])
def test_letter_text_cannot_add_calendar_properties(hostile):
    lines = properties(build(name=hostile))
    names = {line.split(":")[0].split(";")[0] for line in lines}
    assert names <= {"BEGIN", "END", "VERSION", "PRODID", "CALSCALE", "METHOD", "UID",
                     "DTSTAMP", "DTSTART", "DTEND", "SUMMARY", "DESCRIPTION", "TRANSP",
                     "ACTION", "TRIGGER"}
    assert lines.count("BEGIN:VALARM") == 3
    summary = next(line for line in lines if line.startswith("SUMMARY:"))
    # Every comma, semicolon and backslash inside the text is escaped.
    assert not re.search(r"(?<!\\)[;,]", summary[len("SUMMARY:"):].replace("\\\\", ""))


def test_amount_is_only_included_when_given():
    assert "$84.12" in build()
    assert "$" not in build(amount_cents=None).split("DESCRIPTION:")[1].split("\r\n")[0]


def test_every_language_has_texts_and_unknown_falls_back_to_english():
    assert set(cal.TEXTS) == set(LANGUAGES)
    assert "Deadline" in build(language="xx")
    assert "Fecha límite" in build(language="es")


def test_name_may_be_empty():
    assert "SUMMARY:Deadline\r\n" in build(name="  ")


def test_filename_uses_the_date():
    assert cal.filename_for(DUE) == "guarded-mail-deadline-2026-11-24.ics"


# ------------------------------------------------------------------ route


def reading_json(**changes) -> str:
    due = datetime.now(timezone.utc).date() + timedelta(days=10)
    fields = dict(doc_type="bill", payee_candidate="Pioneer Valley Electric",
                  amount_cents=8412, currency="USD", due_date=due, scam_signals=[],
                  confidence="high",
                  raw_text=f"Account number: 4471-220-918 $84.12 {due.isoformat()} {due.strftime('%B %d, %Y')}")
    fields.update(changes)
    return ReaderOutput(**fields).model_dump_json()


class Caller:
    def __init__(self, first, second=None):
        self.first, self.second = first, second or first

    async def generate(self, *, system, prompt, image_jpeg, json_schema):
        if image_jpeg is None:
            return "A letter.", "fake"
        return (self.first if "Read the letter" in prompt else self.second), "fake"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_OFFLINE", "1")
    monkeypatch.setenv("TOKEN_SECRET", "test-secret-0123456789abcdef")
    monkeypatch.setattr(store, "FIXTURES_DIR", tmp_path / "fixtures")
    monkeypatch.setattr(payer, "USED_TOKENS", policy.UsedTokens())
    store.STORE.reset()
    letters.reset_merchant_cache()
    MockStore.reset()
    state = {"caller": Caller(reading_json())}

    async def fake_process(image_bytes, language):
        return await letters.process_letter(image_bytes, language, caller=state["caller"])

    monkeypatch.setattr("app.main.process_letter", fake_process)
    test_client = TestClient(app)
    test_client.state = state
    yield test_client
    store.STORE.reset()
    letters.reset_merchant_cache()


def upload(client, caller, shade) -> dict:
    client.state["caller"] = caller
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), (shade, shade, shade)).save(buffer, "JPEG")
    return client.post("/letters", data={"language": "en"},
                       files={"image": ("l.jpg", buffer.getvalue(), "image/jpeg")}).json()


def test_payable_bill_downloads_a_file_named_for_the_due_date(client):
    letter = upload(client, Caller(reading_json()), 50)
    response = client.get(f"/letters/{letter['letter_id']}/calendar.ics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "no-store" in response.headers["cache-control"]
    due = letter["proposal"]["due_date"]
    assert f'filename="guarded-mail-deadline-{due}.ics"' in response.headers["content-disposition"]
    text = response.text
    assert f"DTSTART;VALUE=DATE:{due.replace('-', '')}" in text
    assert "Pioneer Valley Electric" in text and "$84.12" in text   # trusted name and amount


def test_unknown_payee_gets_a_calendar_file_without_an_amount(client):
    letter = upload(client, Caller(reading_json(payee_candidate="Hilltop Water District")), 60)
    assert letter["proposal"]["action"] == "calendar"
    text = client.get(f"/letters/{letter['letter_id']}/calendar.ics").text
    assert "Hilltop Water District" in text and "$" not in text


def test_scam_letters_get_no_calendar_file(client):
    scam = reading_json(doc_type="scam_suspect", scam_signals=["gift_card"])
    letter = upload(client, Caller(scam), 70)
    response = client.get(f"/letters/{letter['letter_id']}/calendar.ics")
    assert response.status_code == 409 and response.json()["detail"]["error"] == "scam_flagged"


def test_letter_without_an_agreed_due_date_gets_no_file(client):
    notice = reading_json(doc_type="notice", payee_candidate="", amount_cents=0,
                          due_date=None, raw_text="Your street will be repaved.")
    letter = upload(client, Caller(notice), 80)
    response = client.get(f"/letters/{letter['letter_id']}/calendar.ics")
    assert response.status_code == 409 and response.json()["detail"]["error"] == "no_due_date"


def test_disagreeing_due_dates_get_no_file(client):
    other = datetime.now(timezone.utc).date() + timedelta(days=12)
    letter = upload(client, Caller(reading_json(), reading_json(due_date=other)), 90)
    assert client.get(f"/letters/{letter['letter_id']}/calendar.ics").status_code == 409


def test_unknown_letter_is_404(client):
    assert client.get(f"/letters/{uuid4()}/calendar.ics").status_code == 404
    assert client.get("/letters/not-a-uuid/calendar.ics").status_code == 422


def test_export_is_recorded_in_the_audit_log(client):
    letter = upload(client, Caller(reading_json()), 100)
    client.get(f"/letters/{letter['letter_id']}/calendar.ics")
    events = client.get(f"/audit?letter_id={letter['letter_id']}").json()["events"]
    exported = [e for e in events if e["event"] == "calendar_exported"]
    assert len(exported) == 1 and exported[0]["actor"] == "user"
