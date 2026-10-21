"""Adaptador de ElevenLabs. La clonación de la voz se hace en el panel del proveedor (con su verificación de
consentimiento); aquí solo se usa el `voice_id` resultante. La clave llega por configuración, nunca del código."""
import re

from vera.voz.base import AudioSintetizado, VozError, VozNoDisponible, VozTemporal

URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
FORMATO = "pcm_24000"  # PCM de 16 bits a 24 kHz: se reproduce sin decodificadores extra
FRECUENCIA = 24000
MAX_TEXTO = 500
ID_VALIDO = re.compile(r"^[A-Za-z0-9]{10,40}$")


class ElevenLabsMotor:
    nombre = "elevenlabs"

    def __init__(self, api_key, voice_id, model_id="eleven_multilingual_v2", sesion=None, timeout=15.0):
        if not api_key:
            raise VozNoDisponible("falta la clave del proveedor")
        if not ID_VALIDO.match(voice_id or ""):
            raise VozNoDisponible("voice_id con formato no válido")
        if sesion is None:
            import requests  # solo si de verdad se usa este motor
            sesion = requests.Session()
        self._api_key, self.voice_id, self.model_id = api_key, voice_id, model_id
        self._sesion, self._timeout = sesion, timeout

    def __repr__(self):  # la clave nunca se imprime
        return f"ElevenLabsMotor(voice_id={self.voice_id!r}, model_id={self.model_id!r})"

    def huella(self) -> str:
        return f"elevenlabs|{self.voice_id}|{self.model_id}|{FORMATO}"

    def _limpiar(self, texto: str) -> str:
        return texto.replace(self._api_key, "***")  # la clave jamás sale en un mensaje

    def _detalle(self, r) -> str:
        """Lo que responde el proveedor (estado y mensaje), acotado y sin secretos."""
        try:
            datos = r.json()
        except Exception:
            return ""
        d = datos.get("detail", datos) if isinstance(datos, dict) else datos
        partes = [str(d.get("status", "")), str(d.get("message", ""))] if isinstance(d, dict) else [str(d)]
        return self._limpiar(" - ".join(p for p in partes if p))[:160]

    def sintetizar(self, texto: str) -> AudioSintetizado:
        texto = (texto or "").strip()
        if not texto or len(texto) > MAX_TEXTO:
            raise VozError(f"el texto debe tener entre 1 y {MAX_TEXTO} caracteres")
        try:
            r = self._sesion.post(URL.format(voice_id=self.voice_id), params={"output_format": FORMATO},
                                  headers={"xi-api-key": self._api_key, "Content-Type": "application/json"},
                                  json={"text": texto, "model_id": self.model_id}, timeout=self._timeout)
        except Exception as ex:  # tiempo agotado, sin red, etc. (el mensaje original puede contener la URL)
            raise VozTemporal(f"sin respuesta del proveedor ({type(ex).__name__}): revisa tu conexión a internet") from None
        c = r.status_code
        if c == 200 and r.content:
            return AudioSintetizado(r.content, FRECUENCIA)
        d = self._detalle(r)
        dijo = f" El proveedor dice: {d}" if d else ""
        if c == 401:
            raise VozNoDisponible(f"HTTP 401: clave rechazada, revocada, sin cuota o cuenta con restricción.{dijo}")
        if c == 402:
            raise VozNoDisponible(f"HTTP 402: tu plan no permite este uso por API (p. ej. una voz de la biblioteca "
                                  f"en plan gratuito o el formato de audio).{dijo}")
        if c == 403:
            raise VozNoDisponible(f"HTTP 403: acceso denegado a este recurso.{dijo}")
        if c == 404:
            raise VozNoDisponible(f"HTTP 404: esa voz no existe en esta cuenta; revisa el voice_id.{dijo}")
        if c in (400, 422):
            raise VozNoDisponible(f"HTTP {c}: parámetros no válidos (voice_id, modelo o formato).{dijo}")
        if c == 429 or c >= 500:
            raise VozTemporal(f"HTTP {c}: proveedor saturado o límite de ritmo; se reintentará más tarde.{dijo}")
        raise VozError(f"respuesta inesperada del proveedor (HTTP {c}).{dijo}")
