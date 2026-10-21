"""Caché en disco de frases ya sintetizadas: las frases fijas se pagan y se esperan una sola vez."""
import hashlib
import os
import wave
from pathlib import Path

from vera.voz.base import AudioSintetizado


class CacheAudio:
    def __init__(self, carpeta, max_mb=50):
        self.carpeta, self.max_bytes = Path(carpeta), max_mb * 1024 * 1024
        self.carpeta.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def clave(huella: str, texto: str) -> str:
        return hashlib.sha256(f"{huella}\n{texto}".encode("utf-8")).hexdigest()[:32]

    def obtener(self, clave: str):
        ruta = self.carpeta / f"{clave}.wav"
        if not ruta.is_file():
            return None
        try:
            with wave.open(str(ruta)) as w:
                audio = AudioSintetizado(w.readframes(w.getnframes()), w.getframerate())
            os.utime(ruta)  # «usado hace poco»: sirve para decidir qué borrar
            return audio
        except (wave.Error, EOFError, OSError):
            ruta.unlink(missing_ok=True)  # archivo dañado: se descarta y se vuelve a sintetizar
            return None

    def guardar(self, clave: str, audio: AudioSintetizado):
        if not audio.datos:
            return
        try:
            (self.carpeta / f"{clave}.wav").write_bytes(audio.a_wav())
            self._limitar()
        except OSError:
            pass  # sin caché sigue funcionando, solo más lento

    def _limitar(self):
        archivos = sorted(self.carpeta.glob("*.wav"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in archivos)
        while archivos and total > self.max_bytes:
            viejo = archivos.pop(0)
            total -= viejo.stat().st_size
            viejo.unlink(missing_ok=True)
