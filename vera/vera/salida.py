"""Salida de audio. En Windows usa winsound (biblioteca estándar); en otros sistemas no reproduce."""
import sys

from vera.voz.base import AudioSintetizado


class ReproductorWindows:
    def reproducir(self, audio: AudioSintetizado):
        import winsound
        winsound.PlaySound(audio.a_wav(), winsound.SND_MEMORY)  # bloquea hasta terminar: la cola habla de una en una


class ReproductorNulo:
    """No reproduce; cuenta lo que habría sonado (pruebas y sistemas sin audio)."""

    def __init__(self):
        self.reproducidos = []

    def reproducir(self, audio: AudioSintetizado):
        self.reproducidos.append(len(audio.datos))


def crear_reproductor():
    return ReproductorWindows() if sys.platform == "win32" else ReproductorNulo()
