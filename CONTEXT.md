# CONTEXT.md - WESKER Platform

Archivo de relevo entre IAs (Claude / Gemini) y personas. Se actualiza después de cada cambio que funcione.

## Estado actual: v1.6.1 (Zeno 4.1: 3 estaciones, 2 rampas, módulo de calibración; HMI con panel de calibración; V.E.R.A. 0.2.0)
Escritorio PyQt5 + app web (docs/) + nube Supabase. El instalador se compila en GitHub Actions al subir una etiqueta v*.

### Pantallas del escritorio (menú lateral)
- **Conectados**: sesiones activas (nube). Sin cambios de comportamiento.
- **Albert (dosificadora)**: gemelo portado del proyecto original + panel con estado, recetas, modo manual/automático y simulación.
- **Zeno (AGV)**: gemelo portado + telemetría, recorrido simulado, obstáculo y control manual.

### Zeno 4.1.0 + HMI v1.6.1: 3 estaciones, 2 rampas y calibración (reemplaza el diseño de 4 estaciones/3 servos de 1.6.0)
- **Hardware**: tracción BTS7960, servo de dirección, servo de cámara, rampa 1 (izquierda) y rampa 2 (derecha), todos MG995. PCA9685 canales 0 dirección, 1 cámara, 2 rampa 1, 3 rampa 2; respaldo GPIO 21 / 16 / 17 / 22 (`zeno/config.py`).
- **`zeno/calibracion.py`** (fuente única de todo lo ajustable): esquema con tipo, rango, unidad y valor de fábrica; JSON en `~/.config/wesker/zeno_calibracion.json`; `set` valida y aplica en vivo (rechaza, no recorta); `set_many` es todo o nada; coherencia (mínimo ≤ centro ≤ máximo, rampa abierta ≠ cerrada); `guardar()` atómico; archivo dañado/inválido → valores de fábrica (el archivo roto se aparta como `.corrupto.<ts>`). Los límites físicos de la mecánica (`config.LIMITES_FISICOS`) no son calibrables.
- **`zeno/ruta.py`** (sustituye a `Navegador` y `logistica.py`): `ST1_CARGA_R1 -> ST1_INDEXANDO -> ST1_CARGA_R2 -> SALIENDO -> SEGUIMIENTO -> (5 sensores durante debounce_interseccion_ms) -> ESCANEANDO_QR -> QR ESTACION_2: DESCARGANDO rampa 1 | ESTACION_3: rampa 2 | ESTACION_1: vuelve a ST1 -> (t_espera_descarga_s, rampa cerrada) -> SALIENDO`. Arranca y al pasar a AUTO se asume Zeno parado en la Estación 1 con las rampas bloqueadas. Sin carga NO sale (solo alarma `TIMEOUT_CARGA`); sin QR NO cruza la intersección (alarma `QR_NO_LEIDO`, se resuelve al leerlo); `ABORTAR` salta la fase. Tope `vel_auto_max` solo en órdenes automáticas.
- **Protocolo**: ver `zeno/README.md` (`CARGA_RAMPA`, `ABORTAR`, `CAL_*`, línea `RUTA:`). Compatible: un HMI viejo ignora lo nuevo; `TELEM` sigue igual (`sub` = SEGUIMIENTO o ESTACION_DESCARGA).
- **HMI**: panel «Ruta y rampas» (botones «Rampa 1/2 cargada», «Abortar fase», cámara) y ventana «Calibración…» (solo ADMIN y MAINTENANCE; construida con el esquema que manda Zeno: parámetro nuevo en Zeno = control nuevo, sin tocar el HMI; «Probar» mueve el servo en MANUAL; guardar/descartar/fábrica). Auditoría `ZENO_CAL_SET/GUARDAR/RESTAURAR/DEFECTO/ABRIR`. La URL de video lleva el token y no se registra.
- **Gemelo (3 capas)**: `ZenoDigitalTwin.logistica` = dict `fase, estacion, carga_r1, carga_r2, alarma, restante_s, backend, i2c, servos{direccion,camara,rampa1,rampa2}`; capa superior dinámica = `carga_r1/2` + servos de rampa.
- Límite conocido: el panel es del HMI de escritorio (PyQt5). La app web/PWA no puede hablar TCP con Zeno desde el navegador; haría falta una pasarela (pendiente).
- Límite conocido: el token de Zeno es compartido; el rol que puede calibrar se impone en el HMI (y queda auditado), no en Zeno.
- Probado: 128 pruebas de Zeno, 131 del repo (13 de ventanas Qt OMITIDAS: sin PyQt5 en el entorno) y 60 de V.E.R.A. SIN PROBAR: robot, PCA9685, servos y cámara reales; ventanas Qt nuevas (`ui/calibracion_dialog.py`, `ui/zeno_camara.py`, panel de rampas) solo compilan.
- Pendiente: calibrar ángulos y tiempos en el robot; cliente de Albert que mande `CARGA_RAMPA` solo; servo de cámara con GPIO vibra (usar PCA9685); calibrar `CAMARA_FOV_H`/`PAN_GANANCIA` (no están en el panel).

