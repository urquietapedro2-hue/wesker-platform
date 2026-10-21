import io
import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vera import __main__ as principal  # noqa: E402
from vera.config import Config, ConfigError, leer_dotenv  # noqa: E402
from vera.diagnostico import diagnosticar  # noqa: E402
from vera.nucleo import Vera  # noqa: E402
from vera.salida import ReproductorNulo  # noqa: E402
from vera.secretos import Almacen, CifradorDPAPI, SecretosError, destruir  # noqa: E402
from vera.voz.base import AudioSintetizado, VozError, VozNoDisponible, VozTemporal  # noqa: E402
from vera.voz.elevenlabs import ElevenLabsMotor  # noqa: E402

CLAVE = "sk_" + "0123456789abcdef" * 3          # clave FALSA, solo para pruebas
VOZ = "VozDePrueba1234567890"


class CifradorFalso:
    """Cifrador reversible de mentira: permite probar toda la lógica sin Windows."""

    def __init__(self, modo=None):
        self.modo = modo

    def cifrar(self, datos):
        if self.modo == "distinto":
            datos = b'{"api_key": "otra"}'
        if self.modo == "corrupto":
            datos = b"\x00" + datos
        return bytes(b ^ 0x5A for b in datos)[::-1]

    def descifrar(self, datos):
        if self.modo == "falla":
            raise SecretosError("no se puede descifrar")
        return bytes(b ^ 0x5A for b in datos[::-1])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.almacen = Almacen(CifradorFalso(), self.dir / "vera_secretos.dat")

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, texto, codificacion="utf-8", bom=False):
        ruta = self.dir / ".env"
        ruta.write_bytes((b"\xef\xbb\xbf" if bom else b"") + texto.encode(codificacion))
        return ruta


class TestAlmacen(Base):
    def test_ciclo_y_el_archivo_no_contiene_texto_plano(self):
        self.almacen.guardar({"motor": "elevenlabs", "api_key": CLAVE, "voice_id": VOZ, "intruso": "x"})
        crudo = self.almacen.ruta.read_bytes()
        self.assertTrue(crudo.startswith(b"WVS1"))
        for secreto in (CLAVE.encode(), VOZ.encode(), b"elevenlabs", b"api_key"):
            self.assertNotIn(secreto, crudo)
        self.assertEqual(self.almacen.cargar(), {"motor": "elevenlabs", "api_key": CLAVE, "voice_id": VOZ})  # campo ajeno descartado

    def test_sin_archivo_devuelve_vacio(self):
        self.assertEqual(self.almacen.cargar(), {})

    def test_archivos_danados_dan_error_claro_sin_revelar_nada(self):
        for contenido in (b"no es un almacen", b"WVS1" + b"\x01" * 20, b""):
            self.almacen.ruta.write_bytes(contenido)
            with self.assertRaises(SecretosError) as cm:
                self.almacen.cargar()
            self.assertNotIn(CLAVE, str(cm.exception))

    def test_otra_cuenta_de_windows_no_puede_descifrar(self):
        self.almacen.guardar({"api_key": CLAVE})
        ajeno = Almacen(CifradorFalso("falla"), self.almacen.ruta)
        with self.assertRaises(SecretosError):
            ajeno.cargar()

    def test_valores_invalidos_no_se_guardan(self):
        for malo in ({"api_key": 5}, {"api_key": "x" * 600}, {"api_key": "a\x00b"}):
            with self.assertRaises(SecretosError):
                self.almacen.guardar(malo)
        self.assertFalse(self.almacen.existe())

    def test_borrar(self):
        self.almacen.guardar({"api_key": CLAVE})
        self.almacen.borrar()
        self.assertFalse(self.almacen.existe())
        self.almacen.borrar()  # borrar dos veces no falla

    def test_dpapi_solo_existe_en_windows(self):
        if sys.platform == "win32":
            self.skipTest("en Windows DPAPI sí existe")
        with self.assertRaises(SecretosError):
            CifradorDPAPI()

    def test_destruir_sobrescribe_y_borra(self):
        ruta = self.dir / "secreto.txt"
        ruta.write_text(f"ELEVENLABS_API_KEY={CLAVE}", encoding="utf-8")
        with patch("pathlib.Path.unlink") as unlink:  # se observa el contenido justo antes del borrado
            destruir(ruta)
        self.assertNotIn(CLAVE.encode(), ruta.read_bytes())
        self.assertTrue(unlink.called)
        ruta.unlink()


