"""Cliente del HMI para V.E.R.A. (servicio independiente). NO importa código de V.E.R.A.: solo conoce el contrato.
Si V.E.R.A. no está corriendo, no pasa nada: el HMI nunca depende de ella ni se bloquea esperándola."""
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from core.paths import user_data_dir

_SIN_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # el tráfico local nunca pasa por un proxy


class ClienteVera:
    def __init__(self, ruta=None, timeout=0.8):
        self._ruta, self.timeout = ruta, timeout

    def _config(self):
        """(puerto, token) publicados por V.E.R.A. en %APPDATA%/WESKER/vera_local.json, o None si no corre."""
        try:
            datos = json.loads(Path(self._ruta or user_data_dir() / "vera_local.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        puerto, token = datos.get("puerto") if isinstance(datos, dict) else None, datos.get("token") if isinstance(datos, dict) else None
        if isinstance(puerto, int) and not isinstance(puerto, bool) and 0 < puerto < 65536 and isinstance(token, str) and token:
            return puerto, token
        return None

    def _post(self, evento: dict) -> bool:
        cfg = self._config()
        if cfg is None:
            return False
        puerto, token = cfg
        req = urllib.request.Request(f"http://127.0.0.1:{puerto}/v1/evento", data=json.dumps(evento).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "X-Vera-Token": token}, method="POST")
        try:
            with _SIN_PROXY.open(req, timeout=self.timeout) as r:
                return r.status == 202
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def enviar(self, codigo, nivel="info", nodo="", usuario="", datos=None) -> bool:
        """Envío en segundo plano (no bloquea la interfaz). True si se programó; False si V.E.R.A. no está."""
        if self._config() is None:
            return False
        evento = {"v": 1, "codigo": codigo, "nivel": nivel, "nodo": nodo, "usuario": usuario, "datos": datos or {}}
        threading.Thread(target=self._post, args=(evento,), daemon=True).start()
        return True
