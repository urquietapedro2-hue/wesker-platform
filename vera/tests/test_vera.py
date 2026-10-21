import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vera import local  # noqa: E402
from vera.cache import CacheAudio  # noqa: E402
from vera.config import Config, ConfigError  # noqa: E402
from vera.dialogo import redactar  # noqa: E402
from vera.eventos import Evento, EventoInvalido, validar_evento  # noqa: E402
from vera.nucleo import PAUSA_CORTA_S, PAUSA_LARGA_S, Vera  # noqa: E402
from vera.salida import ReproductorNulo  # noqa: E402
from vera.servidor import MAX_CUERPO, crear_servidor  # noqa: E402
from vera.voz import crear_motor  # noqa: E402
from vera.voz.base import AudioSintetizado, VozError, VozNoDisponible, VozTemporal  # noqa: E402
from vera.voz.elevenlabs import ElevenLabsMotor  # noqa: E402

CLAVE_FALSA = "clave-de-prueba-NO-REAL-0123456789"
VOZ_FALSA = "VozDePrueba1234567890"
AUDIO = AudioSintetizado(b"\x01\x00" * 2400, 24000)


class MotorFalso:
    nombre = "falso"

    def __init__(self, *resultados):
        self.resultados, self.llamadas = list(resultados), 0

    def huella(self):
        return "falso|v1"

    def sintetizar(self, texto):
        self.llamadas += 1
        r = self.resultados.pop(0) if self.resultados else AUDIO
        if isinstance(r, Exception):
            raise r
        return r


class TestConfig(unittest.TestCase):
    def test_por_defecto_es_silencioso_y_no_necesita_claves(self):
        self.assertEqual(Config.desde_entorno(cargar_env=False, env={}).motor, "silencioso")

    def test_elevenlabs_exige_clave_y_voz_sin_revelar_valores(self):
        with self.assertRaises(ConfigError) as cm:
            Config.desde_entorno(cargar_env=False, env={"VERA_MOTOR": "elevenlabs", "ELEVENLABS_API_KEY": CLAVE_FALSA})
        self.assertNotIn(CLAVE_FALSA, str(cm.exception))

    def test_la_clave_no_sale_en_repr(self):
        cfg = Config.desde_entorno(cargar_env=False, env={"VERA_MOTOR": "elevenlabs", "ELEVENLABS_API_KEY": CLAVE_FALSA,
                                                          "VERA_VOICE_ID": VOZ_FALSA})
        self.assertNotIn(CLAVE_FALSA, repr(cfg))

    def test_valores_invalidos(self):
        for env in ({"VERA_MOTOR": "otro"}, {"VERA_PUERTO": "abc"}, {"VERA_PUERTO": "70000"}, {"VERA_CACHE_MB": "0"}):
            with self.assertRaises(ConfigError):
                Config.desde_entorno(cargar_env=False, env=env)


class TestEventos(unittest.TestCase):
    def test_evento_valido_y_limpieza(self):
        e = validar_evento({"codigo": "sesion_iniciada", "usuario": "Pe\x00dro\n" + "x" * 100, "datos": {"rol": "ADMIN"}})
        self.assertEqual(e.nivel, "info")
        self.assertNotIn("\x00", e.usuario)
        self.assertLessEqual(len(e.usuario), 40)

    def test_eventos_invalidos(self):
        for malo in (None, "x", [], {}, {"codigo": "explotar"}, {"codigo": ["nube_perdida"]}, {"codigo": "nube_perdida", "nivel": "x"},
                     {"codigo": "nube_perdida", "v": 2}, {"codigo": "nube_perdida", "datos": [1]},
                     {"codigo": "nube_perdida", "datos": {str(i): i for i in range(50)}}, {"codigo": "nube_perdida", "nodo": 5}):
            with self.assertRaises(EventoInvalido):
                validar_evento(malo)

    def test_todo_codigo_tiene_frase(self):
        from vera.eventos import CODIGOS
        for c in CODIGOS:
            self.assertTrue(redactar(Evento(c, usuario="Ana", nodo="ZENO-01")))
        self.assertIn("Zeno", redactar(Evento("nodo_sin_senal", nodo="ZENO-01")))
        self.assertIn("Ana", redactar(Evento("sesion_iniciada", usuario="Ana")))


