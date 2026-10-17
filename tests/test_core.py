import hashlib
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "desktop"))

from core import updater  # noqa: E402
from core.auth import AuthError, SupabaseClient  # noqa: E402


def resp(status=200, data=None, text=""):
    r = MagicMock(status_code=status, text=text)
    r.json.return_value = data
    return r


class TestVersiones(unittest.TestCase):
    def test_comparacion(self):
        self.assertTrue(updater.is_newer("0.1.1", "0.1.0"))
        self.assertTrue(updater.is_newer("v1.0", "0.9.9"))
        self.assertFalse(updater.is_newer("0.1.0", "0.1.0"))
        self.assertFalse(updater.is_newer("0.0.9", "0.1.0"))
        self.assertTrue(updater.is_newer("0.10.0", "0.9.0"))  # numérico, no por texto


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.c = SupabaseClient("https://x.supabase.co", "anon")

    def test_login_ok_registra_auditoria(self):
        sesion = {"access_token": "t", "refresh_token": "r", "expires_in": 3600, "user": {"id": "u1"}}
        perfil = [{"id": "u1", "email": "a@b.c", "nombre": "A", "role": "ADMIN", "activo": True}]
        with patch("core.auth.requests.post", return_value=resp(200, sesion)), \
             patch("core.auth.requests.request", side_effect=[resp(200, perfil), resp(204)]) as req:
            p = self.c.sign_in("a@b.c", "pw")
        self.assertEqual(p["role"], "ADMIN")
        self.assertTrue(req.call_args[0][1].endswith("/rpc/log_event"))
        self.assertEqual(req.call_args[1]["json"]["p_action"], "LOGIN_OK")

    def test_login_fallido_registra_intento_y_no_da_sesion(self):
        with patch("core.auth.requests.post", return_value=resp(400, {})), \
             patch("core.auth.requests.request", return_value=resp(204)) as req:
            with self.assertRaises(AuthError):
                self.c.sign_in("a@b.c", "mal")
        self.assertTrue(req.call_args[0][1].endswith("/rpc/log_failed_login"))
        self.assertIsNone(self.c.token)

    def test_usuario_desactivado_no_entra(self):
        sesion = {"access_token": "t", "expires_in": 3600, "user": {"id": "u1"}}
        with patch("core.auth.requests.post", return_value=resp(200, sesion)), \
             patch("core.auth.requests.request", return_value=resp(200, [{"activo": False}])):
            with self.assertRaises(AuthError):
                self.c.sign_in("a@b.c", "pw")
        self.assertIsNone(self.c.token)

    def test_sin_red_da_mensaje_claro(self):
        import requests
        with patch("core.auth.requests.post", side_effect=requests.ConnectionError()):
            with self.assertRaisesRegex(AuthError, "Sin conexión"):
                self.c.sign_in("a@b.c", "pw")


class TestUpdater(unittest.TestCase):
    def _fake(self, contenido, sha):
        stream = MagicMock()
        stream.__enter__.return_value = stream
        stream.iter_content.return_value = [contenido]
        return (lambda url, **kw: resp(text=sha) if url.endswith(".sha256") else stream)

    def test_descarga_valida(self):
        data = b"instalador"
        info = {"installer_url": "https://h/WESKER-Setup.exe", "sha_url": "https://h/WESKER-Setup.exe.sha256"}
        with patch("core.updater.requests.get", self._fake(data, hashlib.sha256(data).hexdigest() + " WESKER-Setup.exe")):
            path = updater.download_and_verify(info)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), data)

    def test_hash_distinto_se_rechaza_y_borra(self):
        info = {"installer_url": "https://h/WESKER-Setup.exe", "sha_url": "https://h/WESKER-Setup.exe.sha256"}
        with patch("core.updater.requests.get", self._fake(b"adulterado", "0" * 64)):
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                updater.download_and_verify(info)

    def test_check_latest(self):
        rel = {"tag_name": "v0.2.0", "assets": [
            {"name": "WESKER-Setup.exe", "browser_download_url": "u1"},
            {"name": "WESKER-Setup.exe.sha256", "browser_download_url": "u2"}]}
        with patch("core.updater.requests.get", return_value=resp(200, rel)):
            self.assertEqual(updater.check_latest("o/r")["version"], "0.2.0")
        with patch("core.updater.requests.get", return_value=resp(404, {})):
            self.assertIsNone(updater.check_latest("o/r"))


if __name__ == "__main__":
    unittest.main()
