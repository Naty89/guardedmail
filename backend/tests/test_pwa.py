"""The installable-app files: manifest, icons and the page tags that point to them."""

import json
import re
from pathlib import Path

from PIL import Image

PUBLIC = Path(__file__).resolve().parents[2] / "frontend" / "public"
INDEX = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def manifest() -> dict:
    return json.loads((PUBLIC / "manifest.webmanifest").read_text())


def test_manifest_has_what_phones_need_to_install_the_app():
    data = manifest()
    assert data["name"] and data["short_name"]
    assert data["display"] == "standalone"
    assert data["start_url"] == "/" and data["scope"] == "/"
    assert re.fullmatch(r"#[0-9a-f]{6}", data["theme_color"])
    assert re.fullmatch(r"#[0-9a-f]{6}", data["background_color"])


def test_manifest_icons_exist_and_match_their_declared_size():
    sizes = set()
    for icon in manifest()["icons"]:
        path = PUBLIC / icon["src"].lstrip("/")
        assert path.is_file(), icon["src"]
        width, height = Image.open(path).size
        assert f"{width}x{height}" == icon["sizes"], icon["src"]
        sizes.add((icon["sizes"], icon["purpose"]))
    # Android wants a 192 and a 512 plain icon, plus a maskable one.
    assert ("192x192", "any") in sizes and ("512x512", "any") in sizes
    assert ("512x512", "maskable") in sizes


def test_maskable_icon_keeps_its_artwork_inside_the_safe_zone():
    """Android may crop the outer 10% on every side; the corners must be plain cobalt."""
    image = Image.open(PUBLIC / "icons" / "icon-maskable-512.png").convert("RGB")
    cobalt = (29, 78, 216)
    margin = int(512 * 0.10)
    for x in range(0, 512, 8):
        for y in (0, margin - 1, 511 - margin + 1, 511):
            assert image.getpixel((x, y)) == cobalt, (x, y)


def test_apple_touch_icon_is_opaque_180_square():
    image = Image.open(PUBLIC / "icons" / "apple-touch-icon.png")
    assert image.size == (180, 180) and image.mode == "RGB"  # iOS shows transparency as black


def test_page_links_the_manifest_and_icon_and_runs_full_screen():
    html = INDEX.read_text()
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert 'rel="apple-touch-icon" href="/icons/apple-touch-icon.png"' in html
    assert 'name="apple-mobile-web-app-capable" content="yes"' in html
    assert "viewport-fit=cover" in html


def test_no_service_worker_is_registered():
    """A service worker could cache API answers (audit log, balance). We do not use one."""
    source = "\n".join(path.read_text() for path in
                       (INDEX.parent / "src").rglob("*.ts*"))
    assert "serviceWorker" not in source and "serviceWorker" not in INDEX.read_text()
