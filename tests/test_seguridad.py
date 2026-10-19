"""Reglas de seguridad como pruebas: cero credenciales y cero IPs fijas en el repositorio."""
import base64
import json
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
IGNORAR = {".git", "build", "dist", "dist_installer", "__pycache__", "node_modules", "assets"}
EXTENSIONES = {".py", ".json", ".yml", ".yaml", ".sql", ".md", ".html", ".iss", ".txt", ".toml", ".cfg"}
TOKEN_TELEGRAM = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")
LLAVE_PRIVADA = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SOLO_LOCAL = {"127.0.0.1", "0.0.0.0"}


def archivos(extensiones=EXTENSIONES, base=RAIZ):
    for p in base.rglob("*"):
        if p.is_file() and p.suffix.lower() in extensiones and not (set(p.relative_to(RAIZ).parts) & IGNORAR):
            yield p


def rol_jwt(token):
    carga = token.split(".")[1]
    carga += "=" * (-len(carga) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(carga)).get("role")
    except (ValueError, json.JSONDecodeError):
        return None


class TestSinSecretos(unittest.TestCase):
    def test_no_hay_tokens_ni_llaves_privadas(self):
        for p in archivos():
            if p.name == "test_seguridad.py":
                continue
            texto = p.read_text(encoding="utf-8", errors="ignore")
            self.assertIsNone(TOKEN_TELEGRAM.search(texto), f"token tipo Telegram en {p}")
            self.assertIsNone(LLAVE_PRIVADA.search(texto), f"llave privada en {p}")
            self.assertNotIn("sb_secret_", texto, f"clave secreta de Supabase en {p}")

    def test_ningun_jwt_es_service_role(self):
        for p in archivos():
            for token in JWT.findall(p.read_text(encoding="utf-8", errors="ignore")):
                self.assertNotEqual(rol_jwt(token), "service_role", f"clave service_role en {p}")

    def test_app_config_solo_lleva_datos_publicos(self):
        ruta = RAIZ / "desktop" / "app_config.json"
        if not ruta.exists():
            self.skipTest("no hay app_config.json en esta copia")
        cfg = json.loads(ruta.read_text(encoding="utf-8"))
        self.assertEqual(set(cfg), {"supabase_url", "supabase_anon_key", "github_repo"})
        if JWT.fullmatch(cfg["supabase_anon_key"]):
            self.assertEqual(rol_jwt(cfg["supabase_anon_key"]), "anon")


class TestSinIpsFijas(unittest.TestCase):
    def test_el_codigo_de_la_aplicacion_no_tiene_ips_fijas(self):
        for p in archivos({".py"}, RAIZ / "desktop"):
            for ip in IPV4.findall(p.read_text(encoding="utf-8", errors="ignore")):
                self.assertIn(ip, SOLO_LOCAL, f"IP fija {ip} en {p}")


if __name__ == "__main__":
    unittest.main()