class TestPrioridadYOrigen(Base):
    def test_entorno_gana_al_almacen_y_este_al_env(self):
        self.almacen.guardar({"motor": "elevenlabs", "api_key": "de-almacen-0000", "voice_id": VOZ})
        ruta = self.env("VERA_MOTOR=silencioso\nELEVENLABS_API_KEY=del-env-0000\nVERA_VOICE_ID=OtraVoz1234567890\nVERA_MODEL_ID=modelo_env")
        cfg, info = Config.resolver(env={"ELEVENLABS_API_KEY": "de-entorno-00"}, almacen=self.almacen, ruta_env=ruta)
        self.assertEqual(cfg.api_key, "de-entorno-00")
        self.assertEqual(cfg.voice_id, VOZ)
        self.assertEqual(cfg.motor, "elevenlabs")
        self.assertEqual(cfg.model_id, "modelo_env")                      # solo en .env
        self.assertEqual(info.origenes["ELEVENLABS_API_KEY"], "variable de entorno")
        self.assertEqual(info.origenes["VERA_VOICE_ID"], "almacén cifrado")
        self.assertTrue(info.origenes["VERA_MODEL_ID"].startswith(".env"))
        self.assertTrue(info.almacen_existe)

    def test_valores_por_defecto_y_sus_origenes(self):
        cfg, info = Config.resolver(cargar_env=False, env={})
        self.assertEqual((cfg.motor, info.origenes["VERA_MOTOR"]), ("silencioso", "valor por defecto"))

    def test_clave_en_texto_plano_genera_aviso_y_nunca_aparece_en_info(self):
        ruta = self.env(f"VERA_MOTOR=elevenlabs\nELEVENLABS_API_KEY={CLAVE}\nVERA_VOICE_ID={VOZ}\n")
        cfg, info = Config.resolver(env={}, ruta_env=ruta)
        self.assertTrue(any("TEXTO PLANO" in a and "--migrar-env" in a for a in info.avisos))
        self.assertNotIn(CLAVE, repr(info) + repr(cfg))

    def test_comentarios_en_linea_del_env_example_se_ignoran(self):
        ruta = self.env("VERA_MOTOR=silencioso          # silencioso | elevenlabs\nVERA_PUERTO=0   # puerto\n")
        cfg, _ = Config.resolver(env={}, ruta_env=ruta)
        self.assertEqual((cfg.motor, cfg.puerto), ("silencioso", 0))

    def test_env_en_utf8_con_bom_y_en_utf16_de_powershell_se_leen(self):
        contenido = f"VERA_MOTOR=elevenlabs\nELEVENLABS_API_KEY={CLAVE}\nVERA_VOICE_ID={VOZ}\n"
        for etiqueta, ruta in (("BOM", self.env(contenido, bom=True)), ("UTF-16", self.env(contenido, "utf-16"))):
            valores, cod, avisos = leer_dotenv(ruta)
            self.assertEqual(valores["VERA_MOTOR"], "elevenlabs", etiqueta)   # sin esto el motor caía a «silencioso»
            self.assertTrue(avisos, etiqueta)
        cfg, info = Config.resolver(env={}, ruta_env=self.env(contenido, "utf-16"))
        self.assertEqual(cfg.motor, "elevenlabs")

    def test_falta_de_credenciales_da_error_accionable_sin_revelar_valores(self):
        with self.assertRaises(ConfigError) as cm:
            Config.resolver(cargar_env=False, env={"VERA_MOTOR": "elevenlabs", "ELEVENLABS_API_KEY": CLAVE})
        self.assertIn("--guardar-secretos", str(cm.exception))
        self.assertNotIn(CLAVE, str(cm.exception))

    def test_almacen_que_no_se_puede_descifrar_se_propaga_como_error_claro(self):
        self.almacen.guardar({"api_key": CLAVE})
        with self.assertRaises(SecretosError):
            Config.resolver(cargar_env=False, env={}, almacen=Almacen(CifradorFalso("falla"), self.almacen.ruta))


