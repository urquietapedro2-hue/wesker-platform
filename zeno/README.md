# ZENO-01 (firmware del nodo AGV, Raspberry Pi)

Sustituye a `ZENO_V2.py` (que se conserva). Mismos pines, mismas velocidades, mismo protocolo de telemetría y mismas decisiones
de navegación (comprobado por pruebas contra las reglas originales). Cambia lo que lo hacía caerse. Python 3.7 o superior.

```
zeno/
  config.py        pines, tiempos y puertos (sin IPs fijas ni secretos)
  logica.py        decisiones, máquina de estados del modo AUTO y protocolo (sin hardware: se prueba en una PC)
  hardware.py      motor BTS7960, servo y sensores (RPi.GPIO)
  camara.py        cámara USB, QR y video MJPEG
  servidor.py      servidor TCP: autenticación, vigilancia de enlace, reconexión
  principal.py     arranque, supervisión del bucle de navegación, --prueba-sensor y --generar-token
  cliente_prueba.py  cliente para probar Zeno desde una PC
  deploy/zeno.service  arranque automático con systemd
```

## Uso
```
python3 -m zeno --prueba-sensor        # lecturas y decisiones, SIN mover motores (tu script de prueba, integrado)
python3 -m zeno --generar-token        # crea ~/.config/wesker/zeno_token (permisos 600)
python3 -m zeno                        # arranca; --logica NUEVA para la lógica de tu prueba (por defecto V2)
python3 -m unittest discover -s zeno/tests     # pruebas (se corren en la PC, sin Raspberry)
```
Variables opcionales: `ZENO_LOGICA` (V2|NUEVA), `ZENO_TOKEN` o `ZENO_TOKEN_FILE`, `ZENO_HOST` (por defecto 0.0.0.0), `ZENO_PUERTO`, `ZENO_VIGILANCIA_S`.

## Protocolo (puerto 65432, líneas de texto terminadas en `\n`)
| El HMI envía | Efecto |
|---|---|
| `AUTH,<token>` | Obligatorio como primera línea si Zeno tiene token; si falla responde `ERR,AUTH` y cierra |
| `PING` | Responde `PONG`. Mándalo cada 1 s: en MANUAL es el latido que evita el paro de seguridad |
| `HELLO` | Responde `HELLO:ZENO-01,<versión>,<lógica>,<modo>` (así el HMI sabe en qué modo está Zeno) |
| `MODE,AUTO` / `MODE,MANUAL` | Cambia de modo y frena |
| `F,50` `B,50` `L,50` `R,50` `S` | Mover (velocidad 0 a 100); solo en MANUAL |
| `RESUME` | Sale de la estación antes de los 5 s |
| `DIAG_PULSE,F,40,300` | Pulso de diagnóstico (dirección F/B/L/R, velocidad 0-100, 50 a 3000 ms) |
| `CAM_ON` / `CAM_OFF` | Cámara |

Zeno envía 20 veces por segundo `TELEM:dir,vel,dist,s1,s2,s3,s4,s5,subestado,qr` (idéntico a V2).
Video: `http://<ip>:8080/stream.mjpg` (con token: `?t=<token>`).

## Protocolo 4.1 (ruta de 3 estaciones, rampas y calibración)
- Entrada: `CARGA_RAMPA,1|2` (la rampa quedó cargada; solo vale en su turno), `ABORTAR` (abandona la fase y sigue la línea), `PAN,AUTO|CENTRO|0-180` (solo MANUAL).
- Calibración (se aplica en vivo; solo `CAL_GUARDAR` escribe el JSON): `CAL_ESQUEMA`, `CAL_GET`, `CAL_SET,clave,valor`, `CAL_GUARDAR`, `CAL_RESTAURAR`, `CAL_DEFECTO`, `CAL_PROBAR,direccion|camara|rampa1|rampa2,grados` (solo MANUAL). Respuestas: `CAL_ESQ:[json]`, `CAL:{json}`, `CAL_ERR:texto`.
- Salida, después de cada `TELEM`: `RUTA:fase,estacion,carga_r1,carga_r2,alarma,restante_s,backend,i2c,ang_dir,ang_cam,ang_r1,ang_r2,cal_version` (`-` = servo aún sin mover).
- Calibración en disco: `~/.config/wesker/zeno_calibracion.json` (o `ZENO_CALIBRACION`). `python3 -m zeno --calibracion-defecto` lo crea con los valores de fábrica.
- Quitados respecto a 4.0: `RESUME`, `CONFIRMAR`, `CARGA_COMPLETA`, `DESCARGAR`, la línea `EXTRA` y la Estación 4.

## Qué protege
- Una desconexión brusca ya no tumba el programa (V2 terminaba entero).
- En MANUAL, sin órdenes ni PING durante `ZENO_VIGILANCIA_S` (2 s) = paro de seguridad.
- Un error en el bucle de navegación frena el motor y el bucle se recupera solo (V2: el hilo moría y Zeno seguía con el último movimiento).
- Si el bucle de navegación se cuelga más de 1 s, un supervisor frena el motor.
- Conexión nueva reemplaza a una muerta; comandos partidos entre paquetes; líneas enormes rechazadas; pulsos limitados a 3 s.
- Con token: sin `AUTH` correcto no hay telemetría ni se obedece nada, y el video también lo pide.

## Límites que no se pueden resolver con software
- El código no puede garantizar un paro si el programa muere con el PWM en alto: pon **resistencias pull-down** en las entradas RPWM/LPWM del BTS7960 y un **paro físico** en la línea de la batería.
- No hay sensor de obstáculos leído: la distancia que se informa es una constante (35 cm), igual que en V2.
