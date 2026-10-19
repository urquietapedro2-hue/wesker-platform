import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

try:
    from PIL import Image
    import optimizar_fondos as opt
    HAY_PIL = True
except ImportError:
    HAY_PIL = False


@unittest.skipUnless(HAY_PIL, "Pillow no está instalado")
class TestOptimizador(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.origen, self.destino = os.path.join(self.tmp.name, "o"), os.path.join(self.tmp.name, "d")
        os.makedirs(self.origen)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tamano_dinamico_con_imagen_dificil(self):
        # bytes aleatorios de 1500 px (sin reducción previa): no caben en 400 KB ni con la calidad mínima
        Image.frombytes("RGB", (1500, 1000), os.urandom(1500 * 1000 * 3)).save(os.path.join(self.origen, "ruido.png"))
        self.assertEqual(opt.main(["--origen", self.origen, "--destino", self.destino]), 0)
        salida = os.path.join(self.destino, "ruido.jpg")
        self.assertLessEqual(os.path.getsize(salida) / 1024, 400)
        with Image.open(salida) as img:
            self.assertEqual(img.mode, "RGB")
            self.assertLess(img.width, 1500)  # tuvo que reducir el tamaño

    def test_transparencia_se_aplana_sobre_el_color_oscuro(self):
        Image.new("RGBA", (200, 100), (255, 0, 0, 0)).save(os.path.join(self.origen, "vacio.png"))
        opt.main(["--origen", self.origen, "--destino", self.destino])
        with Image.open(os.path.join(self.destino, "vacio.jpg")) as img:
            r, g, b = img.getpixel((50, 50))
        self.assertLess(abs(r - 15) + abs(g - 20) + abs(b - 25), 12)  # no negro ni rojo

    def test_cualquier_modo_sale_en_rgb(self):
        for modo in ("L", "P", "CMYK", "LA"):
            Image.new(modo, (64, 64)).save(os.path.join(self.origen, f"m_{modo}.png" if modo != "CMYK" else "m_CMYK.jpg"))
        self.assertEqual(opt.main(["--origen", self.origen, "--destino", self.destino]), 0)
        for f in os.listdir(self.destino):
            with Image.open(os.path.join(self.destino, f)) as img:
                self.assertEqual(img.mode, "RGB", f)

    def test_no_sobrescribe_originales_ni_falla_sin_imagenes(self):
        self.assertEqual(opt.main(["--origen", self.origen, "--destino", self.origen]), 2)
        self.assertEqual(opt.main(["--origen", self.origen, "--destino", self.destino]), 1)

    def test_imagen_pequena_no_se_agranda_y_filtra_por_patron(self):
        Image.new("RGB", (400, 200), (30, 40, 50)).save(os.path.join(self.origen, "background_a.png"))
        Image.new("RGB", (400, 200), (30, 40, 50)).save(os.path.join(self.origen, "otra.png"))
        opt.main(["--origen", self.origen, "--destino", self.destino, "--patron", "background*"])
        self.assertEqual(os.listdir(self.destino), ["background_a.jpg"])
        with Image.open(os.path.join(self.destino, "background_a.jpg")) as img:
            self.assertEqual(img.size, (400, 200))


if __name__ == "__main__":
    unittest.main()