class TestErroresDelProveedor(unittest.TestCase):
    class Resp:
        def __init__(self, codigo, cuerpo=None, contenido=b""):
            self.status_code, self.content, self._cuerpo = codigo, contenido, cuerpo

        def json(self):
            if self._cuerpo is None:
                raise ValueError("sin json")
            return self._cuerpo

    class Sesion:
        def __init__(self, resp):
            self.resp = resp

        def post(self, *a, **k):
            return self.resp

    def sintetizar(self, resp):
        return ElevenLabsMotor(CLAVE, VOZ, sesion=self.Sesion(resp)).sintetizar("Hola")

    def test_el_mensaje_incluye_lo_que_dice_el_proveedor(self):
        cuerpo = {"detail": {"status": "voice_not_found", "message": "La voz no existe"}}
        with self.assertRaises(VozNoDisponible) as cm:
            self.sintetizar(self.Resp(404, cuerpo))
        self.assertIn("voice_not_found", str(cm.exception))
        self.assertIn("voice_id", str(cm.exception))

    def test_cada_codigo_da_una_explicacion_distinta_y_accionable(self):
        esperado = {401: "clave", 402: "plan", 403: "denegado", 404: "voice_id", 400: "parámetros", 422: "parámetros"}
        for codigo, palabra in esperado.items():
            with self.assertRaises(VozNoDisponible) as cm:
                self.sintetizar(self.Resp(codigo))
            self.assertIn(palabra, str(cm.exception), codigo)
        for codigo in (429, 500, 503):
            with self.assertRaises(VozTemporal):
                self.sintetizar(self.Resp(codigo))
        with self.assertRaises(VozError):
            self.sintetizar(self.Resp(418))

    def test_la_clave_se_elimina_aunque_el_proveedor_la_repita(self):
        cuerpo = {"detail": {"status": "invalid_api_key", "message": f"La clave {CLAVE} no es válida"}}
        with self.assertRaises(VozNoDisponible) as cm:
            self.sintetizar(self.Resp(401, cuerpo))
        self.assertNotIn(CLAVE, str(cm.exception))
        self.assertIn("***", str(cm.exception))

    def test_respuesta_sin_json_o_con_forma_rara_no_rompe(self):
        for cuerpo in (None, [1, 2], "texto", {"detail": [1, 2]}, {"detail": None}):
            with self.assertRaises(VozNoDisponible):
                self.sintetizar(self.Resp(401, cuerpo))

    def test_exito(self):
        self.assertEqual(self.sintetizar(self.Resp(200, contenido=b"\x01\x00" * 50)).datos, b"\x01\x00" * 50)


class TestRegistroVisible(unittest.TestCase):
    def test_se_registra_cada_paso_y_el_error_del_proveedor_sin_la_clave(self):
        class Sesion:
            def post(self, *a, **k):
                class R:
                    status_code = 401
                    content = b""

                    def json(self):
                        return {"detail": {"status": "invalid_api_key", "message": f"mala {CLAVE}"}}
                return R()
        from vera.eventos import Evento
        v = Vera(ElevenLabsMotor(CLAVE, VOZ, sesion=Sesion()), ReproductorNulo(), None)
        with self.assertLogs("vera", level="INFO") as registro:
            v.procesar(Evento("login_fallo"))
        salida = "\n".join(registro.output)
        self.assertIn("Acceso denegado", salida)
        self.assertIn("HTTP 401", salida)
        self.assertNotIn(CLAVE, salida)
        self.assertIn("en pausa", salida)

    def test_eventos_omitidos_por_enfriamiento_quedan_registrados(self):
        from vera.eventos import Evento
        from vera.voz.silencioso import MotorSilencioso
        v = Vera(MotorSilencioso(), ReproductorNulo(), None, enfriamiento_s=60)
        v.encolar(Evento("login_fallo"))
        with self.assertLogs("vera", level="INFO") as registro:
            self.assertEqual(v.encolar(Evento("login_fallo")), "enfriamiento")
        self.assertIn("omitido", registro.output[0])


class MotorOk:
    nombre = "elevenlabs"

    def sintetizar(self, texto):
        return AudioSintetizado(b"\x01\x00" * 500, 24000)


