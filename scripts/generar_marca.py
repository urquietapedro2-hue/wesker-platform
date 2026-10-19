"""Genera la identidad visual propia de WESKER y V.E.R.A.: SVG (vectorial), PNG con transparencia e icono .ico.
Todo se dibuja por código (sin imágenes de terceros). Uso:  python scripts/generar_marca.py  [--salida desktop/assets]
Requiere Pillow solo para este script (no es dependencia de la aplicación)."""
import argparse
import math
import os

from PIL import Image, ImageDraw

CIAN, VIOLETA, BLANCO, TINTA = "#38BDF8", "#A78BFA", "#E2E8F0", "#0b1220"


def _hex(c, a=255):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


# ---------------------------------------------------------------- W.E.S.K.E.R.
# Hexágono = núcleo (kernel). La «W» es una ruta con cinco nodos (enrutamiento); el nodo central es el núcleo sincronizado.
HEX = [(128, 16), (225, 72), (225, 184), (128, 240), (31, 184), (31, 72)]
HEX_INT = [(128 + (x - 128) * 0.9, 128 + (y - 128) * 0.9) for x, y in HEX]
RUTA_W = [(68, 88), (98, 172), (128, 108), (158, 172), (188, 88)]
NODO_CENTRAL = (128, 108)


def svg_wesker():
    pts = lambda p: " ".join(f"{x:.1f},{y:.1f}" for x, y in p)  # noqa: E731
    nodos = "".join(f'<circle cx="{x}" cy="{y}" r="9" fill="{CIAN}"/>' for x, y in RUTA_W if (x, y) != NODO_CENTRAL)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256" role="img" aria-label="Logo W.E.S.K.E.R.">
  <title>W.E.S.K.E.R.</title>
  <polygon points="{pts(HEX)}" fill="{TINTA}" fill-opacity="0.55" stroke="{CIAN}" stroke-width="6" stroke-linejoin="round"/>
  <polygon points="{pts(HEX_INT)}" fill="none" stroke="{CIAN}" stroke-opacity="0.35" stroke-width="2" stroke-linejoin="round"/>
  <polyline points="{pts(RUTA_W)}" fill="none" stroke="{BLANCO}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
  {nodos}
  <circle cx="128" cy="108" r="21" fill="none" stroke="{CIAN}" stroke-width="3" stroke-opacity="0.8"/>
  <circle cx="128" cy="108" r="12" fill="{BLANCO}" stroke="{CIAN}" stroke-width="4"/>
  <line x1="106" y1="206" x2="150" y2="206" stroke="{CIAN}" stroke-width="4" stroke-linecap="round" stroke-opacity="0.7"/>
