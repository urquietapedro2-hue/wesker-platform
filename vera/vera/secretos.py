"""Almacén cifrado de secretos en %APPDATA%\\WESKER\\vera_secretos.dat (fuera del repositorio y fuera de OneDrive).
En Windows usa DPAPI: el cifrado queda atado a TU cuenta de Windows, no hay contraseña que recordar ni guardar,
y el archivo no sirve copiado a otro equipo o a otra cuenta. Sin dependencias (solo ctypes)."""
import json
import os
import sys
import tempfile
from pathlib import Path

MAGIA = b"WVS1"                       # identifica el formato; si falta, el archivo no es de V.E.R.A.
ENTROPIA = b"WESKER-VERA-v1"          # no es secreta: evita que otro programa descifre el archivo por casualidad
CAMPOS_ALMACEN = ("motor", "api_key", "voice_id", "model_id")


class SecretosError(Exception):
    """Mensaje seguro para mostrar: nunca incluye valores secretos."""


class CifradorDPAPI:
    """Windows Data Protection API. Solo existe en Windows."""

    def __init__(self):
        if sys.platform != "win32":
            raise SecretosError("El cifrado local (DPAPI) solo existe en Windows. En otros sistemas usa variables de entorno del sistema.")
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        self._ct, self._BLOB = ctypes, BLOB
        self._crypt32, self._kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
        p = ctypes.POINTER(BLOB)
        self._crypt32.CryptProtectData.argtypes = [p, wintypes.LPCWSTR, p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, p]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = [p, ctypes.POINTER(wintypes.LPWSTR), p, ctypes.c_void_p,
                                                     ctypes.c_void_p, wintypes.DWORD, p]
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self._kernel32.LocalFree.restype = ctypes.c_void_p

    def _blob(self, datos: bytes):
        buf = self._ct.create_string_buffer(datos, len(datos))
        return self._BLOB(len(datos), self._ct.cast(buf, self._ct.POINTER(self._ct.c_char))), buf

    def _liberar(self, salida):
        try:
            return self._ct.string_at(salida.pbData, salida.cbData)
        finally:
            self._kernel32.LocalFree(self._ct.cast(salida.pbData, self._ct.c_void_p))

    def cifrar(self, datos: bytes) -> bytes:
        entrada, _a = self._blob(datos)
        entropia, _b = self._blob(ENTROPIA)
        salida = self._BLOB()
        if not self._crypt32.CryptProtectData(self._ct.byref(entrada), "WESKER V.E.R.A.", self._ct.byref(entropia),
                                              None, None, 0x1, self._ct.byref(salida)):  # 0x1 = sin ventanas
            raise SecretosError("Windows no pudo cifrar los datos (DPAPI).")
        return self._liberar(salida)

    def descifrar(self, datos: bytes) -> bytes:
        entrada, _a = self._blob(datos)
        entropia, _b = self._blob(ENTROPIA)
        salida = self._BLOB()
        if not self._crypt32.CryptUnprotectData(self._ct.byref(entrada), None, self._ct.byref(entropia),
                                                None, None, 0x1, self._ct.byref(salida)):
            raise SecretosError("Windows no pudo descifrar los datos (otra cuenta de Windows o archivo dañado).")
        return self._liberar(salida)


def ruta_almacen() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "WESKER" / "vera_secretos.dat"


class Almacen:
    def __init__(self, cifrador=None, ruta=None):
        self._cifrador, self.ruta = cifrador, Path(ruta) if ruta else ruta_almacen()

    def _c(self):
        if self._cifrador is None:
            self._cifrador = CifradorDPAPI()
        return self._cifrador

    def existe(self) -> bool:
        return self.ruta.is_file()

    def guardar(self, valores: dict):
        limpio = {}
        for campo in CAMPOS_ALMACEN:
            v = valores.get(campo)
            if v is None:
                continue
            if not isinstance(v, str) or len(v) > 512 or "\x00" in v:
                raise SecretosError(f"valor no válido para {campo}")
            limpio[campo] = v.strip()
        cifrado = MAGIA + self._c().cifrar(json.dumps(limpio).encode("utf-8"))
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.ruta.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(cifrado)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.ruta)
        except OSError as ex:
            raise SecretosError(f"no se pudo escribir el almacén ({type(ex).__name__})") from None

    def cargar(self) -> dict:
        """{} si no existe. Lanza SecretosError si existe pero no se puede descifrar."""
        if not self.existe():
            return {}
        try:
            crudo = self.ruta.read_bytes()
        except OSError as ex:
            raise SecretosError(f"no se pudo leer el almacén ({type(ex).__name__})") from None
        if not crudo.startswith(MAGIA):
            raise SecretosError("El almacén cifrado está dañado o no es de V.E.R.A. Vuelve a ejecutar --guardar-secretos.")
        try:
            datos = json.loads(self._c().descifrar(crudo[len(MAGIA):]).decode("utf-8"))
        except SecretosError:
            raise
        except Exception:
            raise SecretosError("No se pudo descifrar el almacén: pertenece a otra cuenta de Windows o está dañado. "
                                "Vuelve a ejecutar --guardar-secretos.") from None
        if not isinstance(datos, dict):
            raise SecretosError("El contenido del almacén no es válido. Vuelve a ejecutar --guardar-secretos.")
        return {k: v for k, v in datos.items() if k in CAMPOS_ALMACEN and isinstance(v, str)}

    def borrar(self):
        self.ruta.unlink(missing_ok=True)


def destruir(ruta):
    """Sobrescribe el archivo con bytes aleatorios y lo borra (mejor esfuerzo: un SSD o OneDrive pueden conservar copias)."""
    ruta = Path(ruta)
    with open(ruta, "r+b") as f:
        f.write(os.urandom(max(1, ruta.stat().st_size)))
        f.flush()
        os.fsync(f.fileno())
    ruta.unlink()
