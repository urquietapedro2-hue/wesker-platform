import os
import unittest
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "desktop" / "assets"
FONDOS = ["background", "background_dashboard", "background_diag", "background_estop", "background_manual", "background_zeno"]

try:
    from PIL import Image
    HAY_PIL = True
except ImportError:
    HAY_PIL = False


@unittest.skipUnless(HAY_PIL, "Pillow no está instalado")
class TestRecursos(unittest.TestCase):
    def test_estan_los_logos_y_el_icono(self):
        for nombre in ("wesker_logo.png", "wesker_logo.svg", "vera_logo.png", "vera_logo.svg", "wesker.ico"):
            self.assertTrue((ASSETS / nombre).exists(), nombre)
        with Image.open(ASSETS / "wesker_logo.png") as img:
            self.assertEqual(img.mode, "RGBA")  # con transparencia
        with Image.open(ASSETS / "wesker.ico") as ico:
            self.assertIn((256, 256), ico.info.get("sizes", {(256, 256)}))

    def test_fondos_ligeros_y_del_tamano_correcto(self):
        for nombre in FONDOS:
            ruta = ASSETS / "fondos" / f"{nombre}.jpg"
            self.assertTrue(ruta.exists(), nombre)
            self.assertLessEqual(os.path.getsize(ruta) / 1024, 400, f"{nombre} pesa demasiado")
            with Image.open(ruta) as img:
                self.assertEqual((img.mode, img.width), ("RGB", 1600))

    def test_los_svg_son_validos(self):
        import xml.etree.ElementTree as ET
        for nombre in ("wesker_logo.svg", "vera_logo.svg"):
            self.assertTrue(ET.parse(ASSETS / nombre).getroot().tag.endswith("svg"))


if __name__ == "__main__":
    unittest.main()
