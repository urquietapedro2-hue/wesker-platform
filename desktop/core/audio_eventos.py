"""Qué sonido corresponde a cada evento y dónde buscarlo. Sin Qt (se prueba solo)."""
import time
from pathlib import Path

EVENTOS = {
    "login_ok": "Inicio de sesión correcto",
    "login_fallo": "Inicio de sesión fallido",
    "error_sistema": "Error de sistema (nube caída, fallo al publicar, estado inválido, actualización fallida)",
}
EXTENSIONES = (".wav", ".mp3", ".ogg")  # orden de preferencia dentro de una misma carpeta
ENFRIAMIENTO_S = {"login_ok": 0.0, "login_fallo": 0.5, "error_sistema": 10.0}  # mínimo entre dos sonidos iguales


def carpetas_de_sonido(datos_usuario: Path, recursos: Path):
    """Prioridad: 1) %APPDATA%/WESKER/sonidos (lo tuyo, sin recompilar) 2) assets/sonidos (lo tuyo, viaja en el
    instalador) 3) assets/sonidos/base (sonidos de ejemplo generados por código)."""
    return [datos_usuario / "sonidos", recursos / "sonidos", recursos / "sonidos" / "base"]


def buscar_sonido(evento: str, carpetas):
    """Primer archivo `<evento>.wav|mp3|ogg` que exista según la prioridad de las carpetas, o None."""
    if evento not in EVENTOS:
        return None
    for carpeta in carpetas:
        for extension in EXTENSIONES:
            ruta = Path(carpeta) / f"{evento}{extension}"
            if ruta.is_file():
                return ruta
    return None


class Enfriamiento:
    """Evita que un mismo evento suene en ráfaga (p. ej. la nube caída avisando cada segundo)."""

    def __init__(self, reloj=time.monotonic):
        self._reloj, self._ultimo = reloj, {}

    def permitido(self, evento: str) -> bool:
        ahora, minimo = self._reloj(), ENFRIAMIENTO_S.get(evento, 0.0)
        if evento in self._ultimo and ahora - self._ultimo[evento] < minimo:
            return False
        self._ultimo[evento] = ahora
        return True
