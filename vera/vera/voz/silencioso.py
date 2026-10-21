from vera.voz.base import AudioSintetizado


class MotorSilencioso:
    """Sin proveedor: V.E.R.A. funciona y registra, pero no habla. Es el valor por defecto (no requiere claves)."""
    nombre = "silencioso"

    def huella(self) -> str:
        return "silencioso"

    def sintetizar(self, texto: str) -> AudioSintetizado:
        return AudioSintetizado(b"", 24000)
