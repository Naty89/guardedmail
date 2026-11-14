"""Tests for tts.py and GET /letters/{id}/audio. No network."""

import asyncio
import io
import wave
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import letters, store, tts
from app.main import app
from app.nessie_mock import MockStore
from app.schemas import VOICE_ENABLED, ReaderOutput


def wav_bytes(seconds=0.1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
        out.writeframes(b"\x00\x00" * int(24000 * seconds))
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def tts_setup(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DEMO_OFFLINE", "0")
    tts._in_flight.clear()


@pytest.fixture
def fake_model(monkeypatch):
    calls = []

    async def fake_generate(text, language, model, api_key):
        calls.append((text, language, model))
        await asyncio.sleep(0.01)
        return wav_bytes()

    monkeypatch.setattr(tts, "_generate", fake_generate)
    return calls


def test_generates_once_then_serves_from_the_cache(fake_model):
    first = asyncio.run(tts.get_audio("Pay $84.12 by November 24.", "en"))
    second = asyncio.run(tts.get_audio("Pay $84.12 by November 24.", "en"))
    assert first == second and first[:4] == b"RIFF"
    assert len(fake_model) == 1
    assert len(list(tts.AUDIO_DIR.glob("*.wav"))) == 1


def test_cache_is_per_text_and_language(fake_model):
    asyncio.run(tts.get_audio("Hola.", "es"))
    asyncio.run(tts.get_audio("Hola.", "pt"))
    asyncio.run(tts.get_audio("Hola amigo.", "es"))
    assert len(fake_model) == 3


@pytest.mark.parametrize("language", ["zh", "ar", "am"])
def test_languages_without_a_tested_voice_get_no_audio(fake_model, language):
    assert language not in VOICE_ENABLED
    assert asyncio.run(tts.get_audio("text", language)) is None
    assert fake_model == []


@pytest.mark.parametrize("text", ["", "   ", "x" * 2001])
def test_empty_or_oversized_text_gets_no_audio(fake_model, text):
    assert asyncio.run(tts.get_audio(text, "en")) is None and fake_model == []


def test_model_failure_gives_none_and_caches_nothing(monkeypatch):
    async def failing(text, language, model, api_key):
        return None

    monkeypatch.setattr(tts, "_generate", failing)
    assert asyncio.run(tts.get_audio("Hello.", "en")) is None
    assert not tts.AUDIO_DIR.exists() or list(tts.AUDIO_DIR.glob("*.wav")) == []


def test_offline_uses_the_cache_but_never_calls_the_model(fake_model, monkeypatch):
    asyncio.run(tts.get_audio("Cached line.", "en"))
    monkeypatch.setenv("DEMO_OFFLINE", "1")
    assert asyncio.run(tts.get_audio("Cached line.", "en")) is not None
    assert asyncio.run(tts.get_audio("New line.", "en")) is None
    assert len(fake_model) == 1


def test_no_api_key_means_no_audio(fake_model, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert asyncio.run(tts.get_audio("Hello.", "en")) is None and fake_model == []


def test_two_requests_at_once_share_one_model_call(fake_model):
    async def both():
        return await asyncio.gather(tts.get_audio("Same text.", "en"),
                                    tts.get_audio("Same text.", "en"))

    first, second = asyncio.run(both())
    assert first == second is not None and len(fake_model) == 1


def test_wav_check():
    assert tts._looks_like_wav(wav_bytes())
    assert not tts._looks_like_wav(b"<html>error</html>" * 10)
    assert not tts._looks_like_wav(b"")


def test_tts_source_passes_no_tools():
    source = open(tts.__file__).read()
    assert "tools=" not in source and "gemini-" not in source
    assert "nessie" not in source.lower() and "raw_text" not in source


# ------------------------------------------------------------------ route


@pytest.fixture
def client(monkeypatch, tmp_path, fake_model):
    monkeypatch.setenv("DEMO_OFFLINE", "1")          # mock bank
    monkeypatch.setenv("TOKEN_SECRET", "test-secret-0123456789abcdef")
    monkeypatch.setattr(store, "FIXTURES_DIR", tmp_path / "fixtures")
    store.STORE.reset()
    letters.reset_merchant_cache()
    MockStore.reset()
    due = datetime.now(timezone.utc).date() + timedelta(days=10)

    class Caller:
        async def generate(self, *, system, prompt, image_jpeg, json_schema):
            if image_jpeg is None:
                return "A bill for $84.12.", "fake"
            return ReaderOutput(
                doc_type="bill", payee_candidate="Pioneer Valley Electric",
                amount_cents=8412, currency="USD", due_date=due, scam_signals=[],
                confidence="high",
                raw_text=f"Account number: 4471-220-918 $84.12 {due.isoformat()}",
            ).model_dump_json(), "fake"

    async def fake_process(image_bytes, language):
        return await letters.process_letter(image_bytes, language, caller=Caller())

    monkeypatch.setattr("app.main.process_letter", fake_process)
    yield TestClient(app)
    store.STORE.reset()
    letters.reset_merchant_cache()


def upload(client, language) -> dict:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), (90, 90, 90)).save(buffer, "JPEG")
    return client.post("/letters", data={"language": language},
                       files={"image": ("l.jpg", buffer.getvalue(), "image/jpeg")}).json()


def test_audio_route_returns_wav(client, monkeypatch):
    monkeypatch.setenv("DEMO_OFFLINE", "0")
    letter = upload(client, "en")
    monkeypatch.setenv("DEMO_OFFLINE", "0")
    response = client.get(f"/letters/{letter['letter_id']}/audio")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content[:4] == b"RIFF"


def test_audio_route_returns_204_when_there_is_no_voice(client):
    letter = upload(client, "am")
    response = client.get(f"/letters/{letter['letter_id']}/audio")
    assert response.status_code == 204 and response.content == b""


def test_audio_route_unknown_letter_is_404(client):
    assert client.get("/letters/11111111-1111-1111-1111-111111111111/audio").status_code == 404
