# WESKER Platform (paso 1: inicio de sesión multiusuario + actualizaciones)

Programa de escritorio (Windows) y app web que comparten **la misma nube**: mismos usuarios, mismos roles, misma lista de conectados y una bitácora de auditoría. Todo lo demás (nodos, gemelos digitales, alertas) se montará sobre esto.

```
desktop/     programa de escritorio (PyQt5)
docs/        app web (GitHub Pages sirve esta carpeta)
supabase/    schema.sql: tablas, roles, auditoría y presencia
installer/   instalador de Windows (Inno Setup)
.github/     compila y publica el instalador al crear una versión
tests/       pruebas del núcleo
```

## 1. Nube (Supabase, gratis para empezar)
1. Crea un proyecto en supabase.com.
2. SQL Editor → pega `supabase/schema.sql` → Run.
3. Authentication → desactiva el registro abierto de nuevos usuarios (los creas tú).
4. Authentication → Users → agrega un usuario con tu correo y contraseña (confírmalo automáticamente). Luego en SQL Editor:
   `update public.profiles set role='ADMIN', nombre='Pedro' where email='TU_CORREO';`
5. Settings → API: copia la **Project URL** y la clave **anon**. La anon es pública por diseño; la protección real son las reglas del esquema.
   **Nunca** pongas la clave `service_role` en este repositorio.

## 2. Configurar
Pega la URL y la clave anon en `desktop/app_config.json` y en la constante `CFG` de `docs/index.html`.
En `app_config.json` pon también tu repo en `github_repo` (`usuario/wesker-platform`).

## 3. Probar en tu PC
```
pip install -r requirements.txt
python -m unittest discover -s tests
python desktop/main.py
```

## 4. Subir a GitHub
Repositorio **público** (no contiene secretos; así el actualizador puede leer las versiones sin llevar ninguna clave).
```
git init && git add . && git commit -m "WESKER v0.1.0"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/wesker-platform.git
git push -u origin main
```
Settings → Pages → Source: *Deploy from a branch* → `main` / carpeta `/docs`. Esa URL es la app web: ábrela en el celular.

## 5. Publicar una versión (el instalador se crea solo)
```
git tag v0.1.0 && git push origin v0.1.0
```
GitHub Actions compila, crea `WESKER-Setup.exe` + su `.sha256` y los publica en Releases. Tu compañero descarga el `.exe` de la pestaña Releases e instala (no pide administrador).

## 6. Probar la actualización
Cambia algo, `git tag v0.1.1 && git push origin v0.1.1`. Al abrir el programa instalado (v0.1.0) aparece el aviso "Hay una versión nueva", descarga, verifica el hash e instala solo.
Para **obligar** a todos a actualizar: `update public.app_settings set value='0.1.1' where key='min_version';`

## Pendiente conocido
- El inicio de sesión es con **correo**, no con nombre de usuario.
- La lista de conectados se actualiza por consulta cada 15 s (escritorio) y 5 s (web); luego pasa a tiempo real.
- Si no hay internet al registrar un evento de auditoría, ese evento se pierde; la cola local llega en el siguiente paso.
- `log_failed_login` es público (necesario para registrar intentos fallidos); un atacante podría llenar la bitácora. Se limita con rate-limit más adelante.
- Las notificaciones push de la app web y la instalación como PWA llegan en el paso de alertas.
