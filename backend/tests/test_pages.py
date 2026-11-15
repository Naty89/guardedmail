"""Tests for letters photographed in several pages. No network."""

import asyncio
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import audit, letters, payer, policy, reader, store
from app.main import app
from app.nessie_mock import MockStore
from app.reader import MAX_PAGES, ReaderError, as_pages, image_sha256, pages_sha256, read_letter
from app.schemas import ReaderOutput

DUE = datetime.now(timezone.utc).date() + timedelta(days=10)


def photo(width=300, height=200, shade=120) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (shade, shade, shade)).save(buffer, "JPEG")
    return buffer.getvalue()


def reading(**changes) -> ReaderOutput:
    fields = dict(doc_type="bill", payee_candidate="Pioneer Valley Electric", amount_cents=8412,
                  currency="USD", due_date=DUE, scam_signals=[], confidence="high",
                  raw_text=f"Account number: 4471-220-918. TOTAL $84.12 due {DUE.isoformat()}")
    fields.update(changes)
    return ReaderOutput(**fields)


class PageCaller:
    """Records what it is sent. Only returns the bill when it was given BOTH pages,
    like a letter whose amount sits on page 2."""

    def __init__(self):
        self.calls = []

    async def generate(self, *, system, prompt, image_jpeg, json_schema, extra_images=None):
        self.calls.append({"prompt": prompt, "image": image_jpeg, "extra": extra_images,
                           "has_schema": json_schema is not None})
        if image_jpeg is None:
            return "A bill for $84.12.", "fake"
        if extra_images:
            return reading().model_dump_json(), "fake"
        return reading(doc_type="other", payee_candidate="", amount_cents=0, due_date=None,
                       raw_text="Dear customer, please see the next page.").model_dump_json(), "fake"


# -------------------------------------------------------------------- hashing


def test_one_page_keeps_its_plain_hash_so_old_caches_still_match():
    page = photo()
    assert pages_sha256([page]) == image_sha256(page)


def test_several_pages_hash_together_and_order_matters():
    a, b = photo(shade=50), photo(shade=200)
    assert pages_sha256([a, b]) == pages_sha256([a, b])
    assert pages_sha256([a, b]) != pages_sha256([b, a])
    assert pages_sha256([a, b]) not in (image_sha256(a), image_sha256(b))
    assert pages_sha256([a, b]) != pages_sha256([a, b, a])


def test_as_pages_accepts_one_image_or_a_list_and_enforces_the_limit():
    page = photo()
    assert as_pages(page) == [page] and as_pages([page, page]) == [page, page]
    with pytest.raises(ReaderError) as empty:
        as_pages([])
    assert empty.value.reason == "image_empty"
    with pytest.raises(ReaderError) as many:
        as_pages([page] * (MAX_PAGES + 1))
    assert many.value.reason == "too_many_pages"
    assert as_pages([page] * MAX_PAGES)


# --------------------------------------------------------------- the reader


def test_every_page_is_sent_to_both_extraction_calls_in_order():
    first_page, second_page = photo(400, 300), photo(200, 500)
    caller = PageCaller()
    result = asyncio.run(read_letter([first_page, second_page], "en", caller))
    extractions = [c for c in caller.calls if c["has_schema"]]
    assert len(extractions) == 2
    for call in extractions:
        assert len(call["extra"]) == 1                      # page 2 rode along
        assert Image.open(io.BytesIO(call["image"])).size == (400, 300)   # page 1 first
        assert Image.open(io.BytesIO(call["extra"][0])).size == (200, 500)  # then page 2
        assert "2 pages" in call["prompt"] and "ONE letter" in call["prompt"]
    assert result.first.amount_cents == 8412            # found on "page 2"
    assert result.evidence_ok is True
    assert result.image_sha256 == pages_sha256([first_page, second_page])


def test_the_explanation_call_gets_no_images_at_all():
    caller = PageCaller()
    asyncio.run(read_letter([photo(), photo(shade=30)], "en", caller))
    explanation = [c for c in caller.calls if not c["has_schema"]]
    assert len(explanation) == 1
    assert explanation[0]["image"] is None and explanation[0]["extra"] is None


def test_a_single_page_is_read_exactly_as_before():
    """No extra_images keyword and no page note, so simple callers keep working."""
    seen = []

    class OldStyleCaller:
        async def generate(self, *, system, prompt, image_jpeg, json_schema):
            seen.append(prompt)
            return (reading().model_dump_json() if image_jpeg else "A bill."), "fake"

    result = asyncio.run(read_letter(photo(), "en", OldStyleCaller()))
    assert result.first.amount_cents == 8412
    assert not any("pages" in prompt for prompt in seen if "Field rules" in prompt)