</svg>
'''


def png_wesker(tam=1024):
    k = tam / 256.0
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    s = lambda p: [(x * k, y * k) for x, y in p]  # noqa: E731

    def linea(puntos, color, ancho, cierre=False):
        puntos = s(puntos) + ([s(puntos)[0]] if cierre else [])
        d.line(puntos, fill=color, width=max(1, round(ancho * k)), joint="curve")
        for x, y in puntos:  # extremos redondeados
            r = ancho * k / 2
            d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    d.polygon(s(HEX), fill=_hex(TINTA, 140))
    linea(HEX, _hex(CIAN), 6, cierre=True)
    linea(HEX_INT, _hex(CIAN, 90), 2, cierre=True)
    linea(RUTA_W, _hex(BLANCO), 9)
    for x, y in RUTA_W:
        if (x, y) != NODO_CENTRAL:
            d.ellipse([(x - 9) * k, (y - 9) * k, (x + 9) * k, (y + 9) * k], fill=_hex(CIAN))
    cx, cy = NODO_CENTRAL
    d.ellipse([(cx - 21) * k, (cy - 21) * k, (cx + 21) * k, (cy + 21) * k], outline=_hex(CIAN, 205), width=round(3 * k))
    d.ellipse([(cx - 14) * k, (cy - 14) * k, (cx + 14) * k, (cy + 14) * k], fill=_hex(CIAN))
    d.ellipse([(cx - 10) * k, (cy - 10) * k, (cx + 10) * k, (cy + 10) * k], fill=_hex(BLANCO))
    linea([(106, 206), (150, 206)], _hex(CIAN, 180), 4)
    return img


# ---------------------------------------------------------------- V.E.R.A.
# Orbe de asistente: anillo con 4 arcos (sensores), iris oscuro y barras de voz (asistencia por voz).
ARCOS = [(10, 80), (100, 170), (190, 260), (280, 350)]
BARRAS = [26, 44, 62, 84, 62, 44, 26]
ESPACIO = 15  # distancia entre barras: las de los extremos deben quedar dentro del iris (radio 62)


def _punto(r, grados):
    a = math.radians(grados)
    return 128 + r * math.cos(a), 128 + r * math.sin(a)


def svg_vera():
    arcos = ""
    for a0, a1 in ARCOS:
        (x0, y0), (x1, y1) = _punto(108, a0), _punto(108, a1)
        arcos += (f'<path d="M{x0:.1f} {y0:.1f} A108 108 0 0 1 {x1:.1f} {y1:.1f}" fill="none" stroke="{VIOLETA}" '
                  f'stroke-width="6" stroke-linecap="round"/>')
    puntos = "".join(f'<circle cx="{_punto(108, g)[0]:.1f}" cy="{_punto(108, g)[1]:.1f}" r="5" fill="{VIOLETA}"/>'
                     for g in (0, 90, 180, 270))
    barras = ""
    for i, h in enumerate(BARRAS):
        x = 128 + (i - 3) * ESPACIO - 5
        color = "#EDE9FE" if i == 3 else VIOLETA
        barras += f'<rect x="{x}" y="{128 - h / 2}" width="10" height="{h}" rx="5" fill="{color}"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256" role="img" aria-label="Logo V.E.R.A.">
  <title>V.E.R.A.</title>
  <circle cx="128" cy="128" r="86" fill="none" stroke="{VIOLETA}" stroke-opacity="0.35" stroke-width="2"/>
  <circle cx="128" cy="128" r="62" fill="#14102a" stroke="{VIOLETA}" stroke-width="3"/>
  {arcos}
  {puntos}
  {barras}
</svg>
'''


def png_vera(tam=1024):
    k = tam / 256.0
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    c = 128 * k
    d.ellipse([c - 86 * k, c - 86 * k, c + 86 * k, c + 86 * k], outline=_hex(VIOLETA, 90), width=round(2 * k))
    d.ellipse([c - 62 * k, c - 62 * k, c + 62 * k, c + 62 * k], fill=_hex("#14102a"), outline=_hex(VIOLETA), width=round(3 * k))
    for a0, a1 in ARCOS:
        d.arc([c - 108 * k, c - 108 * k, c + 108 * k, c + 108 * k], a0, a1, fill=_hex(VIOLETA), width=round(6 * k))
        for g in (a0, a1):  # extremos redondeados
            x, y = _punto(108, g)
            r = 3 * k
            d.ellipse([x * k - r, y * k - r, x * k + r, y * k + r], fill=_hex(VIOLETA))
    for g in (0, 90, 180, 270):
        x, y = _punto(108, g)
        r = 5 * k
        d.ellipse([x * k - r, y * k - r, x * k + r, y * k + r], fill=_hex(VIOLETA))
    for i, h in enumerate(BARRAS):
        x = (128 + (i - 3) * ESPACIO - 5) * k
        d.rounded_rectangle([x, (128 - h / 2) * k, x + 10 * k, (128 + h / 2) * k], radius=5 * k,
                            fill=_hex("#EDE9FE" if i == 3 else VIOLETA))
    return img


def guardar(salida):
    os.makedirs(salida, exist_ok=True)
    for nombre, svg, png in (("wesker_logo", svg_wesker(), png_wesker()), ("vera_logo", svg_vera(), png_vera())):
        with open(os.path.join(salida, f"{nombre}.svg"), "w", encoding="utf-8") as f:
            f.write(svg)
        grande = png.resize((512, 512), Image.Resampling.LANCZOS)
        grande.save(os.path.join(salida, f"{nombre}.png"), optimize=True)
        if nombre == "wesker_logo":
            tam = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
            png.resize((256, 256), Image.Resampling.LANCZOS).save(os.path.join(salida, "wesker.ico"), sizes=tam)
    return sorted(os.listdir(salida))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", default=os.path.join("desktop", "assets"))
    print("Generado en", ap.parse_args().salida, "->", guardar(ap.parse_args().salida))