### Enlace HMI <-> Zeno real y registro de IPs (v1.5.0)
- **Las IPs viven en Supabase** (`supabase/04_endpoints_red.sql`): tabla `node_endpoints` (una IP por nodo y por red), RLS sin políticas (solo funciones), leen ADMIN/OPERATOR/MAINTENANCE, solo ADMIN escribe, todo cambio queda en `audit_log` (`ENDPOINT_SET`/`ENDPOINT_DELETE`). `core/nodos.py` valida (IPv4, no loopback/multicast, puerto 1-65535). Un Visor no ve la pantalla «Nodos y red».
- **Token de Zeno cifrado en el HMI**: `core/secretos_local.py` (DPAPI, `%APPDATA%\WESKER\hmi_secretos.dat`; copia deliberada de la técnica de V.E.R.A. para que sigan independientes). La pantalla Nodos importa el token desde un archivo y ofrece sobrescribirlo y borrarlo. SIN PROBAR en Windows real.
- **`core/zeno_enlace.py`** (sin Qt): hilo propio, `AUTH` + `HELLO` + `PING` cada 1 s, reconexión con espera creciente (1, 2, 4, 8, 15 s), prueba todas las redes registradas, `rechazado` NO reintenta (token equivocado), sin datos 3 s = enlace muerto, jamás expone telemetría vieja. `probar()` para el botón «Probar conexión».
- **Fuente «Zeno real (conectar por red)»** en la página de Zeno (solo roles de control): telemetría real al gemelo, órdenes manuales al robot (auditadas como `ZENO_REAL_ORDEN`), modo sincronizado con el que informa Zeno en `HELLO` (el HMI NO manda `MODE,AUTO` al conectar: el robot arrancaría solo). Publica a la nube con `origen: real`; sin enlace NO publica (los demás ven «sin señal»). Solo la PC que está en la misma red que Zeno se conecta; los demás ven por la nube.
- Probado de punta a punta contra el servidor real de `zeno/` (hardware y Qt falsos). SIN PROBAR: robot físico, ventana real, DPAPI real.
- Pendiente: Albert (el registro admite sus IPs, pero no hay cliente de Albert), auto-reporte de IP de Zeno a Supabase con credencial de dispositivo, batería y sensor de obstáculos.

### Zeno v3 (`zeno/`): nodo robusto y probado en PC (se despliega en la Raspberry, no va en el instalador del HMI)
- Reemplaza a `ZENO_V2.py` (se conserva). Mismos pines, velocidades, tiempos y formato de telemetría; la decisión `V2` es idéntica a la del archivo original en las 32 combinaciones (prueba contra sus reglas). `--logica NUEVA` = lógica del script de prueba con el sensor nuevo (9 de 31 combinaciones deciden distinto; la tabla está en `PASOS_ZENO_V3.md`). Falta que el dueño elija con una prueba en pista.
- Fallos de V2 corregidos (verificados leyendo el código y con pruebas de red reales): un `ConnectionResetError` terminaba el programa; en MANUAL un enlace muerto dejaba el último movimiento (el PING se ignoraba); una excepción en el hilo de navegación dejaba el motor con el último movimiento; `listen(1)` con un solo cliente bloqueaba la reconexión; comandos partidos entre paquetes se perdían; `DIAG_PULSE` sin límite; sin autenticación; IP fija en el código; el QR se perdía en cuadros sueltos (parada repetida); JPEG codificado sin espectadores.
- Protección: vigilancia de enlace en MANUAL (2 s sin órdenes ni PING = paro), supervisor del bucle de navegación, token `AUTH` opcional (archivo `~/.config/wesker/zeno_token`, o `ZENO_TOKEN`), video con token.
- SIN PROBAR con hardware real: GPIO, motor, servo, cámara y QR (solo con falsos). Hay que seguir `PASOS_ZENO_V3.md` empezando con las ruedas en el aire.
- Pendiente de hardware: pull-down en RPWM/LPWM del BTS7960, paro físico, y no hay sensor de obstáculos (la distancia es una constante de 35 cm, como en V2).
- Próximo paso: elegir la lógica de seguimiento en pista, cliente de Albert y auto-reporte de IP de Zeno.

