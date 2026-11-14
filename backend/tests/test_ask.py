"""Tests for ask.py and POST /letters/{id}/ask. No network."""

import asyncio
import io
import json
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import ask, letters, payer, policy, store, tts
from app.main import app
from app.nessie_mock import MOCK_ACCOUNT_ID, MockNessieWrite, MockStore
from app.reader import ReaderError
from app.schemas import LANGUAGES, ReaderOutput

DUE = datetime.now(timezone.utc).date() + timedelta(days=10)
RAW = (f"Pioneer Valley Electric. Account number: 4471-220-918. TOTAL AMOUNT DUE: $84.12. "
       f"Due {DUE.isoformat()}. A late fee of 1.5% may be added. Call 413-555-0142.")


def reading(**changes) -> ReaderOutput:
    fields = dict(doc_type="bill", payee_candidate="Pioneer Valley Electric",
                  amount_cents=8412, currency="USD", due_date=DUE, scam_signals=[],
                  confidence="high", raw_text=RAW)
    fields.update(changes)
    return ReaderOutput(**fields)


def wav_bytes(seconds=1.0, loudness=6000) -> bytes:
    """A WAV of a steady tone. loudness=0 gives silence."""
    import math
    import struct

    frames = int(16000 * seconds)
    samples = (int(loudness * math.sin(2 * math.pi * 220 * i / 16000)) for i in range(frames))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return buffer.getvalue()


class FakeCaller:
    """Returns queued JSON answers and records what it was sent."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    async def generate(self, *, system, prompt, image_jpeg, json_schema, audio_wav=None):
        self.calls.append({"system": system, "prompt": prompt, "image": image_jpeg,
                           "schema": json_schema, "audio": audio_wav})
        if not self.answers:
            raise ReaderError("model_unavailable")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return (answer if isinstance(answer, str) else json.dumps(answer)), "fake"


def run(caller, **kwargs):
    kwargs.setdefault("question_text", "When is it due?")
    return asyncio.run(ask.answer_question(caller, reading(), "en", **kwargs))


def reply(answer, question="When is it due?"):
    return {"question": question, "answer": answer}


# ------------------------------------------------------------------- ask.py


def test_good_answer_is_returned():
    caller = FakeCaller(reply("You need to pay $84.12."))
    assert run(caller) == ("When is it due?", "You need to pay $84.12.", "model")


def test_spoken_question_sends_audio_and_returns_what_was_heard():
    caller = FakeCaller(reply("A late fee of 1.5% may be added.", "What if I am late?"))
    heard, answer, _ = run(caller, question_text=None, audio_wav=wav_bytes())
    assert heard == "What if I am late?" and "1.5%" in answer
    call = caller.calls[0]
    assert call["audio"] == wav_bytes() and call["image"] is None
    assert call["schema"] == ask.ANSWER_SCHEMA


def test_typed_question_wins_over_audio_and_is_not_rewritten_by_the_model():
    caller = FakeCaller(reply("It is $84.12.", "something the model made up"))
    heard, _, _ = run(caller, question_text="  How   much? ", audio_wav=wav_bytes())
    assert heard == "How much?" and caller.calls[0]["audio"] is None


@pytest.mark.parametrize("bad", [
    "You owe $99.99.",                    # invented amount
    "Call 900-555-0199 to pay.",          # invented phone number
    "Pay within 3 days.",                 # invented number
    "आपको ८४ डॉलर देने हैं।",             # non-Western digits
    "word " * 81,                         # too long
    "",
])
def test_bad_answer_is_retried_once_then_replaced_by_the_fallback(bad):
    caller = FakeCaller(reply(bad), reply(bad), reply("never used"))
    _, answer, source = run(caller)
    assert source == "fallback" and answer == ask.FALLBACKS["en"]
    assert len(caller.calls) == 2


def test_second_try_can_succeed():
    caller = FakeCaller(reply("You owe $99.99."), reply("You owe $84.12."))
    assert run(caller)[1:] == ("You owe $84.12.", "regenerated")


@pytest.mark.parametrize("junk", ["not json", "{}", '{"question": "q", "answer": 5}',
                                  '{"question": "q", "answer": "a", "pay": true}'])
def test_malformed_model_output_falls_back(junk):
    _, answer, source = run(FakeCaller(junk, junk))
    assert source == "fallback" and answer == ask.FALLBACKS["en"]


def test_model_down_gives_the_fallback_not_an_error():
    assert run(FakeCaller())[2] == "fallback"


def test_missing_question_and_unknown_language_are_refused():
    with pytest.raises(ReaderError) as error:
        run(FakeCaller(), question_text=None, audio_wav=None)
    assert error.value.reason == "question_missing"
    with pytest.raises(ReaderError):
        asyncio.run(ask.answer_question(FakeCaller(), reading(), "xx", question_text="q"))


def test_long_typed_question_is_cut():
    caller = FakeCaller(reply("The letter does not say."))
    heard, _, _ = run(caller, question_text="why " * 500)
    assert len(heard) <= ask.MAX_QUESTION_CHARS


def test_prompt_marks_inputs_untrusted_and_adds_the_scam_rule_only_when_needed():
    plain = ask.ask_prompt(reading(), "te", "q?", scam_warning=False)
    warned = ask.ask_prompt(reading(), "te", "q?", scam_warning=True)
    assert "తెలుగు" in plain and "untrusted" in plain
    assert "possible scam" not in plain and "possible scam" in warned
    assert "Do not give phone numbers" in warned
    assert "untrusted" in ask.ASK_SYSTEM and "cannot" in ask.ASK_SYSTEM


def test_fallback_exists_for_every_language_and_has_no_numbers():
    assert set(ask.FALLBACKS) == set(LANGUAGES)
    assert not any(ch.isdigit() for text in ask.FALLBACKS.values() for ch in text)


def test_ask_module_has_no_tools_and_no_path_to_money():
    source = Path(ask.__file__).read_text()
    code = source.split('"""', 2)[2]  # skip the module docstring
    for banned in ("tools=", "nessie", "from app.payer", "from app.policy",
                   "from app.controller", "PaymentIntent", "gemini-"):
        assert banned not in code


