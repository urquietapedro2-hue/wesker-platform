"""Optimiza imágenes de fondo: las convierte a JPEG RGB, limita el ancho y el peso.
Uso:  python scripts/optimizar_fondos.py --origen CARPETA_ORIGINAL --destino desktop/assets/fondos
Opciones: --ancho 1600  --max-kb 400  --calidad 78  --patron "background*"
Requiere Pillow solo para este script (no es dependencia de la aplicación)."""
import argparse
import fnmatch
import os
import sys

from PIL import Image, ImageOps

EXTENSIONES = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
COLOR_TRANSPARENCIA = (15, 20, 25)  # lo transparente se aplana sobre el fondo oscuro de la app (no sobre negro)
CALIDAD_MINIMA = 40                 # por debajo de esto se ve mal: primero se reduce la calidad y luego el tamaño
ANCHO_MINIMO = 320


def a_rgb(img):
    """Cualquier modo (RGBA, LA, P, CMYK, 16 bits...) a RGB, respetando la orientación EXIF."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, COLOR_TRANSPARENCIA)
        base.paste(rgba, mask=rgba.getchannel("A"))
        return base
    return img.convert("RGB")


def _redimensionar(img, ancho):
    return img.resize((ancho, max(1, round(img.height * ancho / img.width))), Image.Resampling.LANCZOS)


def optimizar(origen, destino, ancho_max=1600, max_kb=400, calidad_inicial=78):
    """Guarda `destino` como JPEG. Baja la calidad hasta CALIDAD_MINIMA y, si aún pesa de más,
    reduce el ancho un 10 % y repite. Devuelve (calidad, ancho, alto, kb)."""
    with Image.open(origen) as original:
        img = a_rgb(original)
    if img.width > ancho_max:
        img = _redimensionar(img, ancho_max)
    while True:
        calidad = calidad_inicial
        while True:
            img.save(destino, "JPEG", quality=calidad, optimize=True)
            kb = os.path.getsize(destino) / 1024
            if kb <= max_kb or calidad <= CALIDAD_MINIMA:
                break
            calidad -= 5
        if kb <= max_kb or img.width <= ANCHO_MINIMO:
            return calidad, img.width, img.height, kb
        img = _redimensionar(img, int(img.width * 0.9))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origen", required=True, help="carpeta con las imágenes originales")
    ap.add_argument("--destino", required=True, help="carpeta de salida (se crea si no existe)")
    ap.add_argument("--ancho", type=int, default=1600)
    ap.add_argument("--max-kb", type=int, default=400)
    ap.add_argument("--calidad", type=int, default=78)
    ap.add_argument("--patron", default="*", help='filtro por nombre, p. ej. "background*"')
    a = ap.parse_args(argv)

    if os.path.realpath(a.origen) == os.path.realpath(a.destino):
        print("Error: origen y destino son la misma carpeta; así se sobrescribirían los originales.")
        return 2
    archivos = sorted(f for f in os.listdir(a.origen)
                      if f.lower().endswith(EXTENSIONES) and fnmatch.fnmatch(os.path.splitext(f)[0], a.patron))
    if not archivos:
        print(f"No se encontraron imágenes en {a.origen} con el patrón {a.patron!r}.")
        return 1
    os.makedirs(a.destino, exist_ok=True)
    total_antes = total_despues = 0.0
    for nombre in archivos:
        origen = os.path.join(a.origen, nombre)
        destino = os.path.join(a.destino, os.path.splitext(nombre)[0] + ".jpg")
        antes = os.path.getsize(origen) / 1024
        calidad, ancho, alto, kb = optimizar(origen, destino, a.ancho, a.max_kb, a.calidad)
        total_antes, total_despues = total_antes + antes, total_despues + kb
        print(f"{nombre}: {antes:.0f} KB -> {kb:.0f} KB | {ancho}x{alto} | calidad {calidad}")
    print(f"Total: {total_antes:.0f} KB -> {total_despues:.0f} KB ({len(archivos)} imágenes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