### V.E.R.A. 0.2.0: secretos cifrados y diagnóstico (se publica con `git push`, sin etiqueta: V.E.R.A. no va en el instalador)
- Problema reportado: la voz de ElevenLabs no sonaba y la consola no mostraba errores. Causa del silencio: V.E.R.A. 0.1 no imprimía nada por evento y guardaba los fallos del proveedor solo en `ultimo_error`; además, si el `.env` no se leía, el motor caía en silencio a `silencioso` sin avisar. La causa concreta en la máquina del usuario NO estaba identificada al entregar esta versión: la determina `python -m vera --diagnostico`.
- Ahora: cada evento y cada error salen en consola (`logging`, sin secretos); aviso explícito si el motor es `silencioso`; los eventos omitidos por enfriamiento también se registran; el adaptador de ElevenLabs muestra lo que responde el proveedor (HTTP + estado + mensaje, con la clave eliminada).
- `vera/secretos.py`: almacén cifrado con DPAPI de Windows (`%APPDATA%\WESKER\vera_secretos.dat`), atado a la cuenta de Windows, sin contraseña y sin dependencias. SIN PROBAR en Windows real (aquí solo se probó la lógica con un cifrador falso). Comandos: `--guardar-secretos`, `--migrar-env` (verifica que descifra ANTES de destruir el .env), `--borrar-secretos`, `--diagnostico`.
- `vera/config.py`: prioridad entorno > almacén > `.env` > defecto, con registro de ORIGEN de cada dato; lee `.env` en UTF-8, UTF-8 con BOM y UTF-16 (PowerShell).
- `scripts/verificar_secretos.py`: bloquea commits con `.env`, claves (Telegram, ElevenLabs, Supabase service_role, llaves privadas); `--instalar-hook` lo conecta a git; probado con un repositorio real.
- ALERTA: el proyecto del usuario vive dentro de OneDrive (`...\OneDrive\Escritorio\wesker-platform`): un `.env` allí ya se sincronizó a la nube. La clave de ElevenLabs debe rotarse después de migrar.