def test_too_many_pages_fail_before_any_model_call():
    caller = PageCaller()
    with pytest.raises(ReaderError) as error:
        asyncio.run(read_letter([photo()] * (MAX_PAGES + 1), "en", caller))
    assert error.value.reason == "too_many_pages" and caller.calls == []


def test_a_bad_page_in_the_middle_is_refused():
    caller = PageCaller()
    with pytest.raises(ReaderError) as error:
        asyncio.run(read_letter([photo(), b"not an image", photo()], "en", caller))
    assert error.value.reason == "image_unreadable" and caller.calls == []


# ------------------------------------------------- policy rules do not change


def test_two_page_letters_still_need_both_readings_to_agree():
    class Disagreeing(PageCaller):
        n = 0

        async def generate(self, *, system, prompt, image_jpeg, json_schema, extra_images=None):
            if image_jpeg is None:
                return "A bill.", "fake"
            Disagreeing.n += 1
            amount = 8412 if Disagreeing.n % 2 else 8421
            return reading(amount_cents=amount,
                           raw_text="$84.12 $84.21 " + DUE.isoformat()).model_dump_json(), "fake"

    result = asyncio.run(read_letter([photo(), photo(shade=40)], "en", Disagreeing()))
    assert result.first.amount_cents != result.second.amount_cents   # policy will block this


# --------------------------------------------------------------------- routes


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_OFFLINE", "1")
    monkeypatch.setenv("TOKEN_SECRET", "test-secret-0123456789abcdef")
    monkeypatch.setattr(store, "FIXTURES_DIR", tmp_path / "fixtures")
    monkeypatch.setattr(payer, "USED_TOKENS", policy.UsedTokens())
    store.STORE.reset()
    letters.reset_merchant_cache()
    MockStore.reset()
    caller = PageCaller()

    async def fake_process(image_bytes, language):
        return await letters.process_letter(image_bytes, language, caller=caller)

    monkeypatch.setattr("app.main.process_letter", fake_process)
    test_client = TestClient(app)
    test_client.caller = caller
    yield test_client
    store.STORE.reset()
    letters.reset_merchant_cache()


def post_pages(client, *pages, language="en"):
    files = [("image", (f"page{i}.jpg", page, "image/jpeg")) for i, page in enumerate(pages)]
    return client.post("/letters", data={"language": language}, files=files)


def test_two_pages_upload_gives_one_letter_with_the_amount_from_page_two(client):
    response = post_pages(client, photo(400, 300), photo(200, 500))
    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["action"] == "pay" and body["proposal"]["amount_cents"] == 8412
    assert body["summary"]["sender"] == "Pioneer Valley Electric"


def test_the_picture_shown_for_the_letter_is_page_one(client):
    letter = post_pages(client, photo(600, 300), photo(200, 800)).json()
    thumb = client.get(f"/letters/{letter['letter_id']}/image")
    width, height = Image.open(io.BytesIO(thumb.content)).size
    assert width > height   # page 1 is landscape; page 2 would be portrait


def test_five_pages_are_refused(client):
    response = post_pages(client, *[photo()] * 5)
    assert response.status_code == 400 and response.json()["detail"]["error"] == "too_many_pages"
    assert client.caller.calls == []


def test_exactly_four_pages_are_accepted(client):
    assert post_pages(client, *[photo(shade=40 + 40 * i) for i in range(4)]).status_code == 200


def test_a_bad_page_is_a_400_and_nothing_is_read(client):
    response = post_pages(client, photo(), b"not an image")
    assert response.status_code == 400 and response.json()["detail"]["error"] == "image_unreadable"
    assert client.caller.calls == []


def test_one_page_still_works_the_old_way(client):
    assert client.post("/letters", data={"language": "en"},
                       files={"image": ("l.jpg", photo(), "image/jpeg")}).status_code == 200


def test_same_pages_are_cached_but_a_different_order_is_a_new_read(client):
    a, b = photo(300, 200, 50), photo(200, 300, 200)
    post_pages(client, a, b)
    reads_after_first = len(client.caller.calls)
    post_pages(client, a, b)
    assert len(client.caller.calls) == reads_after_first          # cached: no new model calls
    post_pages(client, b, a)
    assert len(client.caller.calls) > reads_after_first           # swapped order: read again


def test_multi_page_letters_can_be_reopened_from_history(client):
    letter = post_pages(client, photo(300, 200, 50), photo(200, 300, 200)).json()
    calls = len(client.caller.calls)
    reopened = client.post(f"/history/{letter['letter_id']}/open")
    assert reopened.status_code == 200 and len(client.caller.calls) == calls
    assert reopened.json()["summary"]["amount_cents"] == 8412
