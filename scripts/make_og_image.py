"""Disegna web/static/og-image.png (1200x630), l'anteprima dei link condivisi (og:image).

Si lancia a mano quando cambiano logo o slogan; il PNG sta nel repo, quindi Pillow non
serve né al bot né al sito:

    pip install pillow && python scripts/make_og_image.py
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "..", "web", "static")
W, H = 1200, 630
SCALE = 2                      # disegna al doppio e riduce: bordi più puliti
# gli stessi colori di style.css
BLUE, BLUE_DARK, AMBER, WHITE = (30, 58, 138), (12, 24, 66), (245, 158, 11), (255, 255, 255)
SOFT, FG, MUTED, BORDER = (199, 210, 254), (15, 23, 42), (100, 116, 139), (226, 232, 240)
PRIMARY_SOFT, ACCENT_SOFT, ACCENT_FG = (232, 237, 251), (255, 228, 168), (146, 64, 14)

FONT_CANDIDATES = {
    "bold": ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "semibold": ["seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "regular": ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"],
}
FONT_DIRS = [r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"]

# card finte del feed: fonte, data, titolo e la parola "filtrata" da evidenziare
CARDS = [
    ("Ministero", "oggi", "Supplenze: pubblicate le nuove graduatorie provinciali", "graduatorie"),
    ("USR Lombardia", "ieri", "Immissioni in ruolo docenti: calendario delle convocazioni", "convocazioni"),
    ("USP Milano", "23 set", "Graduatorie ATA di terza fascia: elenchi definitivi", "Graduatorie"),
]


def s(v):
    return int(v * SCALE)


def font(kind, size):
    for name in FONT_CANDIDATES[kind]:
        for d in FONT_DIRS:
            path = os.path.join(d, name)
            if os.path.exists(path):
                return ImageFont.truetype(path, s(size))
    sys.exit("Nessun font trovato: installa DejaVu o lancialo da Windows")


def wrap(draw, text, f, width):
    """Spezza il testo in righe che stanno in `width` pixel."""
    lines, line = [], ""
    for word in text.split():
        probe = f"{line} {word}".strip()
        if line and draw.textlength(probe, font=f) > width:
            lines.append(line)
            line = word
        else:
            line = probe
    return lines + [line]


def glow(img, center, radius, color, alpha):
    """Alone sfumato per dare profondità allo sfondo."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cx, cy = center
    ImageDraw.Draw(layer).ellipse([s(cx - radius), s(cy - radius), s(cx + radius), s(cy + radius)], fill=color + (alpha,))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(s(radius * 0.45))))


def card(img, x, y, w, source, when, title, keyword):
    """Una notizia come appare nel feed, con la parola filtrata evidenziata; restituisce l'altezza."""
    f_title, f_meta = font("semibold", 23), font("regular", 18)
    probe = ImageDraw.Draw(img)
    lines = wrap(probe, title, f_title, s(w - 56))
    h = 70 + 32 * len(lines) + 16

    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([s(x), s(y + 10), s(x + w), s(y + h + 10)], radius=s(18), fill=(0, 0, 0, 90))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(s(14))))

    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([s(x), s(y), s(x + w), s(y + h)], radius=s(18), fill=WHITE)
    # fonte come pillola, data a destra
    tw = draw.textlength(source, font=f_meta)
    draw.rounded_rectangle([s(x + 28), s(y + 24), s(x + 28) + tw + s(24), s(y + 54)], radius=s(15), fill=PRIMARY_SOFT)
    draw.text((s(x + 40), s(y + 39)), source, font=f_meta, fill=BLUE, anchor="lm")
    draw.text((s(x + w - 28), s(y + 39)), when, font=f_meta, fill=MUTED, anchor="rm")

    ty = y + 70
    for line in lines:
        cx = s(x + 28)
        for i, word in enumerate(line.split()):
            text = word if i == 0 else " " + word
            if word.strip(":,.") == keyword:
                lead = draw.textlength(" ", font=f_title) if i else 0
                ww = draw.textlength(word, font=f_title)
                draw.rounded_rectangle([cx + lead - s(5), s(ty + 1), cx + lead + ww + s(5), s(ty + 30)], radius=s(6), fill=ACCENT_SOFT)
                draw.text((cx, s(ty)), text, font=f_title, fill=ACCENT_FG)
            else:
                draw.text((cx, s(ty)), text, font=f_title, fill=FG)
            cx += draw.textlength(text, font=f_title)
        ty += 32
    return h


def main():
    img = Image.new("RGBA", (s(W), s(H)), BLUE)
    draw = ImageDraw.Draw(img)
    # sfumatura diagonale dal blu del sito al blu scuro
    for y in range(s(H)):
        t = y / s(H)
        draw.line([(0, y), (s(W), y)], fill=tuple(int(a + (b - a) * t * 0.75) for a, b in zip(BLUE, BLUE_DARK)))
    glow(img, (980, 150), 330, (96, 130, 230), 110)
    draw = ImageDraw.Draw(img)

    # marchio in alto a sinistra
    logo = Image.open(os.path.join(STATIC, "android-chrome-512x512.png")).convert("RGBA").resize((s(64), s(64)), Image.LANCZOS)
    mask = Image.new("L", logo.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, logo.size[0] - 1, logo.size[1] - 1], radius=s(14), fill=255)
    img.paste(logo, (s(72), s(64)), mask)
    draw.rounded_rectangle([s(72), s(64), s(136), s(128)], radius=s(14), outline=SOFT, width=s(2))
    draw.text((s(156), s(96)), "School Feed Monitor", font=font("bold", 30), fill=WHITE, anchor="lm")

    # messaggio
    f_head = font("bold", 58)
    y = 178
    for line in ("Le notizie della", "scuola, filtrate", "per te."):
        draw.text((s(72), s(y)), line, font=f_head, fill=AMBER if line == "per te." else WHITE)
        y += 72
    y += 26
    for line in ("Ministero, USR e uffici provinciali:", "scegli fonti e parole, il resto arriva da sé."):
        draw.text((s(72), s(y)), line, font=font("regular", 25), fill=SOFT)
        y += 36

    # pillole in basso
    x, f = s(72), font("semibold", 19)
    for label in ("Oltre 100 fonti", "Senza registrazione", "Anche su Telegram"):
        w = draw.textlength(label, font=f)
        draw.rounded_rectangle([x, s(534), x + w + s(32), s(574)], radius=s(20), outline=SOFT, width=s(2))
        draw.text((x + s(16), s(554)), label, font=f, fill=WHITE, anchor="lm")
        x += w + s(44)

    # feed a destra: le card escono dal bordo in basso, come una lista che continua
    y = 70
    for source, when, title, keyword in CARDS:
        y += card(img, 690, y, 450, source, when, title, keyword) + 20

    out = os.path.join(STATIC, "og-image.png")
    img.convert("RGB").resize((W, H), Image.LANCZOS).save(out, optimize=True)
    print(f"scritto {os.path.normpath(out)} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