class TestElevenLabs(unittest.TestCase):
    class Resp:
        def __init__(self, codigo, contenido=b"\x00\x01" * 100):
            self.status_code, self.content = codigo, contenido

    class Sesion:
        def __init__(self, resp=None, error=None):
            self.resp, self.error, self.peticiones = resp, error, []

        def post(self, url, **kw):
            self.peticiones.append((url, kw))
            if self.error:
                raise self.error
            return self.resp

    def motor(self, sesion):
        return ElevenLabsMotor(CLAVE_FALSA, VOZ_FALSA, sesion=sesion)

    def test_peticion_correcta(self):
        s = self.Sesion(self.Resp(200))
        audio = self.motor(s).sintetizar("Hola")
        url, kw = s.peticiones[0]
        self.assertTrue(url.endswith(f"/v1/text-to-speech/{VOZ_FALSA}"))
        self.assertEqual(kw["params"], {"output_format": "pcm_24000"})
        self.assertEqual(kw["headers"]["xi-api-key"], CLAVE_FALSA)
        self.assertEqual(kw["json"], {"text": "Hola", "model_id": "eleven_multilingual_v2"})
        self.assertEqual((len(audio.datos), audio.frecuencia), (200, 24000))

    def test_errores_se_clasifican(self):
        casos = ((401, VozNoDisponible), (403, VozNoDisponible), (422, VozNoDisponible), (429, VozTemporal),
                 (503, VozTemporal), (404, VozError))
        for codigo, esperado in casos:
            with self.assertRaises(esperado):
                self.motor(self.Sesion(self.Resp(codigo))).sintetizar("Hola")

    def test_sin_red_es_temporal_y_no_filtra_la_clave(self):
        s = self.Sesion(error=ConnectionError(f"fallo con {CLAVE_FALSA}"))
        with self.assertRaises(VozTemporal) as cm:
            self.motor(s).sintetizar("Hola")
        self.assertNotIn(CLAVE_FALSA, str(cm.exception))

    def test_entradas_invalidas(self):
        for texto in ("", "   ", "x" * 501):
            with self.assertRaises(VozError):
                self.motor(self.Sesion(self.Resp(200))).sintetizar(texto)
        for api, voz in (("", VOZ_FALSA), (CLAVE_FALSA, ""), (CLAVE_FALSA, "../../etc"), (CLAVE_FALSA, "corto")):
            with self.assertRaises(VozNoDisponible):
                ElevenLabsMotor(api, voz, sesion=self.Sesion())

    def test_repr_no_contiene_la_clave_y_la_huella_cambia_con_la_voz(self):
        m = self.motor(self.Sesion())
        self.assertNotIn(CLAVE_FALSA, repr(m))
        otra = ElevenLabsMotor(CLAVE_FALSA, "OtraVoz1234567890", sesion=self.Sesion())
        self.assertNotEqual(m.huella(), otra.huella())

    def test_fabrica(self):
        self.assertEqual(crear_motor(Config()).nombre, "silencioso")
        cfg = Config(motor="elevenlabs", api_key=CLAVE_FALSA, voice_id=VOZ_FALSA)
        self.assertEqual(crear_motor(cfg).nombre, "elevenlabs")