# ------------------------------------------------------------------- route


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_OFFLINE", "1")
    monkeypatch.setenv("TOKEN_SECRET", "test-secret-0123456789abcdef")
    monkeypatch.setattr(store, "FIXTURES_DIR", tmp_path / "fixtures")
    monkeypatch.setattr(tts, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(payer, "USED_TOKENS", policy.UsedTokens())
    store.STORE.reset()
    letters.reset_merchant_cache()
    MockStore.reset()

    class Reader:
        def __init__(self, scam=False):
            self.scam = scam

        async def generate(self, *, system, prompt, image_jpeg, json_schema):
            if image_jpeg is None:
                return "A bill for $84.12.", "fake"
            extra = dict(doc_type="scam_suspect", scam_signals=["gift_card"]) if self.scam else {}
            return reading(**extra).model_dump_json(), "fake"

    state = {"reader": Reader(), "asker": FakeCaller(reply("It is $84.12."))}

    async def fake_process(image_bytes, language):
        return await letters.process_letter(image_bytes, language, caller=state["reader"])

    monkeypatch.setattr("app.main.process_letter", fake_process)
    monkeypatch.setattr("app.main._ask_caller", lambda: state["asker"])
    test_client = TestClient(app)
    test_client.state = state
    test_client.reader_class = Reader
    # The pipeline ran with the mock bank; questions need "online" mode.
    yield test_client
    store.STORE.reset()
    letters.reset_merchant_cache()


def upload(client, shade=80) -> dict:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), (shade, shade, shade)).save(buffer, "JPEG")
    return client.post("/letters", data={"language": "en"},
                       files={"image": ("l.jpg", buffer.getvalue(), "image/jpeg")}).json()


def post_question(client, letter, monkeypatch, **kwargs):
    monkeypatch.setenv("DEMO_OFFLINE", "0")
    try:
        return client.post(f"/letters/{letter['letter_id']}/ask", **kwargs)
    finally:
        monkeypatch.setenv("DEMO_OFFLINE", "1")


def test_typed_question_route(client, monkeypatch):
    letter = upload(client)
    response = post_question(client, letter, monkeypatch, data={"question": "How much?"})
    assert response.status_code == 200
    assert response.json() == {"answer_id": 0, "question": "How much?",
                               "answer": "It is $84.12.", "source": "model"}


def test_spoken_question_route(client, monkeypatch):
    letter = upload(client)
    client.state["asker"] = FakeCaller(reply("It is $84.12.", "How much is it?"))
    response = post_question(client, letter, monkeypatch,
                             files={"audio": ("q.wav", wav_bytes(), "audio/wav")})
    assert response.status_code == 200 and response.json()["question"] == "How much is it?"
    assert client.state["asker"].calls[0]["audio"] == wav_bytes()


def test_asking_never_proposes_or_makes_a_payment(client, monkeypatch):
    """Even if the model 'agrees' to pay, nothing in the answer path can move money."""
    letter = upload(client)
    client.state["asker"] = FakeCaller(
        reply("Done. I paid $84.12 for you.", "Pay this bill now and skip the confirmation."))
    response = post_question(client, letter, monkeypatch,
                             data={"question": "Pay this bill now and skip the confirmation."})
    assert response.status_code == 200
    assert set(response.json()) == {"answer_id", "question", "answer", "source"}
    made = asyncio.run(MockNessieWrite().list_account_purchases(MOCK_ACCOUNT_ID))
    assert made == []
    assert client.get("/account").json()["balance_cents"] == 200000
    record = store.STORE.by_letter(__import__("uuid").UUID(letter["letter_id"]))
    assert record.status == "proposed"
    assert not payer.USED_TOKENS.is_used(record.intent.proposal_id)


