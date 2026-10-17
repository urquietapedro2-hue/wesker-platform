"""Configuración pública de la app (sin secretos). settings.json en APPDATA puede sobrescribirla."""
import json

from .paths import resource_path, user_data_dir


def load_config() -> dict:
    cfg = json.loads(resource_path("app_config.json").read_text(encoding="utf-8"))
    override = user_data_dir() / "settings.json"
    if override.exists():
        cfg.update(json.loads(override.read_text(encoding="utf-8")))
    return cfg


def is_configured(cfg: dict) -> bool:
    return "TU_PROYECTO" not in cfg.get("supabase_url", "TU_PROYECTO")
