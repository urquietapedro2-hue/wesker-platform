"""Sonidos de eventos (inicio de sesión, fallos, errores de sistema). Todo es opcional y silencioso ante cualquier
fallo: el audio nunca debe romper la aplicación. Los archivos se buscan según core/audio_eventos.py."""
import os
import time

from core import preferencias
from core.audio_eventos import Enfriamiento, buscar_sonido, carpetas_de_sonido
from core.paths import resource_path, user_data_dir


class GestorAudio:
    def __init__(self):
        self.prefs = preferencias.cargar()
        self._enfriamiento = Enfriamiento()
        self._objetos = {}        # ruta -> objeto de Qt, se reutiliza para no recargar el archivo
        self._disponible = False if os.environ.get("WESKER_SIN_AUDIO") == "1" else None  # None = aún sin comprobar
        self._anotados = set()

    def activo(self) -> bool:
        return self.prefs["audio_activo"]

    def set_activo(self, valor: bool):
        self.prefs["audio_activo"] = bool(valor)
        preferencias.guardar(self.prefs)

    def volumen(self) -> int:
        return self.prefs["volumen"]

    def set_volumen(self, valor: int):
        self.prefs["volumen"] = max(0, min(100, int(valor)))
        preferencias.guardar(self.prefs)

    def reproducir(self, evento: str) -> bool:
        """True si se mandó a reproducir. Nunca lanza excepciones."""
        try:
            if not self.activo() or self._disponible is False or not self._enfriamiento.permitido(evento):
                return False
            ruta = buscar_sonido(evento, carpetas_de_sonido(user_data_dir(), resource_path("assets")))
            return False if ruta is None else self._tocar(ruta)
        except Exception as ex:
            self._anotar(ex)
            return False

    def _anotar(self, ex):
        """Diagnóstico mínimo: un renglón por tipo de error en %APPDATA%/WESKER/audio.log (el audio nunca rompe la app)."""
        if type(ex).__name__ in self._anotados:
            return
        self._anotados.add(type(ex).__name__)
        try:
            with open(user_data_dir() / "audio.log", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {type(ex).__name__}: {ex}\n")
        except OSError:
            pass

    def _tocar(self, ruta) -> bool:
        objeto = self._objetos.get(ruta)
        if objeto is None:
            objeto = self._crear(ruta)
            if objeto is None:
                return False
            self._objetos[ruta] = objeto
        if ruta.suffix.lower() == ".wav":       # QSoundEffect: volumen 0.0 a 1.0
            objeto.setVolume(self.volumen() / 100.0)
        else:                                    # QMediaPlayer: volumen 0 a 100
            objeto.setVolume(self.volumen())
            objeto.stop()
        objeto.play()
        return True

    def _crear(self, ruta):
        try:
            from PyQt5 import QtCore, QtMultimedia  # se importa al primer uso, no al arrancar
        except ImportError as ex:
            self._disponible = False
            self._anotar(ex)  # típico si el instalador no incluyó QtMultimedia
            return None
        url = QtCore.QUrl.fromLocalFile(str(ruta))
        if ruta.suffix.lower() == ".wav":
            efecto = QtMultimedia.QSoundEffect()
            efecto.setSource(url)
            return efecto
        reproductor = QtMultimedia.QMediaPlayer()
        reproductor.setMedia(QtMultimedia.QMediaContent(url))
        return reproductor


_gestor = None


def gestor() -> GestorAudio:
    global _gestor
    if _gestor is None:
        _gestor = GestorAudio()
    return _gestor


def reproducir(evento: str) -> bool:
    return gestor().reproducir(evento)
