"""Tests for PDF uploads: the server renders each PDF page to an image. No network."""

import io
from datetime import datetime, timedelta, timezone

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import letters, payer, policy, reader, store
from app.main import app
from app.nessie_mock import MockStore
from app.reader import LONG_EDGE_PX, MAX_PAGES, ReaderError, as_pages
from app.schemas import ReaderOutput

DUE = datetime.now(timezone.utc).date() + timedelta(days=10)


def pdf(page_count=1, width=612, height=792) -> bytes:
    """A real, minimal PDF with `page_count` blank pages."""
    doc = pdfium.PdfDocument.new()
    for _ in range(page_count):
        doc.new_page(width, height)
    buffer = io.BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


def photo(width=300, height=200, shade=120) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (shade, shade, shade)).save(buffer, "JPEG")
    return buffer.getvalue()


def reading() -> ReaderOutput:
    return ReaderOutput(
        doc_type="bill", payee_candidate="Pioneer Valley Electric", amount_cents=8412,
        currency="USD", due_date=DUE, scam_signals=[], confidence="high",
        raw_text=f"Account number: 4471-220-918. TOTAL $84.12 due {DUE.isoformat()}")


class BillCaller:
    """Reads whatever images it is given as the same electric bill."""

    def __init__(self):
        self.calls = []

    async def generate(self, *, system, prompt, image_jpeg, json_schema, extra_images=None):
        self.calls.append({"image": image_jpeg, "extra": extra_images,
                           "has_schema": json_schema is not None})
        if image_jpeg is None:
            return "A bill for $84.12.", "fake"
        return reading().model_dump_json(), "fake"


# ------------------------------------------------------------ pdf expansion


def test_a_pdf_becomes_one_jpeg_per_page():
    pages = as_pages(pdf(2))
    assert len(pages) == 2
    for page in pages:
        assert Image.open(io.BytesIO(page)).format == "JPEG"


def test_a_single_page_pdf_stays_a_single_page():
    assert len(as_pages(pdf(1))) == 1


def test_rendered_pages_are_at_most_the_reader_long_edge():
    (page,) = as_pages(pdf(1))
    assert max(Image.open(io.BytesIO(page)).size) == LONG_EDGE_PX


def test_a_pdf_with_too_many_pages_is_refused():
    with pytest.raises(ReaderError) as error:
        as_pages(pdf(MAX_PAGES + 1))
    assert error.value.reason == "too_many_pages"


def test_pdf_pages_and_photos_count_together_towards_the_limit():
    assert len(as_pages([pdf(MAX_PAGES - 1), photo()])) == MAX_PAGES
    with pytest.raises(ReaderError) as error:
        as_pages([pdf(MAX_PAGES - 1), photo(), photo()])
    assert error.value.reason == "too_many_pages"


def test_a_broken_pdf_is_refused():
    with pytest.raises(ReaderError) as error:
        as_pages(b"%PDF-1.7 but not really a pdf")
    assert error.value.reason == "image_unreadable"


def test_an_oversized_pdf_is_refused(monkeypatch):
    monkeypatch.setattr(reader, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(ReaderError) as error:
        as_pages(pdf(1))
    assert error.value.reason == "image_too_large"


def test_photos_are_left_untouched_by_the_pdf_check():
    page = photo()
    assert as_pages(page) == [page]


# -------------------------------------------------------------------- routes


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_OFFLINE", "1")
    monkeypatch.setenv("TOKEN_SECRET", "test-secret-0123456789abcdef")
    monkeypatch.setattr(store, "FIXTURES_DIR", tmp_path / "fixtures")
    monkeypatch.setattr(payer, "USED_TOKENS", policy.UsedTokens())
    store.STORE.reset()
    letters.reset_merchant_cache()
    MockStore.reset()
    caller = BillCaller()

    async def fake_process(image_bytes, language):
        return await letters.process_letter(image_bytes, language, caller=caller)

    monkeypatch.setattr("app.main.process_letter", fake_process)
    test_client = TestClient(app)
    test_client.caller = caller
    yield test_client
    store.STORE.reset()
    letters.reset_merchant_cache()


def post_pdf(client, data, filename="letter.pdf"):
    return client.post("/letters", data={"language": "en"},
                       files={"image": (filename, data, "application/pdf")})


def test_a_pdf_upload_is_read_like_a_photo_letter(client):
    response = post_pdf(client, pdf(2))
    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["action"] == "pay" and body["proposal"]["amount_cents"] == 8412
    assert body["summary"]["sender"] == "Pioneer Valley Electric"
    # Both pages reached the extraction calls as images.
    extractions = [c for c in client.caller.calls if c["has_schema"]]
    assert len(extractions) == 2 and len(extractions[0]["extra"]) == 1


def test_the_letter_gets_a_thumbnail_from_the_first_pdf_page(client):
    letter = post_pdf(client, pdf(1)).json()
    thumb = client.get(f"/letters/{letter['letter_id']}/image")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"


def test_the_same_pdf_twice_is_served_from_the_cache(client):
    data = pdf(1)
    post_pdf(client, data)
    calls_after_first = len(client.caller.calls)
    post_pdf(client, data)
    assert len(client.caller.calls) == calls_after_first


def test_a_five_page_pdf_is_a_400_and_nothing_is_read(client):
    response = post_pdf(client, pdf(MAX_PAGES + 1))
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "too_many_pages"
    assert client.caller.calls == []


def test_a_broken_pdf_is_a_400(client):
    response = post_pdf(client, b"%PDF-1.7 but not really a pdf")
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "image_unreadable"
    assert client.caller.calls == []


def test_a_pdf_and_a_photo_can_be_uploaded_together(client):
    response = client.post("/letters", data={"language": "en"}, files=[
        ("image", ("letter.pdf", pdf(1), "application/pdf")),
        ("image", ("page2.jpg", photo(), "image/jpeg")),
    ])
    assert response.status_code == 200
