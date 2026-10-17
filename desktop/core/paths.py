"""Rutas: recursos empaquetados (solo lectura) y datos del usuario (escribibles)."""
import os
import sys
from pathlib import Path

APP_NAME = "WESKER"


def resource_path(rel: str) -> Path:
    """Archivo incluido con el programa (funciona en desarrollo y en el .exe)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel


def user_data_dir() -> Path:
    """%APPDATA%/WESKER: aquí van los datos del usuario; una actualización nunca los toca."""
    root = os.environ.get("APPDATA") or str(Path.home() / ".local" / "share")
    path = Path(root) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path
