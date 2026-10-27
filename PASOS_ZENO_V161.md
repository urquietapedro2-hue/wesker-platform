# Pasos: Zeno 4.1 (3 estaciones, 2 rampas, calibración) y HMI v1.6.1

Reemplaza la guía `PASOS_ZENO_V4.md` (diseño anterior de 4 estaciones). **Nada de esto se probó con el robot, el PCA9685, los servos ni la cámara reales**: se probó en PC con piezas falsas. Empieza con las ruedas en el aire.

## 1. Qué cambió
- **Máquina de estados nueva** (`zeno/ruta.py`): Estación 1 (carga rampa 1 → avance de indexación → carga rampa 2) → seguimiento de línea → intersección (5 sensores activos durante el filtro) → escaneo de QR → `ESTACION_2` abre la rampa 1, `ESTACION_3` abre la rampa 2, espera, cierra y sigue. Un QR `ESTACION_1` en una intersección reinicia el ciclo de carga.
- **Cero valores fijos de ajuste**: ángulos, tope de PWM, tiempos y filtro viven en `~/.config/wesker/zeno_calibracion.json`. Lo estructural (pines, puertos, límites físicos de seguridad) sigue en `zeno/config.py`.
- **Calibración en vivo desde el HMI** (ventana «Calibración…» en la página de Zeno, solo roles ADMIN y MAINTENANCE).
- Quitado: Estación 4, servos de estación 1–3, `CONFIRMAR`, `CARGA_COMPLETA`, `RESUME`, línea `EXTRA`.

## 2. Publicar el HMI (Windows)
1. Descomprime el ZIP **sobre** tu carpeta del proyecto (reemplaza archivos).
2. `python -m unittest discover -s tests -p "test_*.py"` (las de ventanas se omiten si no tienes PyQt5).
3. `python scripts/verificar_secretos.py` debe decir «Sin secretos».
4. `git add .` · `git commit -m "Zeno 4.1: 2 rampas, 3 estaciones y calibracion"` · `git push` · `git tag v1.6.1` · `git push origin v1.6.1`. Revisa Actions e instala.

## 3. Poner Zeno 4.1 en la Raspberry
1. Reemplaza la carpeta `zeno/` completa (tu token sigue en `~/.config/wesker/zeno_token`).
2. `python3 -m zeno --calibracion-defecto` crea el JSON con los valores de fábrica (si ya existe, no lo sobrescribe).
3. PCA9685 (opcional hoy): I2C activado en `raspi-config`, `pip3 install --break-system-packages -r zeno/requirements-pi.txt`, y `i2cdetect -y 1` debe mostrar `40`. Sin esto Zeno usa GPIO solo.
4. `python3 -m zeno`. La consola debe decir la versión `4.1.0`, el backend de servos (PCA9685 o GPIO, y por qué) y la ruta del JSON de calibración. Si el JSON estaba dañado lo avisa y usa valores de fábrica.

## 4. Cableado de servos (antes de energizar)
- Servos **solo** del Buck de 5 A; GND común con la Raspberry y el PCA9685. Nunca del 5 V de la Raspberry.
- PCA9685: `V+` al Buck, `VCC` a 3.3 V, `SDA` GPIO2 (pin 3), `SCL` GPIO3 (pin 5). Canales: **0 dirección, 1 cámara, 2 rampa 1, 3 rampa 2**.
- Respaldo GPIO (señal): dirección **21**, cámara **16**, rampa 1 **17**, rampa 2 **22**.
- Pendiente de la v3: pull-down en RPWM/LPWM del BTS7960 y paro físico de emergencia.

