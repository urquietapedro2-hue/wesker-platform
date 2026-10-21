import json
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "desktop"))

from core import preferencias  # noqa: E402
from core.audio_eventos import ENFRIAMIENTO_S, EVENTOS, Enfriamiento, buscar_sonido, carpetas_de_sonido  # noqa: E402

BASE = Path(__file__).resolve().parent.parent / "desktop" / "assets" / "sonidos" / "base"


class TestBusqueda(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        self.usuario, self.recursos = r / "usuario", r / "recursos"
        for c in (self.usuario / "sonidos", self.recursos / "sonidos" / "base"):
            c.mkdir(parents=True)
        self.carpetas = carpetas_de_sonido(self.usuario, self.recursos)

    def tearDown(self):
        self.tmp.cleanup()

    def test_prioridad_usuario_luego_repo_luego_base(self):
        base = self.recursos / "sonidos" / "base" / "login_ok.wav"
        base.write_bytes(b"x")
        self.assertEqual(buscar_sonido("login_ok", self.carpetas), base)
        propio = self.recursos / "sonidos" / "login_ok.mp3"
        propio.write_bytes(b"x")
        self.assertEqual(buscar_sonido("login_ok", self.carpetas), propio)  # lo tuyo gana al de ejemplo
        appdata = self.usuario / "sonidos" / "login_ok.wav"
        appdata.write_bytes(b"x")
        self.assertEqual(buscar_sonido("login_ok", self.carpetas), appdata)  # y lo de AppData gana a todo

    def test_dentro_de_una_carpeta_prefiere_wav(self):
        for ext in (".ogg", ".mp3", ".wav"):
            (self.usuario / "sonidos" / f"login_fallo{ext}").write_bytes(b"x")
        self.assertEqual(buscar_sonido("login_fallo", self.carpetas).suffix, ".wav")

    def test_evento_desconocido_o_sin_archivo(self):
        self.assertIsNone(buscar_sonido("error_sistema", self.carpetas))
        (self.usuario / "sonidos" / "explosion.wav").write_bytes(b"x")
        self.assertIsNone(buscar_sonido("explosion", self.carpetas))   # solo eventos conocidos
        self.assertIsNone(buscar_sonido("../login_ok", self.carpetas))  # sin escapar de las carpetas


class TestEnfriamiento(unittest.TestCase):
    def test_no_suena_en_rafaga(self):
        t = [0.0]
        e = Enfriamiento(lambda: t[0])
        self.assertTrue(e.permitido("error_sistema"))
        t[0] = 5.0
        self.assertFalse(e.permitido("error_sistema"))      # dentro de los 10 s
        self.assertTrue(e.permitido("login_ok"))              # otro evento, sin espera
        t[0] = 10.5
        self.assertTrue(e.permitido("error_sistema"))

    def test_todos_los_eventos_tienen_regla(self):
        self.assertEqual(set(ENFRIAMIENTO_S), set(EVENTOS))


class TestPreferencias(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.anterior = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self.tmp.name

    def tearDown(self):
        if self.anterior is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self.anterior
        self.tmp.cleanup()

    def test_valores_por_defecto_y_ciclo_guardar_cargar(self):
        self.assertEqual(preferencias.cargar(), {"audio_activo": True, "volumen": 80})
        self.assertTrue(preferencias.guardar({"audio_activo": False, "volumen": 35}))
        self.assertEqual(preferencias.cargar(), {"audio_activo": False, "volumen": 35})

    def test_archivo_roto_o_con_basura_no_falla(self):
        ruta = Path(self.tmp.name) / "WESKER" / "preferencias.json"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        for contenido in ("no es json", "[1,2]", json.dumps({"audio_activo": "si", "volumen": 9999}),
                          json.dumps({"volumen": True}), json.dumps({"volumen": -5})):
            ruta.write_text(contenido, encoding="utf-8")
            p = preferencias.cargar()
            self.assertIsInstance(p["audio_activo"], bool)
            self.assertTrue(0 <= p["volumen"] <= 100)

    def test_guardar_limita_el_volumen(self):
        preferencias.guardar({"audio_activo": True, "volumen": 500})
        self.assertEqual(preferencias.cargar()["volumen"], 100)


class TestSonidosBase(unittest.TestCase):
    def test_los_ejemplos_son_wav_validos_y_cortos(self):
        for evento in EVENTOS:
            ruta = BASE / f"{evento}.wav"
            self.assertTrue(ruta.exists(), evento)
            with wave.open(str(ruta)) as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth()), (1, 2))
                self.assertLess(w.getnframes() / w.getframerate(), 3.0)
                self.assertGreater(w.getnframes(), 1000)


if __name__ == "__main__":
    unittest.main()
