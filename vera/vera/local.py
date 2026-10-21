"""Descubrimiento local: V.E.R.A. escribe su puerto y un token aleatorio (nuevo en cada arranque) en
%APPDATA%/WESKER/vera_local.json para que el HMI de esta misma PC pueda hablarle. Nada de esto se versiona."""
import json
import os
import tempfile
from pathlib import Path


def ruta_local() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "WESKER" / "vera_local.json"


def publicar(puerto: int, token: str) -> Path:
    destino = ruta_local()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=destino.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"puerto": puerto, "token": token, "pid": os.getpid()}, f)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, destino)
    return destino


def retirar():
    try:
        datos = json.loads(ruta_local().read_text(encoding="utf-8"))
        if datos.get("pid") == os.getpid():  # solo borra el suyo
            ruta_local().unlink()
    except (OSError, ValueError):
        pass


def consultar_estado(timeout: float = 1.5):
    """Estado de la instancia de V.E.R.A. en marcha ({motor, cola, ultimo_error, en_pausa}) o None si no hay ninguna."""
    import urllib.error
    import urllib.request
    try:
        datos = json.loads(ruta_local().read_text(encoding="utf-8"))
        req = urllib.request.Request(f"http://127.0.0.1:{int(datos['puerto'])}/v1/estado",
                                     headers={"X-Vera-Token": str(datos["token"])})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return None
