# CONTEXT.md - WESKER Platform

Archivo de relevo entre IAs (Claude / Gemini) y personas. Se actualiza después de cada cambio que funcione.

## Estado actual: v1.1.0 (gemelos digitales)
Escritorio PyQt5 + app web (docs/) + nube Supabase. El instalador se compila en GitHub Actions al subir una etiqueta v*.

### Pantallas del escritorio (menú lateral)
- **Conectados**: sesiones activas (nube). Sin cambios de comportamiento.
- **Albert (dosificadora)**: gemelo portado del proyecto original + panel con estado, recetas, modo manual/automático y simulación.
- **Zeno (AGV)**: gemelo portado + telemetría, recorrido simulado, obstáculo y control manual.

### Decisiones tomadas
- Los gemelos (`ui/twins/`) son el código original sin cambiar su dibujo. Albert simula solo todo el proceso cuando recibe pasos (`animar_rotacion()`); Zeno es una vista pura alimentada con `set_telemetria()`.
- `core/sim.py` (sin Qt, con pruebas) hace de nodo falso: `ZenoSimulator.tick()` devuelve los argumentos exactos de `set_telemetria()`; `AlbertSimulator` solo marca el ritmo de pasos.
- Ritmo mínimo de Albert = 8 s por paso: el sellado del gemelo dura ~7 s y debe terminar antes del siguiente paso (si no, se omiten sellados).
- Roles: ADMIN/OPERATOR/MAINTENANCE controlan la simulación; VIEWER solo observa (`core/permissions.py`). Iniciar/detener simulación y provocar obstáculo quedan en `audit_log` (SIM_ALBERT_*, SIM_ZENO_*).
- Los eventos de auditoría y toda la red van fuera del hilo de la GUI (`run_async`).

### Limitaciones conocidas
- **La simulación es local a cada PC**: dos usuarios NO ven el mismo gemelo todavía.
- Los nodos reales (ESP32/Raspberry) aún no están conectados; las rutas a `albert_client`/`sellador_client` del gemelo están inactivas a propósito.
- La prueba de humo de Actions solo abre la ventana de login; no abre la ventana principal.
- Probado: lógica (tests/test_sim.py) y ejecución de las páginas con un PyQt simulado. NO probado en una pantalla real hasta que se corra `python desktop/main.py`.

### Intocable (ver reglas): desktop/main.py, .github/workflows/release.yml, core/updater.py, core/paths.py.

## Siguiente
1. Compartir el estado del gemelo entre usuarios (publicar snapshot en la nube; los demás lo ven).
2. Registro de nodos editable (IP por ID de nodo) y simuladores como respaldo.
3. Conectar nodos reales (necesito el firmware de Zeno, Albert, Estrella y Sellador).
4. Extender la prueba de humo para abrir también la ventana principal.