class TestDiagnostico(Base):
    def correr(self, cfg, info, motor, estado=None, repro=None):
        lineas = []
        codigo = diagnosticar(cfg, info, motor, repro or ReproductorNulo(), lambda: estado, salida=lineas.append)
        return codigo, "\n".join(lineas)

    def test_motor_silencioso_por_falta_de_configuracion_se_explica(self):
        cfg, info = Config.resolver(cargar_env=False, env={})
        codigo, texto = self.correr(cfg, info, None)
        self.assertEqual(codigo, 1)
        self.assertIn("SILENCIOSO", texto)
        self.assertIn("no está definido", texto)

    def test_todo_correcto(self):
        cfg, info = Config.resolver(cargar_env=False, env={"VERA_MOTOR": "elevenlabs", "ELEVENLABS_API_KEY": CLAVE, "VERA_VOICE_ID": VOZ})
        repro = ReproductorNulo()
        codigo, texto = self.correr(cfg, info, MotorOk(), {"motor": "elevenlabs", "en_pausa": False, "ultimo_error": None}, repro)
        self.assertEqual(codigo, 0)
        self.assertEqual(len(repro.reproducidos), 1)
        self.assertIn("1000 bytes", texto)
        self.assertNotIn(CLAVE, texto)                       # nunca se imprime la clave
        self.assertNotIn(VOZ, texto)                         # el voice_id sale enmascarado
        self.assertIn("Vo", texto)

    def test_proveedor_que_rechaza_se_reporta_con_su_motivo(self):
        class Rechaza:
            nombre = "elevenlabs"

            def sintetizar(self, t):
                raise VozNoDisponible("HTTP 402: tu plan no permite este uso por API.")
        cfg, info = Config.resolver(cargar_env=False, env={"VERA_MOTOR": "elevenlabs", "ELEVENLABS_API_KEY": CLAVE, "VERA_VOICE_ID": VOZ})
        codigo, texto = self.correr(cfg, info, Rechaza())
        self.assertEqual(codigo, 1)
        self.assertIn("HTTP 402", texto)

    def test_falta_de_credencial_o_voz_invalida(self):
        cfg = Config(motor="elevenlabs", api_key="", voice_id="../x")
        _, info = Config.resolver(cargar_env=False, env={})
        codigo, texto = self.correr(cfg, info, MotorOk())
        self.assertEqual(codigo, 1)
        self.assertIn("AUSENTE", texto)
        self.assertIn("formato no válido", texto)

    def test_el_servicio_en_pausa_muestra_su_ultimo_error(self):
        cfg, info = Config.resolver(cargar_env=False, env={"VERA_MOTOR": "elevenlabs", "ELEVENLABS_API_KEY": CLAVE, "VERA_VOICE_ID": VOZ})
        _, texto = self.correr(cfg, info, MotorOk(), {"motor": "elevenlabs", "en_pausa": True, "ultimo_error": "HTTP 401: clave rechazada"})
        self.assertIn("en_pausa=True", texto)
        self.assertIn("HTTP 401", texto)


class TestComandos(Base):
    def test_migrar_cifra_verifica_y_destruye_el_env(self):
        ruta = self.env(f"VERA_MOTOR=elevenlabs\nELEVENLABS_API_KEY={CLAVE}\nVERA_VOICE_ID={VOZ}\n")
        with patch.object(principal, "encontrar_dotenv", return_value=ruta), patch("builtins.print"):
            self.assertEqual(principal._migrar_env(self.almacen), 0)
        self.assertFalse(ruta.exists())
        self.assertEqual(self.almacen.cargar()["api_key"], CLAVE)
        self.assertNotIn(CLAVE.encode(), self.almacen.ruta.read_bytes())

    def test_si_la_verificacion_falla_el_env_no_se_toca(self):
        for modo in ("distinto", "corrupto"):
            ruta = self.env(f"ELEVENLABS_API_KEY={CLAVE}\n")
            malo = Almacen(CifradorFalso(modo), self.dir / f"{modo}.dat")
            with patch.object(principal, "encontrar_dotenv", return_value=ruta), patch("builtins.print"):
                try:
                    resultado = principal._migrar_env(malo)
                except SecretosError:
                    resultado = 1
            self.assertEqual(resultado, 1, modo)
            self.assertTrue(ruta.exists(), modo)
            self.assertIn(CLAVE, ruta.read_text(encoding="utf-8"), modo)

    def test_migrar_sin_clave_o_sin_env(self):
        ruta = self.env("VERA_MOTOR=silencioso\n")
        with patch.object(principal, "encontrar_dotenv", return_value=ruta), patch("builtins.print"):
            self.assertEqual(principal._migrar_env(self.almacen), 1)
        self.assertTrue(ruta.exists())
        with patch.object(principal, "encontrar_dotenv", return_value=None), patch("builtins.print"):
            self.assertEqual(principal._migrar_env(self.almacen), 1)

    def test_guardar_secretos_valida_y_no_muestra_la_clave(self):
        with patch("getpass.getpass", return_value=CLAVE), patch("builtins.input", side_effect=[VOZ, ""]), \
                patch("builtins.print") as imprimir:
            self.assertEqual(principal._guardar_secretos(self.almacen), 0)
        self.assertNotIn(CLAVE, " ".join(str(c) for c in imprimir.call_args_list))
        self.assertEqual(self.almacen.cargar()["model_id"], "eleven_multilingual_v2")
        with patch("getpass.getpass", return_value=CLAVE), patch("builtins.input", side_effect=["../mal", ""]), patch("builtins.print"):
            self.assertEqual(principal._guardar_secretos(Almacen(CifradorFalso(), self.dir / "otro.dat")), 1)
        with patch("getpass.getpass", return_value="corta"), patch("builtins.input", side_effect=[VOZ, ""]), patch("builtins.print"):
            self.assertEqual(principal._guardar_secretos(Almacen(CifradorFalso(), self.dir / "otro2.dat")), 1)


if __name__ == "__main__":
    unittest.main()
