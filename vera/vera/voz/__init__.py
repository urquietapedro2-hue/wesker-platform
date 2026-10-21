from vera.config import Config
from vera.voz.base import MotorVoz  # noqa: F401


def crear_motor(cfg: Config):
    """Único lugar que conoce a los proveedores. Para añadir uno: crear su adaptador y registrarlo aquí."""
    if cfg.motor == "elevenlabs":
        from vera.voz.elevenlabs import ElevenLabsMotor
        return ElevenLabsMotor(cfg.api_key, cfg.voice_id, cfg.model_id)
    from vera.voz.silencioso import MotorSilencioso
    return MotorSilencioso()
