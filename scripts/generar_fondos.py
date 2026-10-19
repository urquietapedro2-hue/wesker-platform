"""Genera los fondos propios de WESKER: metal oscuro cepillado + marco HUD, sin textos ni logos incrustados
(los logos los coloca la aplicación). Cada pantalla usa un color de acento distinto.
Uso:  python scripts/generar_fondos.py [--salida desktop/assets/fondos]    (solo requiere Pillow)"""
import argparse
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

# nombre del archivo -> color de acento (mismos nombres que el proyecto original, para mapearlos fácil)
FONDOS = {
    "background": (56, 189, 248),            # inicio de sesión: cian
    "background_dashboard": (56, 189, 248),  # principal: cian
    "background_diag": (74, 222, 128),       # diagnóstico: verde
    "background_estop": (248, 113, 113),     # paro de emergencia: rojo
    "background_manual": (251, 191, 36),     # control manual: ámbar
    "background_zeno": (167, 139, 250),      # Zeno: violeta
}


def metal(w, h, semilla):
    """Fondo base: luz suave en el centro, viñeta en las esquinas y vetas horizontales de metal cepillado."""
    oscuro, claro = Image.new("RGB", (w, h), (10, 13, 18)), Image.new("RGB", (w, h), (44, 50, 60))
    centro = ImageChops.invert(Image.radial_gradient("L").resize((w, h), Image.Resampling.BICUBIC))
    img = Image.composite(claro, oscuro, centro.point(lambda v: int(v * 1.0)))
    vetas = Image.effect_noise((max(8, w // 90), h), 9).resize((w, h), Image.Resampling.BICUBIC)
    grano = Image.effect_noise((w, h), 5)
    for capa in (vetas, grano):  # se suma el ruido centrado en 128, es decir, ± alrededor de 0
        img = ImageChops.add(img, capa.convert("RGB"), 1.0, -128)
    return img


def marco_hud(w, h, acento, semilla):
    """Capa transparente con el marco: borde, esquinas, marcas de regla, indicadores y un trazo de señal."""
    rnd = random.Random(semilla)
    capa = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    a = lambda alfa: acento + (alfa,)  # noqa: E731
    m, L = 22, 70
    d.rectangle([m, m, w - m, h - m], outline=a(70), width=2)
    for (x, y, sx, sy) in ((m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
        d.line([(x, y + sy * L), (x, y), (x + sx * L, y)], fill=a(230), width=5)
    for i, x in enumerate(range(150, w - 150, 22)):  # reglas arriba y abajo
        largo = 14 if i % 5 == 0 else 7
        d.line([(x, m + 2), (x, m + 2 + largo)], fill=(200, 215, 230, 90), width=2)
        d.line([(x, h - m - 2), (x, h - m - 2 - largo)], fill=(200, 215, 230, 90), width=2)
    for i, y in enumerate(range(130, h - 130, 22)):  # reglas a los lados
        largo = 14 if i % 5 == 0 else 7
        d.line([(m + 2, y), (m + 2 + largo, y)], fill=(200, 215, 230, 70), width=2)
        d.line([(w - m - 2, y), (w - m - 2 - largo, y)], fill=(200, 215, 230, 70), width=2)
    x0, y0 = w - 230, 46  # indicadores de estado arriba a la derecha
    d.rectangle([x0, y0, x0 + 170, y0 + 38], outline=a(150), width=2)
    for i in range(8):
        encendido = rnd.random() > 0.25
        d.rectangle([x0 + 12 + i * 19, y0 + 12, x0 + 22 + i * 19, y0 + 26], fill=a(230 if encendido else 60))
    pts, x, y = [], 60, h - 90  # trazo de señal abajo a la izquierda, con nodos
    for _ in range(9):
        pts.append((x, y))
        x += 34
        y += rnd.choice((-26, -13, 0, 13, 26))
        y = max(h - 140, min(h - 60, y))
    d.line(pts, fill=a(120), width=3)
    for px, py in pts:
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=a(200))
    brillo = capa.filter(ImageFilter.GaussianBlur(7))  # resplandor tenue detrás de las líneas
    return Image.alpha_composite(brillo, capa)


def generar(salida, ancho=1600, alto=900, calidad=80):
    os.makedirs(salida, exist_ok=True)
    for i, (nombre, acento) in enumerate(FONDOS.items()):
        base = metal(ancho, alto, i).convert("RGBA")
        final = Image.alpha_composite(base, marco_hud(ancho, alto, acento, i)).convert("RGB")
        ruta = os.path.join(salida, f"{nombre}.jpg")
        final.save(ruta, "JPEG", quality=calidad, optimize=True)
        print(f"{nombre}.jpg  {os.path.getsize(ruta) / 1024:.0f} KB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", default=os.path.join("desktop", "assets", "fondos"))
    generar(ap.parse_args().salida)
