"""Pre-generate everything the demo letters need, so the demo never waits on Gemini.

Run:  cd backend && .venv/bin/python -m scripts.warm_fixtures [--refresh-explanations]

For both sample letters, in every language:
- the reader result (cached in backend/fixtures by image hash + language)
- the read-aloud audio, for languages with a voice (backend/fixtures/audio)

Anything already cached is skipped. `--refresh-explanations` rewrites only the
explanation of cached readings (one model call each), for use after the
explanation prompt has changed. Calls are spaced out to stay under the free
tier's per-minute limit; rerun the script if some items fail.
"""

import asyncio
import sys
from dataclasses import replace

from app import tts
from app.config import get_settings
from app.reader import GeminiCaller, ReaderError, explain, image_sha256, read_letter
from app.schemas import LANGUAGES, VOICE_ENABLED
from app.store import (
    FIXTURES_DIR,
    SAMPLE_IDS,
    load_cached_reading,
    sample_image_bytes,
    save_cached_reading,
)

PAUSE_S = 7.0


async def warm(refresh_explanations: bool) -> int:
    caller = GeminiCaller()
    failures = 0
    for sample_id in SAMPLE_IDS:
        image = sample_image_bytes(sample_id)
        sha = image_sha256(image)
        for language in LANGUAGES:
            label = f"{sample_id} [{language}]"
            reading = load_cached_reading(sha, language)
            try:
                if reading is None:
                    reading = await read_letter(image, language, caller)
                    save_cached_reading(reading, language, FIXTURES_DIR)
                    print(f"{label}: read ({reading.explanation_source})")
                    await asyncio.sleep(PAUSE_S)
                elif refresh_explanations:
                    text, source = await explain(caller, reading.first, language)
                    reading = replace(reading, explanation=text, explanation_source=source)
                    save_cached_reading(reading, language, FIXTURES_DIR)
                    print(f"{label}: explanation rewritten ({source})")
                    await asyncio.sleep(PAUSE_S)
                else:
                    print(f"{label}: reading already cached")
            except ReaderError as exc:
                print(f"{label}: READ FAILED ({exc})")
                failures += 1
                await asyncio.sleep(PAUSE_S * 3)
                continue

            if language in VOICE_ENABLED:
                key = tts.cache_key(reading.explanation.strip(), language,
                                    get_settings().gemini_tts_model)
                if (tts.AUDIO_DIR / f"{key}.wav").is_file():
                    print(f"{label}: audio already cached")
                    continue
                audio = await tts.get_audio(reading.explanation, language)
                if audio is None:
                    print(f"{label}: AUDIO FAILED (the browser voice will be used)")
                    failures += 1
                else:
                    print(f"{label}: audio made ({len(audio) // 1024} KB)")
                await asyncio.sleep(PAUSE_S)
    print(f"Done. {failures} item(s) failed." if failures else "Done. Everything is cached.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(warm("--refresh-explanations" in sys.argv)))
