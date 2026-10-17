"""Actualizaciones por GitHub Releases: detecta, descarga, verifica SHA-256 e instala en silencio."""
import hashlib
import os
import subprocess
import tempfile

import requests

INSTALLER_NAME = "WESKER-Setup.exe"


def parse_version(v: str) -> tuple:
    parts = [int(p) for p in v.strip().lstrip("v").split(".")[:3]]
    return tuple(parts + [0] * (3 - len(parts)))


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def check_latest(repo: str, timeout: float = 6.0):
    """Devuelve {version, installer_url, sha_url} de la última release, o None si no hay o no hay red."""
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest",
                         headers={"Accept": "application/vnd.github+json"}, timeout=timeout)
        if r.status_code != 200:
            return None
        data = r.json()
        assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
        if INSTALLER_NAME not in assets or f"{INSTALLER_NAME}.sha256" not in assets:
            return None
        return {"version": data["tag_name"].lstrip("v"), "installer_url": assets[INSTALLER_NAME],
                "sha_url": assets[f"{INSTALLER_NAME}.sha256"]}
    except (requests.RequestException, ValueError, KeyError):
        return None


def download_and_verify(info: dict) -> str:
    """Descarga el instalador y lo borra si el hash no coincide."""
    expected = requests.get(info["sha_url"], timeout=15).text.split()[0].strip().lower()
    path = os.path.join(tempfile.mkdtemp(prefix="wesker_upd_"), INSTALLER_NAME)
    digest = hashlib.sha256()
    with requests.get(info["installer_url"], stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                digest.update(chunk)
    if digest.hexdigest() != expected:
        os.remove(path)
        raise RuntimeError("El archivo descargado no coincide con su firma SHA-256.")
    return path


def launch_installer(path: str):
    """Instalación silenciosa; el instalador cierra la app y la vuelve a abrir."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"], creationflags=flags)
