"""Genera assets/visormd.ico — cuadrado violeta con la M y la flecha de Markdown.

    python build/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "visormd.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]
ACCENT = (28, 158, 28, 255)
WHITE = (255, 255, 255, 255)
MASTER = 1024


def font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "seguisb.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_master() -> Image.Image:
    img = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, MASTER - 1, MASTER - 1], radius=int(MASTER * 0.22), fill=ACCENT)

    f = font(int(MASTER * 0.52))
    box = d.textbbox((0, 0), "M", font=f)
    d.text(((MASTER - (box[2] - box[0])) / 2 - box[0] - MASTER * 0.15,
            (MASTER - (box[3] - box[1])) / 2 - box[1] - MASTER * 0.04),
           "M", font=f, fill=WHITE)

    # flecha hacia abajo a la derecha de la M
    x, y, w = MASTER * 0.755, MASTER * 0.33, MASTER * 0.075
    d.rectangle([x - w / 2, y, x + w / 2, y + MASTER * 0.26], fill=WHITE)
    d.polygon([(x - MASTER * 0.10, y + MASTER * 0.24),
               (x + MASTER * 0.10, y + MASTER * 0.24),
               (x, y + MASTER * 0.42)], fill=WHITE)
    return img


def main() -> None:
    master = draw_master()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    master.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    master.resize((256, 256), Image.LANCZOS).save(OUT.with_suffix(".png"))
    print("icono generado:", OUT)


if __name__ == "__main__":
    main()
