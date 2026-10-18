# CONTEXT.md - WESKER Platform

Archivo de relevo entre IAs (Claude / Gemini) y personas. Se actualiza después de cada cambio que funcione.

## Estado actual: v1.2.0 (gemelos compartidos)
Escritorio PyQt5 + app web (docs/) + nube Supabase. El instalador se compila en GitHub Actions al subir una etiqueta v*.

### Pantallas del escritorio (menú lateral)
- **Conectados**: sesiones activas (nube). Sin cambios de comportamiento.
- **Albert (dosificadora)**: gemelo portado del proyecto original + panel con estado, recetas, modo manual/automático y simulación.
- **Zeno (AGV)**: gemelo portado + telemetría, recorrido simulado, obstáculo y control manual.

### Gemelos compartidos (v1.2.0)
- Cada gemelo tiene una **fuente**: *Ver la planta* (por defecto), *Publicar mi simulación* (ADMIN/OPERATOR/MAINTENANCE) o *Local*. El VIEWER solo ve.
- Una sola persona publica cada nodo (ALBERT-01, ZENO-01). Si otra ya publica, el servidor responde `OCUPADO:nombre` y la página vuelve a «Ver». El candado caduca a los 10 s sin publicar; un ADMIN puede forzarlo (`p_force`, aún sin botón).
- Se publica cada 0.5 s (~0.55 KB). Los que miran consultan cada 1 s `get_states(p_known)`: el servidor solo reenvía el estado si su versión cambió.
- Albert: `exportar_estado()` / `importar_estado()` y **modo espejo** (`twin.espejo = True`): el espejo solo suaviza el movimiento hacia lo recibido y NO ejecuta la lógica del proceso. Zeno no necesita espejo: su telemetría ya es el estado.
- Se simplifican en el espejo: la caída del vaso desde el silo y la animación de descarga (el vaso aparece/desaparece).
- SQL nuevo: `supabase/02_estado_compartido.sql` (ejecutar ANTES de publicar la versión). `core/shared.py` (cliente, sin Qt) y `ui/shared_sync.py` (consulta y publica en hilos).
- `core/auth.py`: añadido candado para que un solo hilo renueve el token (con más consultas simultáneas era una condición de carrera).

### Decisiones tomadas
- Los gemelos (`ui/twins/`) son el código original sin cambiar su dibujo. Albert simula solo todo el proceso cuando recibe pasos (`animar_rotacion()`); Zeno es una vista pura alimentada con `set_telemetria()`.
- `core/sim.py` (sin Qt, con pruebas) hace de nodo falso: `ZenoSimulator.tick()` devuelve los argumentos exactos de `set_telemetria()`; `AlbertSimulator` solo marca el ritmo de pasos.
- Ritmo mínimo de Albert = 8 s por paso: el sellado del gemelo dura ~7 s y debe terminar antes del siguiente paso (si no, se omiten sellados).
- Roles: ADMIN/OPERATOR/MAINTENANCE controlan la simulación; VIEWER solo observa (`core/permissions.py`). Iniciar/detener simulación y provocar obstáculo quedan en `audit_log` (SIM_ALBERT_*, SIM_ZENO_*).
- Los eventos de auditoría y toda la red van fuera del hilo de la GUI (`run_async`).

### Limitaciones conocidas
- Si el SQL 02 no se ejecutó, las páginas muestran «Estado compartido no disponible».
- Retardo de ~1-2 s para quien mira: sirve para monitoreo, no para control.
- Los nodos reales (ESP32/Raspberry) aún no están conectados; las rutas a `albert_client`/`sellador_client` del gemelo están inactivas a propósito.
- La prueba de humo de Actions solo abre la ventana de login; no abre la ventana principal.
- Probado: lógica (tests/test_sim.py) y ejecución de las páginas con un PyQt simulado. NO probado en una pantalla real hasta que se corra `python desktop/main.py`.

### Intocable (ver reglas): desktop/main.py, .github/workflows/release.yml, core/updater.py, core/paths.py.

## Siguiente
1. Pantalla **Planta**: tarjetas ONLINE/OFFLINE por nodo, estado global, historial de eventos y alertas compartidos (reemplaza Telegram).
2. Registro de nodos editable (IP por red: Casa, Equipo, Universidad).
3. Conectar nodos reales (necesito el firmware de Zeno, Albert, Estrella y Sellador).
4. Extender la prueba de humo para abrir también la ventana principal.
