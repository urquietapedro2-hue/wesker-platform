import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import verificar_secretos as vs  # noqa: E402

CLAVE_11 = ("sk_" + "0123456789abcdef" * 3).encode()          # claves FALSAS armadas al vuelo
TELEGRAM = (b"1234567890:" + b"A" * 35)


def jwt(rol):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=")  # noqa: E731
    return b({"alg": "HS256"}) + b"." + b({"role": rol, "ref": "x"}) + b"." + b"firmafirmafirma"


class TestRevision(unittest.TestCase):
    def test_nombres_prohibidos(self):
        for ruta in (".env", "vera/.env", ".env.local", "a/b/.env.produccion", "vera_secretos.dat", "x/vera_secretos_v2.dat",
                     "llave.pem", "k.KEY", "cert.pfx"):
            self.assertIsNotNone(vs.nombre_prohibido(ruta), ruta)
        for ruta in (".env.example", "vera/.env.example", "main.py", "envio.py", "README.md", "environment.yml"):
            self.assertIsNone(vs.nombre_prohibido(ruta), ruta)

    def test_detecta_secretos_en_el_contenido_sin_imprimirlos(self):
        archivos = {"a.py": b"KEY = '" + CLAVE_11 + b"'", "b.txt": TELEGRAM, "c.md": b"-----BEGIN RSA PRIVATE KEY-----\nxx",
                    "d.json": b'{"k": "' + jwt("service_role") + b'"}', "e.txt": b"sb_secret_abcdefghijklmnop"}
        hallazgos = vs.revisar(archivos)
        self.assertEqual(len(hallazgos), 5)
        texto = "\n".join(hallazgos)
        for secreto in (CLAVE_11.decode(), TELEGRAM.decode(), "service_role_x"):
            self.assertNotIn(secreto, texto)

    def test_lo_legitimo_pasa(self):
        self.assertEqual(vs.revisar({"ok.py": b"x = 1", "cfg.json": b'{"k": "' + jwt("anon") + b'"}',
                                     "vera/.env.example": b"ELEVENLABS_API_KEY=", "img.bin": b"\x00" + CLAVE_11,
                                     "grande.txt": b"x" * (vs.LIMITE + 1) + CLAVE_11}), [])

    def test_env_vacio_o_binario_con_nombre_prohibido_se_marca_igual(self):
        self.assertEqual(len(vs.revisar({".env": b""})), 1)
        self.assertEqual(len(vs.revisar({".env": None})), 1)


@unittest.skipUnless(shutil.which("git") and shutil.which("sh"), "hace falta git y sh")
class TestHookReal(unittest.TestCase):
    """Repositorio temporal real: se instala el hook y se intenta hacer commit con y sin secretos."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / "scripts").mkdir()
        shutil.copy(RAIZ / "scripts" / "verificar_secretos.py", self.repo / "scripts")
        self.git("init", "-q")
        self.git("config", "user.email", "t@t.t")
        self.git("config", "user.name", "t")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True)

    def instalar(self):
        r = subprocess.run([sys.executable, "scripts/verificar_secretos.py", "--instalar-hook"], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # el hook busca `python`; en esta máquina se fuerza a usar el mismo intérprete de las pruebas
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text(hook.read_text().replace('PY=$(command -v python || command -v python3 || command -v py)', f'PY="{sys.executable}"'))

    def test_bloquea_env_y_claves_y_deja_pasar_lo_limpio(self):
        self.instalar()
        (self.repo / ".env").write_text("VERA_MOTOR=silencioso\n")
        self.git("add", ".env")
        r = self.git("commit", "-m", "malo")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("COMMIT BLOQUEADO", r.stdout + r.stderr)
        self.git("reset", "-q")
        (self.repo / "codigo.py").write_text("CLAVE = '" + CLAVE_11.decode() + "'\n")
        self.git("add", "codigo.py")
        r = self.git("commit", "-m", "malo2")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn(CLAVE_11.decode(), r.stdout + r.stderr)
        self.git("reset", "-q")
        (self.repo / "limpio.py").write_text("x = 1\n")
        self.git("add", "limpio.py")
        self.assertEqual(self.git("commit", "-m", "bien").returncode, 0)

    def test_respeta_un_hook_ajeno(self):
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho ajeno\n")
        r = subprocess.run([sys.executable, "scripts/verificar_secretos.py", "--instalar-hook"], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("echo ajeno", hook.read_text())


if __name__ == "__main__":
    unittest.main()
