"""Cliente mínimo de Supabase (Auth + RPC) por REST. Sin SDK, sin secretos: solo la anon key pública."""
import time

import requests


class AuthError(Exception):
    """Error mostrable al usuario."""


class SupabaseClient:
    def __init__(self, url: str, anon_key: str, timeout: float = 8.0):
        self.url = url.rstrip("/")
        self.key = anon_key
        self.timeout = timeout
        self.token = None
        self.refresh_token = None
        self.expires_at = 0.0
        self.user_id = None
        self.profile = None

    # ---------- HTTP ----------
    def _headers(self, with_token=True):
        bearer = self.token if (with_token and self.token) else self.key
        return {"apikey": self.key, "Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}

    def _request(self, method, path, with_token=True, timeout=None, **kw):
        if with_token and self.token and time.time() > self.expires_at - 60:
            self._refresh()
        try:
            return requests.request(method, f"{self.url}{path}", headers=self._headers(with_token),
                                    timeout=timeout or self.timeout, **kw)
        except requests.RequestException as ex:
            raise AuthError("Sin conexión con el servidor.") from ex

    def _rpc(self, name, args=None, with_token=True, timeout=None):
        r = self._request("POST", f"/rest/v1/rpc/{name}", with_token, timeout, json=args or {})
        if r.status_code >= 300:
            raise AuthError(f"Error del servidor ({name}): {r.status_code}")
        return r

    # ---------- sesión ----------
    def _set_session(self, data):
        self.token = data["access_token"]
        self.refresh_token = data.get("refresh_token")
        self.expires_at = time.time() + int(data.get("expires_in", 3600))
        self.user_id = data["user"]["id"]

    def _refresh(self):
        try:
            r = requests.post(f"{self.url}/auth/v1/token", params={"grant_type": "refresh_token"},
                              json={"refresh_token": self.refresh_token},
                              headers=self._headers(False), timeout=self.timeout)
        except requests.RequestException as ex:
            raise AuthError("Sin conexión con el servidor.") from ex
        if r.status_code != 200:
            self.token = None
            raise AuthError("La sesión expiró. Inicia sesión de nuevo.")
        self._set_session(r.json())

    def sign_in(self, email: str, password: str) -> dict:
        try:
            r = requests.post(f"{self.url}/auth/v1/token", params={"grant_type": "password"},
                              json={"email": email, "password": password},
                              headers=self._headers(False), timeout=self.timeout)
        except requests.RequestException as ex:
            raise AuthError("Sin conexión con el servidor.") from ex
        if r.status_code != 200:
            try:
                self._rpc("log_failed_login", {"p_email": email}, with_token=False)
            except AuthError:
                pass
            raise AuthError("Correo o contraseña incorrectos.")
        self._set_session(r.json())
        rows = self._request("GET", "/rest/v1/profiles", params={"id": f"eq.{self.user_id}", "select": "*"}).json()
        if not rows or not rows[0].get("activo", False):
            self._clear()
            raise AuthError("Tu usuario no tiene acceso. Pide al administrador que lo active.")
        self.profile = rows[0]
        self.log_event("LOGIN_OK", {"client": "desktop"})
        return self.profile

    def _clear(self):
        self.token = self.refresh_token = self.user_id = self.profile = None

    def sign_out(self):
        """Mejor esfuerzo y rápido: nunca debe colgar el cierre de la app."""
        if not self.token:
            return
        for call in (lambda: self.log_event("LOGOUT", {"client": "desktop"}, timeout=3),
                     lambda: self._rpc("leave_presence", {"p_client": "desktop"}, timeout=3),
                     lambda: self._request("POST", "/auth/v1/logout", timeout=3)):
            try:
                call()
            except AuthError:
                pass
        self._clear()

    # ---------- funciones de plataforma ----------
    def log_event(self, action: str, detail: dict = None, timeout=None):
        self._rpc("log_event", {"p_action": action, "p_detail": detail or {}}, timeout=timeout)

    def heartbeat(self, client: str, version: str):
        self._rpc("heartbeat", {"p_client": client, "p_version": version})

    def online_users(self) -> list:
        return self._rpc("online_users").json()

    def min_version(self) -> str:
        r = self._request("GET", "/rest/v1/app_settings", params={"key": "eq.min_version", "select": "value"})
        rows = r.json() if r.status_code == 200 else []
        return rows[0]["value"] if rows else "0.0.0"