### HMI, audio y V.E.R.A. (v1.4.0)
- **HMI**: `ui/hmi.py` (barra de estado con logo, estado de la planta, nodos EN LÍNEA/SIN SEÑAL, nube, reloj, usuario; registro de eventos de la sesión; fondo propio; hoja de estilos con botones grandes). F11 = pantalla completa (letra y botones más grandes, para pantalla táctil); Esc sale. «En línea» significa que alguien publica ese nodo (simulación hoy, hardware mañana). El historial compartido y permanente llega con la pantalla Planta.
- `MainWindow.evento(nivel, texto, codigo, nodo)` es el punto único de eventos: registro visible + sonido (si es error) + aviso a V.E.R.A. (si hay código). Anti-repetición de 5 s; las alertas de nodo/nube se disparan solo al CAMBIAR de estado.
- **Audio**: `core/audio_eventos.py` (lógica sin Qt) y `ui/audio.py` (QSoundEffect para WAV, QMediaPlayer para MP3/OGG; QtMultimedia se carga al primer uso). Eventos: `login_ok`, `login_fallo`, `error_sistema`. Búsqueda: `%APPDATA%\WESKER\sonidos\` > `desktop\assets\sonidos\` > `desktop\assets\sonidos\base\` (tonos de ejemplo propios, `scripts/generar_sonidos_base.py`). Preferencias en `%APPDATA%\WESKER\preferencias.json`. `WESKER_SIN_AUDIO=1` silencia (pruebas/CI). Diagnóstico en `%APPDATA%\WESKER\audio.log`. SIN PROBAR en el .exe real.
- Icono: `ui/branding.py` fija el AppUserModelID de Windows (icono correcto en la barra de tareas); el icono del .exe sale de `--icon` en release.yml.
- **V.E.R.A.** vive en `vera/` como paquete independiente (su propio requirements, pruebas y README). El HMI solo conoce el contrato `vera/CONTRATO.md` mediante `core/vera_cliente.py` (HTTP local, en segundo plano, silencioso si V.E.R.A. no corre; una prueba impide que `desktop/` importe código de `vera/`). Puerto de voz `MotorVoz`; adaptador de ElevenLabs sin probar con una cuenta real; sin voz por defecto (`VERA_MOTOR=silencioso`).
- **Voz «Dalia»**: en el proyecto original era la voz sintética de Microsoft `es-MX-DaliaNeural` (edge-tts), NO una persona. Clonar una voz exige consentimiento de su dueño y el proveedor lo verifica. Decisión pendiente del dueño del proyecto: voz propia con consentimiento, voz de la biblioteca del proveedor o voz diseñada.

### Identidad visual y seguridad (v1.3.0)
- **Marca propia, sin material de terceros.** Los fondos originales traían el emblema de Umbrella Corporation (marca de Capcom) y NO deben subirse al repo público ni al instalador. Todo se genera por código: `scripts/generar_marca.py` (logos W.E.S.K.E.R. y V.E.R.A. en SVG/PNG + `wesker.ico`) y `scripts/generar_fondos.py` (metal oscuro + marco HUD, acento por pantalla). Los resultados viven en `desktop/assets/`.
- Significado de las siglas (para textos y futuros diseños): **W.E.S.K.E.R.** = Wireless Environment for Synchronized Kernel Execution & Routing (plataforma central). **V.E.R.A.** = Virtual Entity for Reasoning and Assistance (asistente virtual, futura IA).
- `scripts/optimizar_fondos.py --origen X --destino Y` convierte imágenes a JPEG RGB, con ancho máximo y peso máximo dinámicos (baja la calidad hasta 40 y luego reduce el tamaño). Pillow es solo para scripts; NO va en requirements.txt.
- Hoy solo la pantalla de inicio de sesión usa el fondo; las demás pantallas lo usarán al rediseñar paneles (versión Planta). Los 6 fondos ya están listos en `desktop/assets/fondos/`.
- `ui/branding.py` carga los recursos y, si falta uno, la app sigue sin él. **Para que viajen en el instalador** el workflow necesita `--add-data "desktop/assets;assets" --icon "desktop/assets/wesker.ico"` (cambio mínimo en release.yml, que es archivo intocable: se aplica con aprobación del dueño).
- `core/estado.py`: todo estado recibido de la nube se valida (tipo, rango, valores permitidos) antes de tocar un gemelo; lo inválido se descarta. Un publicador defectuoso o malicioso ya no puede romper las pantallas de los demás.
- `supabase/03_endurecimiento.sql` (opcional, recomendado): usuarios nuevos inactivos hasta que un Admin los active, y límite de 30 intentos fallidos/minuto en la bitácora.
- Pruebas de seguridad automáticas (`tests/test_seguridad.py`): ningún token, llave privada ni `service_role`; `app_config.json` solo con datos públicos; **ninguna IP fija en el código** (regla: las IPs vivirán en Supabase).
- Regla de trabajo: credenciales solo por variables de entorno (`.env`, ignorado por git) y solo del lado servidor; la URL y la clave `anon` de Supabase son públicas por diseño y van en `app_config.json`.

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
0. Probar el HMI y el audio en una ventana real; decidir la voz de V.E.R.A.
1. Pantalla **Planta**: tarjetas ONLINE/OFFLINE por nodo, estado global, historial de eventos y alertas compartidos (reemplaza Telegram).
2. Registro de nodos editable (IP por red: Casa, Equipo, Universidad).
3. Conectar nodos reales (necesito el firmware de Zeno, Albert, Estrella y Sellador).
4. Extender la prueba de humo para abrir también la ventana principal.
