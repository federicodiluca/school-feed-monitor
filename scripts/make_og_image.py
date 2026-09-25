"""Disegna web/static/og-image.png (1200x630), l'anteprima dei link condivisi (og:image).

Si lancia a mano quando cambiano logo o slogan; il PNG sta nel repo, quindi Pillow non
serve né al bot né al sito:

    pip install pillow && python scripts/make_og_image.py
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "..", "web", "static")
W, H = 1200, 630
SCALE = 2                      # disegna al doppio e riduce: bordi più puliti
BLUE, BLUE_DARK, AMBER, WHITE = (30, 58, 138), (15, 30, 80), (245, 158, 11), (255, 255, 255)
SOFT = (199, 210, 254)

FONT_CANDIDATES = {
    "bold": ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "regular": ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"],
}
FONT_DIRS = [r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"]


def font(kind, size):
    for name in FONT_CANDIDATES[kind]:
        for d in FONT_DIRS:
            path = os.path.join(d, name)
            if os.path.exists(path):
                return ImageFont.truetype(path, size * SCALE)
    sys.exit("Nessun font trovato: installa DejaVu o lancialo da Windows")


def main():
    img = Image.new("RGB", (W * SCALE, H * SCALE), BLUE)
    draw = ImageDraw.Draw(img)
    # sfumatura verticale leggera verso il blu scuro
    for y in range(H * SCALE):
        t = y / (H * SCALE)
        draw.line([(0, y), (W * SCALE, y)], fill=tuple(int(a + (b - a) * t * 0.6) for a, b in zip(BLUE, BLUE_DARK)))
    s = lambda v: v * SCALE    # noqa: E731

    logo = Image.open(os.path.join(STATIC, "android-chrome-512x512.png")).convert("RGBA").resize((s(150), s(150)), Image.LANCZOS)
    mask = Image.new("L", logo.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, logo.size[0] - 1, logo.size[1] - 1], radius=s(28), fill=255)
    img.paste(logo, (s(80), s(80)), mask)
    draw.rounded_rectangle([s(80), s(80), s(230), s(230)], radius=s(28), outline=SOFT, width=s(3))

    draw.text((s(260), s(95)), "School Feed", font=font("bold", 64), fill=WHITE)
    draw.text((s(260), s(165)), "Monitor", font=font("bold", 64), fill=WHITE)

    draw.text((s(80), s(300)), "Le notizie di Ministero, USR e USP", font=font("regular", 44), fill=WHITE)
    draw.text((s(80), s(360)), "filtrate per le fonti e le parole che scegli.", font=font("regular", 44), fill=SOFT)

    # pillole in basso
    x = s(80)
    for label in ("Senza registrazione", "Anche su Telegram", "Oltre 100 fonti"):
        f = font("bold", 28)
        w = draw.textlength(label, font=f)
        draw.rounded_rectangle([x, s(470), x + w + s(44), s(530)], radius=s(30), fill=AMBER)
        draw.text((x + s(22), s(482)), label, font=f, fill=BLUE_DARK)
        x += w + s(64)

    out = os.path.join(STATIC, "og-image.png")
    img.resize((W, H), Image.LANCZOS).save(out, optimize=True)
    print(f"scritto {os.path.normpath(out)} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
