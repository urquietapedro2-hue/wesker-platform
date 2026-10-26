"""Almacén cifrado del HMI (token de Zeno) en %APPDATA%/WESKER/hmi_secretos.dat, atado a tu cuenta de Windows (DPAPI).
Copia deliberada de la técnica de vera/secretos.py: el HMI y V.E.R.A. son independientes y no se importan entre sí."""
import json
import os
import sys
import tempfile
from pathlib import Path

from core.paths import user_data_dir

MAGIA = b"WHS1"
ENTROPIA = b"WESKER-HMI-v1"


class SecretosError(Exception):
    """Mensaje seguro para mostrar: nunca incluye valores secretos."""


class CifradorDPAPI:
    def __init__(self):
        if sys.platform != "win32":
            raise SecretosError("El cifrado local (DPAPI) solo existe en Windows.")
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

    def _blob(self, datos):
        buf = self._ct.create_string_buffer(datos, len(datos))
        return self._BLOB(len(datos), self._ct.cast(buf, self._ct.POINTER(self._ct.c_char))), buf

    def _liberar(self, salida):
        try:
            return self._ct.string_at(salida.pbData, salida.cbData)
        finally:
            self._kernel32.LocalFree(self._ct.cast(salida.pbData, self._ct.c_void_p))

    def cifrar(self, datos):
        entrada, _a = self._blob(datos)
        entropia, _b = self._blob(ENTROPIA)
        salida = self._BLOB()
        if not self._crypt32.CryptProtectData(self._ct.byref(entrada), "WESKER HMI", self._ct.byref(entropia), None, None, 0x1,
                                              self._ct.byref(salida)):
            raise SecretosError("Windows no pudo cifrar los datos (DPAPI).")
        return self._liberar(salida)

    def descifrar(self, datos):
        entrada, _a = self._blob(datos)
        entropia, _b = self._blob(ENTROPIA)
        salida = self._BLOB()
        if not self._crypt32.CryptUnprotectData(self._ct.byref(entrada), None, self._ct.byref(entropia), None, None, 0x1,
                                                self._ct.byref(salida)):
            raise SecretosError("Windows no pudo descifrar los datos (otra cuenta de Windows o archivo dañado).")
        return self._liberar(salida)


class Almacen:
    CAMPOS = ("zeno_token",)

    def __init__(self, cifrador=None, ruta=None):
        self._cifrador, self.ruta = cifrador, Path(ruta) if ruta else user_data_dir() / "hmi_secretos.dat"

    def _c(self):
        if self._cifrador is None:
            self._cifrador = CifradorDPAPI()
        return self._cifrador

    def _cargar(self):
        if not self.ruta.is_file():
            return {}
        crudo = self.ruta.read_bytes()
        if not crudo.startswith(MAGIA):
            raise SecretosError("El almacén cifrado del HMI está dañado. Vuelve a guardar el token.")
        try:
            datos = json.loads(self._c().descifrar(crudo[len(MAGIA):]).decode("utf-8"))
        except SecretosError:
            raise
        except Exception:
            raise SecretosError("No se pudo descifrar el almacén (otra cuenta de Windows o archivo dañado). Vuelve a guardar el token.") from None
        return {k: v for k, v in datos.items() if k in self.CAMPOS and isinstance(v, str)} if isinstance(datos, dict) else {}

    def _guardar(self, datos):
        cifrado = MAGIA + self._c().cifrar(json.dumps(datos).encode("utf-8"))
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.ruta.parent, suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(cifrado)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.ruta)

    def token_zeno(self) -> str:
        return self._cargar().get("zeno_token", "")

    def hay_token(self) -> bool:
        try:
            return bool(self.token_zeno())
        except SecretosError:
            return False

    def guardar_token_zeno(self, token: str):
        token = (token or "").strip()
        if not 8 <= len(token) <= 200 or any(c.isspace() or ord(c) < 33 for c in token) or "," in token:
            raise SecretosError("El token no es válido (8 a 200 caracteres, sin espacios ni comas).")
        self._guardar({**self._cargar(), "zeno_token": token})

    def borrar_token_zeno(self):
        datos = self._cargar()
        datos.pop("zeno_token", None)
        self._guardar(datos)


def destruir(ruta):
    """Sobrescribe un archivo con bytes aleatorios y lo borra (mejor esfuerzo: un SSD o OneDrive pueden conservar copias)."""
    ruta = Path(ruta)
    with open(ruta, "r+b") as f:
        f.write(os.urandom(max(1, ruta.stat().st_size)))
        f.flush()
        os.fsync(f.fileno())
    ruta.unlink()