class TestNucleo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = [0.0]
        self.repro = ReproductorNulo()
        self.cache = CacheAudio(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def vera(self, motor, cache=True):
        return Vera(motor, self.repro, self.cache if cache else None, enfriamiento_s=20, reloj=lambda: self.t[0])

    def test_sintetiza_reproduce_y_la_segunda_vez_sale_de_cache(self):
        motor = MotorFalso()
        v, e = self.vera(motor), Evento("nube_perdida")
        self.assertTrue(v.procesar(e))
        self.assertTrue(v.procesar(e))
        self.assertEqual((motor.llamadas, len(self.repro.reproducidos)), (1, 2))

    def test_la_cache_depende_de_la_voz(self):
        m1, m2 = MotorFalso(), MotorFalso()
        m2.huella = lambda: "falso|v2"
        e = Evento("nube_perdida")
        self.vera(m1).procesar(e)
        self.vera(m2).procesar(e)
        self.assertEqual((m1.llamadas, m2.llamadas), (1, 1))

    def test_tres_fallos_temporales_ponen_en_pausa_y_luego_se_recupera(self):
        motor = MotorFalso(*[VozTemporal("x")] * 3)
        v = self.vera(motor, cache=False)
        e = Evento("nube_perdida")
        for _ in range(3):
            self.assertFalse(v.procesar(e))
        self.assertTrue(v.estado()["en_pausa"])
        self.assertFalse(v.procesar(e))
        self.assertEqual(motor.llamadas, 3)                 # en pausa no se le insiste al proveedor
        self.t[0] = PAUSA_CORTA_S + 1
        self.assertTrue(v.procesar(e))                      # pasada la pausa vuelve a intentar
        self.assertFalse(v.estado()["en_pausa"])

    def test_credencial_rechazada_pausa_larga_de_inmediato(self):
        motor = MotorFalso(VozNoDisponible("credencial rechazada"))
        v = self.vera(motor, cache=False)
        self.assertFalse(v.procesar(Evento("nube_perdida")))
        self.t[0] = PAUSA_CORTA_S + 1
        self.assertTrue(v.estado()["en_pausa"])
        self.t[0] = PAUSA_LARGA_S + 1
        self.assertFalse(v.estado()["en_pausa"])

    def test_la_cache_sigue_hablando_aunque_el_proveedor_este_en_pausa(self):
        v, e = self.vera(MotorFalso()), Evento("nube_perdida")
        v.procesar(e)
        v.motor.resultados = [VozNoDisponible("x")]
        v.procesar(Evento("nube_restablecida"))             # fallo -> pausa
        self.assertTrue(v.procesar(e))                      # lo que ya estaba en caché suena igual

    def test_enfriamiento_y_cola_llena_nunca_bloquean(self):
        v = Vera(MotorFalso(), self.repro, None, enfriamiento_s=20, reloj=lambda: self.t[0], max_cola=2)
        self.assertEqual(v.encolar(Evento("nube_perdida")), "encolado")
        self.assertEqual(v.encolar(Evento("nube_perdida")), "enfriamiento")
        self.t[0] = 100.0
        self.assertEqual(v.encolar(Evento("nube_restablecida")), "encolado")
        self.assertEqual(v.encolar(Evento("login_fallo")), "cola_llena")

    def test_motor_silencioso_no_reproduce(self):
        from vera.voz.silencioso import MotorSilencioso
        v = self.vera(MotorSilencioso())
        self.assertFalse(v.procesar(Evento("login_fallo")))
        self.assertEqual(self.repro.reproducidos, [])

    def test_un_evento_defectuoso_no_mata_el_hilo(self):
        class Roto(MotorFalso):
            def sintetizar(self, texto):
                raise RuntimeError("boom")
        v = self.vera(Roto(), cache=False)
        v.iniciar()
        v.encolar(Evento("nube_perdida"))
        v.encolar(Evento("login_fallo"))
        v.detener()
        self.assertIn("error interno", v.estado()["ultimo_error"])


class TestCache(unittest.TestCase):
    def test_limite_de_tamano_borra_lo_mas_viejo(self):
        with tempfile.TemporaryDirectory() as d:
            cache = CacheAudio(d, max_mb=1)
            grande = AudioSintetizado(b"\x00\x00" * 200_000, 24000)  # ~0.4 MB cada uno
            for i in range(5):
                cache.guardar(f"{i:032d}", grande)
                os.utime(Path(d) / f"{i:032d}.wav", (i, i))
            self.assertLessEqual(len(list(Path(d).glob("*.wav"))), 2)

    def test_archivo_danado_se_descarta(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ("a" * 32 + ".wav")).write_bytes(b"no soy un wav")
            self.assertIsNone(CacheAudio(d).obtener("a" * 32))
            self.assertFalse((Path(d) / ("a" * 32 + ".wav")).exists())


class TestServidor(unittest.TestCase):
    TOKEN = "token-de-prueba"

    def setUp(self):
        self.repro = ReproductorNulo()
        self.vera = Vera(MotorFalso(), self.repro, None, enfriamiento_s=0)
        self.srv = crear_servidor(self.vera, self.TOKEN, 0)
        self.puerto = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def pedir(self, metodo, ruta, cuerpo=None, token=TOKEN, host=None, cabeceras=None):
        c = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=3)
        h = {"Host": host or f"127.0.0.1:{self.puerto}", **(cabeceras or {})}
        if token is not None:
            h["X-Vera-Token"] = token
        datos = None if cuerpo is None else (cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode())
        if datos is not None:
            h.setdefault("Content-Type", "application/json")
        c.request(metodo, ruta, body=datos, headers=h)
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def test_solo_escucha_en_loopback(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")

    def test_evento_valido_se_acepta(self):
        s, cuerpo = self.pedir("POST", "/v1/evento", {"codigo": "nube_perdida"})
        self.assertEqual((s, cuerpo["resultado"]), (202, "encolado"))

    def test_sin_token_o_con_token_malo_o_host_ajeno(self):
        e = {"codigo": "nube_perdida"}
        self.assertEqual(self.pedir("POST", "/v1/evento", e, token=None)[0], 401)
        self.assertEqual(self.pedir("POST", "/v1/evento", e, token="otro")[0], 401)
        self.assertEqual(self.pedir("POST", "/v1/evento", e, host="malicioso.example")[0], 401)  # DNS rebinding
        self.assertEqual(self.pedir("GET", "/v1/estado", token="otro")[0], 401)
        self.assertEqual(self.pedir("POST", "/v1/evento", e, token="ñandú")[0], 401)               # no ASCII: sin excepción

    def test_entradas_malas(self):
        self.assertEqual(self.pedir("POST", "/v1/evento", b"{no es json")[0], 400)
        self.assertEqual(self.pedir("POST", "/v1/evento", {"codigo": "explotar"})[0], 400)
        self.assertEqual(self.pedir("POST", "/v1/evento", b"x" * (MAX_CUERPO + 1))[0], 413)
        self.assertEqual(self.pedir("POST", "/v1/otra", {"codigo": "nube_perdida"})[0], 404)
        self.assertEqual(self.pedir("GET", "/v1/evento")[0], 404)

    def test_estado(self):
        s, cuerpo = self.pedir("GET", "/v1/estado")
        self.assertEqual((s, cuerpo["motor"], cuerpo["ok"]), (200, "falso", True))


class TestLocal(unittest.TestCase):
    def test_publicar_y_retirar(self):
        with tempfile.TemporaryDirectory() as d:
            anterior = os.environ.get("APPDATA")
            os.environ["APPDATA"] = d
            try:
                ruta = local.publicar(1234, "tok")
                self.assertEqual(json.loads(ruta.read_text())["puerto"], 1234)
                local.retirar()
                self.assertFalse(ruta.exists())
            finally:
                os.environ.pop("APPDATA") if anterior is None else os.environ.update(APPDATA=anterior)


if __name__ == "__main__":
    unittest.main()
