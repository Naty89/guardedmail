"""Draw the home-screen icons for the installable app (PWA).

Run:  cd backend && .venv/bin/python -m scripts.make_app_icons

Writes PNGs into frontend/public/icons/. The artwork matches the header mark:
a yellow disc with a navy envelope on a cobalt background.

  icon-192.png, icon-512.png   rounded square, transparent corners ("any" purpose)
  icon-maskable-512.png        full square with the artwork inside the centre 80%,
                               so Android can crop it to any shape
  apple-touch-icon.png         180x180 full square (iOS rounds the corners itself)
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "icons"
COBALT = (29, 78, 216)
YELLOW = (255, 201, 51)
INK = (18, 27, 56)
SIZE = 2048  # draw large, then shrink for smooth edges


def artwork(scale: float) -> Image.Image:
    """The yellow disc and envelope on cobalt, with the disc `scale` of the canvas wide."""
    image = Image.new("RGBA", (SIZE, SIZE), COBALT + (255,))
    draw = ImageDraw.Draw(image)
    centre = SIZE / 2
    radius = SIZE * scale / 2
    draw.ellipse([centre - radius, centre - radius, centre + radius, centre + radius], fill=YELLOW)

    # Envelope: outline of a rounded rectangle plus the V of the flap.
    width, height = SIZE * scale * 0.50, SIZE * scale * 0.36
    left, top = centre - width / 2, centre - height / 2
    stroke = int(SIZE * scale * 0.04)
    draw.rounded_rectangle([left, top, left + width, top + height],
                           radius=SIZE * scale * 0.05, outline=INK, width=stroke)
    flap = [(left + stroke * 0.6, top + stroke * 0.9), (centre, top + height * 0.58),
            (left + width - stroke * 0.6, top + stroke * 0.9)]
    draw.line(flap, fill=INK, width=stroke, joint="curve")
    return image


def rounded(image: Image.Image) -> Image.Image:
    """Cut the corners off, leaving them transparent."""
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE, SIZE], radius=SIZE * 0.22, fill=255)
    cut = image.copy()
    cut.putalpha(mask)
    return cut


def save(image: Image.Image, name: str, size: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    image.resize((size, size), Image.LANCZOS).save(OUT / name, optimize=True)
    print(f"  {name} ({size}x{size})")


def main() -> None:
    full = artwork(scale=0.66)       # fills the icon on iOS and the plain icons
    safe = artwork(scale=0.56)       # smaller disc, inside Android's 80% safe zone
    save(rounded(full), "icon-512.png", 512)
    save(rounded(full), "icon-192.png", 192)
    save(safe, "icon-maskable-512.png", 512)
    save(full.convert("RGB"), "apple-touch-icon.png", 180)
    print(f"wrote icons to {OUT}")


if __name__ == "__main__":
    main()
