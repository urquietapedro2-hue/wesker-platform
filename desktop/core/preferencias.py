"""Preferencias del usuario (sonido y volumen) en %APPDATA%/WESKER/preferencias.json. Escritura atómica."""
import json
import os
import tempfile

from core.paths import user_data_dir

POR_DEFECTO = {"audio_activo": True, "volumen": 80}


def _ruta():
    return user_data_dir() / "preferencias.json"


def cargar() -> dict:
    """Lee las preferencias; cualquier archivo ausente, roto o con valores raros cae a los valores por defecto."""
    prefs = dict(POR_DEFECTO)
    try:
        datos = json.loads(_ruta().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return prefs
    if isinstance(datos, dict):
        if isinstance(datos.get("audio_activo"), bool):
            prefs["audio_activo"] = datos["audio_activo"]
        v = datos.get("volumen")
        if isinstance(v, int) and not isinstance(v, bool):
            prefs["volumen"] = max(0, min(100, v))
    return prefs


def guardar(prefs: dict) -> bool:
    destino = _ruta()
    limpio = {"audio_activo": bool(prefs.get("audio_activo", True)),
              "volumen": max(0, min(100, int(prefs.get("volumen", 80))))}
    try:
        fd, tmp = tempfile.mkstemp(dir=destino.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(limpio, f)
        os.replace(tmp, destino)
        return True
    except OSError:
        return False