## 5. Calibrar (con las rampas SIN carga y la mecánica a la vista)
1. En el HMI: Nodos y red → IP de Zeno → página Zeno → fuente «Zeno real» → **Calibración…**.
2. Pasa Zeno a **Manual** (el botón «Probar» solo mueve servos en manual).
3. Orden recomendado:
   - **Dirección**: «Probar» el centro (ruedas rectas). Ajusta «Ajuste fino mecánico» si el brazo del servo quedó desfasado. Luego mínimo (derecha) y máximo (izquierda). Si Zeno gira al revés, activa «Invertir izquierda/derecha». Los límites físicos son 45°–135°.
   - **Cámara**: centro (mira al frente), mínimo y máximo del barrido. Velocidad del barrido y, si gira al revés, «Invertir sentido».
   - **Rampa 1 / Rampa 2**: «Bloqueo» (retiene la carga) y «Liberación» (suelta). Prueba cada uno con «Probar». Deben diferir al menos 5°.
   - **Tracción automática**: baja «Límite de PWM» hasta que Zeno siga la línea sin pasarse. Solo recorta lo automático; el manual no se limita.
   - **Temporizadores**: «Espera con la rampa abierta» (20 s), «Pulso del avance de indexación» y su PWM (mueve a Zeno lo justo para alinear la rampa 2), «Avance ciego al salir» (que cruce la marca de la intersección sin volver a detectarla).
   - **Filtro de línea**: «Tiempo con los 5 sensores activos» (150 ms de partida). Súbelo si un brillo o un empalme de cinta lo detiene en falso; bájalo si pasa de largo la intersección.
4. Los cambios se aplican **al instante** pero solo viven en memoria. Pulsa **Guardar en Zeno** para escribirlos en el JSON. «Descartar cambios» vuelve a lo guardado; «Valores de fábrica» carga los de fábrica (también hay que guardar).
5. Si Zeno rechaza un valor (fuera de rango o incoherente, por ejemplo mínimo mayor que el centro), el panel muestra el motivo y no cambia nada. Para mover mínimo y centro a la vez, hazlo en el orden que mantenga mínimo ≤ centro ≤ máximo.

## 6. Prueba de la ruta (ruedas en el aire, luego en pista)
1. Al pasar a **Automático** (o al arrancar) Zeno se queda quieto, con las rampas bloqueadas. Panel: «Estación 1: esperando carga de la rampa 1». Aunque vea la línea no avanza.
2. Pulsa **Rampa 1 cargada** → hace el avance de indexación y se detiene → «esperando carga de la rampa 2». Pulsa **Rampa 2 cargada** → sale y sigue la línea.
3. En cada intersección se detiene (tras el filtro), la cámara barre y lee el QR. Textos exactos de los QR: `ESTACION_1`, `ESTACION_2`, `ESTACION_3`.
   - `ESTACION_2`: abre la rampa 1, cuenta la espera (el panel la muestra), la cierra y sigue.
   - `ESTACION_3`: igual con la rampa 2.
4. Si la carga tarda más de lo programado o no se lee el QR, el panel marca alarma, Zeno **sigue detenido** y no cruza. Se resuelve cargando / leyendo el QR, o con **Abortar fase** (cruza la intersección sin descargar / sale de la Estación 1 sin carga completa).
5. Cambiar a Manual a mitad de un ciclo lo cancela; al volver a Automático se reinicia en la Estación 1.

## 7. Límites que debes conocer
- El panel de calibración es del HMI de escritorio. La app web/PWA no puede hablar TCP con Zeno desde el navegador; para calibrar desde la web haría falta una pasarela (no incluida).
- El token de Zeno es compartido: quien lo tenga puede mandar `CAL_*`. Que solo ADMIN y MAINTENANCE calibren lo impone el HMI y queda en la auditoría (`ZENO_CAL_*`), no Zeno.
- Con GPIO los servos usan PWM por software: los que se mantienen energizados (cámara y rampas en bloqueo) pueden vibrar. En producción usa el PCA9685.
- Zeno sigue sin sensor de obstáculos ni batería. Albert no tiene cliente: «Rampa 1/2 cargada» son botones del HMI.
- Para quien rehaga el gemelo: `ZenoDigitalTwin.logistica` trae fase, estación, `carga_r1/2`, alarma, tiempo restante y ángulos de servos (ver `CONTEXT.md`).