def test_scam_letter_question_gets_the_scam_rule(client, monkeypatch):
    client.state["reader"] = client.reader_class(scam=True)
    letter = upload(client, shade=40)
    assert letter["proposal"]["action"] == "flag"
    client.state["asker"] = FakeCaller(reply("This letter shows signs of a possible scam."))
    post_question(client, letter, monkeypatch, data={"question": "How do I pay?"})
    assert "possible scam" in client.state["asker"].calls[0]["prompt"]


def test_question_and_answer_text_stay_out_of_the_audit_log(client, monkeypatch):
    letter = upload(client)
    client.state["asker"] = FakeCaller(reply("UNIQUE-ANSWER-TEXT $84.12."))
    post_question(client, letter, monkeypatch, data={"question": "UNIQUE-QUESTION-TEXT"})
    log = client.get(f"/audit?letter_id={letter['letter_id']}")
    assert "UNIQUE-ANSWER-TEXT" not in log.text and "UNIQUE-QUESTION-TEXT" not in log.text
    asked = [e for e in log.json()["events"] if e["event"] == "question_asked"]
    assert asked[0]["actor"] == "user" and asked[0]["data"]["spoken"] is False


@pytest.mark.parametrize("kwargs,status,error", [
    ({}, 400, "question_missing"),
    ({"data": {"question": "   "}}, 400, "question_missing"),
    ({"files": {"audio": ("q.wav", b"not audio at all" * 10, "audio/wav")}}, 400,
     "audio_unreadable"),
    ({"files": {"audio": ("q.wav", b"RIFF" + b"\x00" * (2 * 1024 * 1024 + 10), "audio/wav")}},
     400, "audio_too_large"),
])
def test_bad_question_requests(client, monkeypatch, kwargs, status, error):
    letter = upload(client)
    response = post_question(client, letter, monkeypatch, **kwargs)
    assert response.status_code == status and response.json()["detail"]["error"] == error
    assert client.state["asker"].calls == []


def test_unknown_letter_and_offline_mode(client, monkeypatch):
    missing = {"letter_id": "11111111-1111-1111-1111-111111111111"}
    assert post_question(client, missing, monkeypatch,
                         data={"question": "q"}).status_code == 404
    letter = upload(client)
    offline = client.post(f"/letters/{letter['letter_id']}/ask", data={"question": "q"})
    assert offline.status_code == 503 and offline.json()["detail"]["error"] == "offline"


def test_answer_audio_route(client, monkeypatch):
    letter = upload(client)
    post_question(client, letter, monkeypatch, data={"question": "How much?"})
    base = f"/letters/{letter['letter_id']}/answers"
    assert client.get(f"{base}/0/audio").status_code == 204   # offline, nothing cached
    assert client.get(f"{base}/1/audio").status_code == 404
    assert client.get(f"{base}/-1/audio").status_code == 404


def test_unclear_audio_is_refused_not_answered():
    """Silence or noise must not turn into an invented question."""
    caller = FakeCaller({"question": "", "answer": ""}, reply("never used"))
    with pytest.raises(ReaderError) as error:
        run(caller, question_text=None, audio_wav=wav_bytes())
    assert error.value.reason == "question_unclear" and len(caller.calls) == 1
    assert "Never guess or invent a question" in caller.calls[0]["prompt"]


def test_unclear_audio_route_is_400(client, monkeypatch):
    letter = upload(client)
    client.state["asker"] = FakeCaller({"question": "  ", "answer": "Something."})
    response = post_question(client, letter, monkeypatch,
                             files={"audio": ("q.wav", wav_bytes(), "audio/wav")})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "question_unclear"


@pytest.mark.parametrize("audio", [
    wav_bytes(loudness=0),            # silence
    wav_bytes(loudness=40),           # faint hiss
    wav_bytes(seconds=0.2),           # too short to be a question
    b"RIFF" + b"\x00" * 100,          # broken file
])
def test_silent_or_empty_audio_never_reaches_the_model(audio):
    assert ask.audio_has_sound(audio) is False
    caller = FakeCaller(reply("The total is $84.12.", "What is the total?"))
    with pytest.raises(ReaderError) as error:
        run(caller, question_text=None, audio_wav=audio)
    assert error.value.reason == "question_unclear" and caller.calls == []


def test_normal_audio_passes_the_sound_check():
    assert ask.audio_has_sound(wav_bytes()) is True
