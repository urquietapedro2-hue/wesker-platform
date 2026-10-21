"""Configuración de V.E.R.A.
Prioridad por dato: variable de entorno real > almacén cifrado > archivo .env > valor por defecto.
Los secretos NO deben vivir en .env: usa `python -m vera --guardar-secretos` o `--migrar-env`."""
import io
import os
from dataclasses import dataclass, field
from pathlib import Path

MOTORES = ("silencioso", "elevenlabs")
# nombre en entorno/.env -> campo en el almacén cifrado
CAMPOS_SECRETOS = {"VERA_MOTOR": "motor", "ELEVENLABS_API_KEY": "api_key", "VERA_VOICE_ID": "voice_id",
                   "VERA_MODEL_ID": "model_id"}


class ConfigError(Exception):
    """Configuración inválida; el mensaje nunca incluye valores secretos."""


def _entero(valor, minimo, maximo, nombre):
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise ConfigError(f"{nombre} debe ser un número entero") from None
    if not minimo <= n <= maximo:
        raise ConfigError(f"{nombre} debe estar entre {minimo} y {maximo}")
    return n


def candidatos_dotenv():
    """Dónde se busca el .env: la carpeta actual y hasta 5 niveles hacia arriba, y la carpeta de V.E.R.A."""
    base = Path.cwd().resolve()
    rutas = [d / ".env" for d in [base, *base.parents][:6]] + [Path(__file__).resolve().parent.parent / ".env"]
    vistos = []
    for r in rutas:
        if r not in vistos:
            vistos.append(r)
    return vistos


def encontrar_dotenv():
    return next((r for r in candidatos_dotenv() if r.is_file()), None)


def leer_dotenv(ruta):
    """(valores, codificación, avisos). Entiende UTF-8, UTF-8 con BOM y UTF-16 (el que genera PowerShell con `>`)."""
    crudo, avisos = Path(ruta).read_bytes(), []
    if crudo.startswith(b"\xef\xbb\xbf"):
        texto, cod = crudo.decode("utf-8-sig"), "UTF-8 con BOM"
        avisos.append(".env guardado como UTF-8 con BOM: se leyó bien, pero guárdalo como UTF-8 sin BOM.")
    elif crudo.startswith((b"\xff\xfe", b"\xfe\xff")):
        texto, cod = crudo.decode("utf-16"), "UTF-16"
        avisos.append(".env guardado como UTF-16 (típico de PowerShell con '>'): se leyó bien, pero otras herramientas no lo leerían.")
    else:
        try:
            texto, cod = crudo.decode("utf-8"), "UTF-8"
        except UnicodeDecodeError:
            texto, cod = crudo.decode("cp1252", errors="replace"), "Windows-1252"
            avisos.append(".env no está en UTF-8: puede haber caracteres mal leídos.")
    try:
        from dotenv import dotenv_values
    except ImportError:
        raise ConfigError("Falta la biblioteca python-dotenv: ejecuta  pip install -r requirements.txt") from None
    return {k: v for k, v in dotenv_values(stream=io.StringIO(texto)).items() if v is not None}, cod, avisos


@dataclass(frozen=True)
class Info:
    """De dónde salió cada dato. Nunca contiene valores secretos."""
    origenes: dict = field(default_factory=dict)
    ruta_env: str = ""
    codificacion_env: str = ""
    buscado_en: tuple = ()
    avisos: tuple = ()
    almacen_existe: bool = False


@dataclass(frozen=True)
class Config:
    motor: str = "silencioso"
    api_key: str = field(default="", repr=False)  # nunca aparece en repr, logs ni mensajes de error
    voice_id: str = ""
    model_id: str = "eleven_multilingual_v2"
    puerto: int = 0                                # 0 = el sistema elige un puerto libre (solo 127.0.0.1)
    cache_dir: str = ""
    cache_max_mb: int = 50
    enfriamiento_s: float = 20.0

    @classmethod
    def desde_entorno(cls, cargar_env=True, env=None, almacen=None):
        return cls.resolver(cargar_env, env, almacen)[0]

    @classmethod
    def resolver(cls, cargar_env=True, env=None, almacen=None, ruta_env=None):
        """(Config, Info). `almacen` es un Almacen cifrado; puede lanzar SecretosError si no se puede descifrar."""
        e = os.environ if env is None else env
        guardados = almacen.cargar() if almacen is not None else {}
        archivo, ruta, cod, avisos, buscado = {}, None, "", [], ()
        if cargar_env:
            buscado = (str(ruta_env),) if ruta_env else tuple(str(r) for r in candidatos_dotenv())
            ruta = Path(ruta_env) if ruta_env else encontrar_dotenv()
            if ruta is not None and ruta.is_file():
                archivo, cod, av = leer_dotenv(ruta)
                avisos += av
            else:
                ruta = None
        origenes = {}

        def tomar(nombre, defecto=""):
            if (e.get(nombre) or "").strip():
                origenes[nombre] = "variable de entorno"
                return e[nombre].strip()
            if (guardados.get(CAMPOS_SECRETOS.get(nombre, "")) or "").strip():
                origenes[nombre] = "almacén cifrado"
                return guardados[CAMPOS_SECRETOS[nombre]].strip()
            if (archivo.get(nombre) or "").strip():
                origenes[nombre] = f".env ({ruta})"
                return archivo[nombre].strip()
            origenes[nombre] = "valor por defecto"
            return defecto

        motor = tomar("VERA_MOTOR", "silencioso").lower()
        if motor not in MOTORES:
            raise ConfigError(f"VERA_MOTOR debe ser uno de {MOTORES}")
        api_key, voice_id = tomar("ELEVENLABS_API_KEY"), tomar("VERA_VOICE_ID")
        model_id = tomar("VERA_MODEL_ID", "eleven_multilingual_v2")
        if (archivo.get("ELEVENLABS_API_KEY") or "").strip():
            avisos.append(f"Hay una clave en TEXTO PLANO en {ruta}. Ejecuta:  python -m vera --migrar-env")

        def simple(nombre, defecto):  # datos no secretos: solo entorno y .env
            return (e.get(nombre) or archivo.get(nombre) or defecto).strip()

        cfg = cls(motor=motor, api_key=api_key, voice_id=voice_id, model_id=model_id,
                  puerto=_entero(simple("VERA_PUERTO", "0"), 0, 65535, "VERA_PUERTO"),
                  cache_dir=simple("VERA_CACHE_DIR", ""),
                  cache_max_mb=_entero(simple("VERA_CACHE_MB", "50"), 1, 2000, "VERA_CACHE_MB"))
        if motor == "elevenlabs" and not (api_key and voice_id):
            raise ConfigError("Con VERA_MOTOR=elevenlabs hacen falta la clave y el voice_id (almacén cifrado, "
                              "variables de entorno o .env). Ejecuta:  python -m vera --guardar-secretos")
        return cfg, Info(origenes, str(ruta or ""), cod, buscado, tuple(avisos), bool(almacen and almacen.existe()))
