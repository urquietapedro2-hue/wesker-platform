"""Puerto de voz: lo único que V.E.R.A. exige a un proveedor. Cambiar de proveedor = escribir otro adaptador."""
import io
import wave
from dataclasses import dataclass
from typing import Protocol


class VozError(Exception):
    """Fallo al sintetizar. Nunca incluye claves ni datos secretos en el mensaje."""


class VozNoDisponible(VozError):
    """Fallo que no se arregla reintentando (credencial rechazada, voz o modelo inválidos, cuota)."""


class VozTemporal(VozError):
    """Fallo pasajero (tiempo agotado, límite de ritmo, caída del servidor): se puede reintentar más tarde."""


@dataclass(frozen=True)
class AudioSintetizado:
    datos: bytes           # PCM de 16 bits, mono, little-endian
    frecuencia: int = 24000

    def a_wav(self) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.frecuencia)
            w.writeframes(self.datos)
        return buf.getvalue()


class MotorVoz(Protocol):
    nombre: str

    def huella(self) -> str:
        """Identifica proveedor+voz+modelo+formato: si cambia, el audio guardado en caché deja de valer."""

    def sintetizar(self, texto: str) -> AudioSintetizado:
        """Convierte texto en audio. Lanza VozNoDisponible, VozTemporal o VozError."""
