"""Read-aloud: turn an explanation into speech, and cache the audio.

- Only languages in VOICE_ENABLED get generated speech. For the others, and
  whenever generation fails, `get_audio` returns None, the API answers 204,
  and the browser falls back to its own built-in voice.
- Audio is cached on disk by a hash of (text, language, model, voice), so the
  same explanation is only ever generated once. Cached audio also works with
  DEMO_OFFLINE=1.
- The speech model has no tools. Its input is the explanation text, which the
  user can already read on screen.

Checked live (2026-11): speech needs API version "v1alpha"; the default
version rejects `speech_config`. The answer is a WAV file (24 kHz, mono).
"""

import asyncio
import hashlib
from pathlib import Path

from app.schemas import LANGUAGES, VOICE_ENABLED

AUDIO_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "audio"
VOICE_NAME = "Kore"
TTS_API_VERSION = "v1alpha"
TTS_TIMEOUT_S = 25.0   # speech takes longer than text: about 5s for 17s of audio
TTS_TRIES = 2
MAX_TTS_CHARS = 2000

# Speech being generated right now, so two requests for the same audio share one call.
_in_flight: dict[str, asyncio.Task] = {}


def cache_key(text: str, language: str, model: str) -> str:
    material = "\n".join([text, language, model, VOICE_NAME])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return AUDIO_DIR / f"{key}.wav"


def _looks_like_wav(data: bytes) -> bool:
    return len(data) > 44 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


async def _generate(text: str, language: str, model: str, api_key: str) -> bytes | None:
    """One round of calls to the speech model. Returns WAV bytes or None."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
        api_version=TTS_API_VERSION, timeout=int(TTS_TIMEOUT_S * 1000)))
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            language_code=LANGUAGES[language][1],
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME))),
    )
    for attempt in range(TTS_TRIES):
        if attempt:
            await asyncio.sleep(1.5)
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(model=model, contents=text, config=config),
                timeout=TTS_TIMEOUT_S)
            data = response.candidates[0].content.parts[0].inline_data.data
            if isinstance(data, bytes) and _looks_like_wav(data):
                return data
        except Exception:
            continue  # timeout, quota, overload: try once more, then give up
    return None


async def get_audio(text: str, language: str) -> bytes | None:
    """WAV bytes for this text, from the cache or freshly generated. None = no audio."""
    from app.config import get_settings

    text = text.strip()
    if language not in VOICE_ENABLED or not text or len(text) > MAX_TTS_CHARS:
        return None
    settings = get_settings()
    key = cache_key(text, language, settings.gemini_tts_model)
    path = _cache_path(key)
    if path.is_file():
        return path.read_bytes()
    if settings.demo_offline or not settings.gemini_api_key:
        return None

    task = _in_flight.get(key)
    if task is None:
        task = asyncio.create_task(
            _generate(text, language, settings.gemini_tts_model, settings.gemini_api_key))
        _in_flight[key] = task
        task.add_done_callback(lambda _: _in_flight.pop(key, None))
    audio = await asyncio.shield(task)
    if audio is not None:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
    return audio


def warm_up(text: str, language: str) -> None:
    """Start generating in the background so Play responds quickly later."""
    if language not in VOICE_ENABLED:
        return
    task = asyncio.ensure_future(get_audio(text, language))
    task.add_done_callback(lambda finished: finished.exception())  # never raise unhandled
