# Pasos: Zeno v3 (nodo más robusto) y lógica del sensor nuevo

Este ZIP agrega la carpeta `zeno/` (nodo) y actualiza `tests/`, `CONTEXT.md`. **No toca el HMI ni V.E.R.A.** Tu `ZENO_V2.py` se conserva como respaldo.

## Qué cambia respecto a ZENO_V2.py

| Punto | ZENO_V2.py | zeno/ (v3) |
|---|---|---|
| Desconexión brusca del HMI (`ConnectionResetError`) | Escapa del bucle y **termina el programa entero** | Se registra, frena y sigue aceptando conexiones |
| Enlace muerto en MANUAL (Wi-Fi caído sin cierre) | Sigue moviéndose con la última orden; el `PING` se ignora | Paro de seguridad a los 2 s sin órdenes ni PING |
| Error en el hilo de navegación | El hilo muere y el motor sigue con el último movimiento | Frena, registra y se recupera; un supervisor frena si se cuelga |
| Reconexión | `listen(1)` y un solo cliente: una conexión muerta bloquea a las demás | La nueva conexión reemplaza a la muerta |
| Comandos | Se parte por paquete (un comando partido se pierde); `DIAG_PULSE` sin límite de tiempo | Búfer por líneas; todo se valida; pulsos de 50 a 3000 ms |
| Acceso | Cualquiera en la red puede mover a Zeno y ver la cámara | Con token (`AUTH`) también el video; sin token avisa en consola |
| Dirección de red | IP escrita en el código | `0.0.0.0` (la IP la decide el router) |
| QR | Se pierde en cuadros sueltos y puede detenerse dos veces en la misma estación | Se mantiene 0.6 s: se evita la parada repetida |
| Video | Codifica JPEG siempre, aunque nadie mire | Solo si alguien mira |
| Pruebas | Ninguna | 62 pruebas que corren en la PC |

**Sin cambios:** pines, ángulos de dirección, velocidades, tiempos (5 s en estación, 1 s de salida), formato de telemetría y comandos.
La decisión de seguimiento `V2` es idéntica a la de tu archivo en las 32 combinaciones de sensores (lo comprueba una prueba).

## Tu sensor nuevo: dónde difieren V2 y tu script de prueba
De las 31 combinaciones de sensores (11111 es la base y ambas detienen), **9 deciden distinto** (calculado con el código real de ambas lógicas):

| Sensores S1..S5 | V2 | Lógica nueva (tu prueba) |
|---|---|---|
| 01001 | Derecha | Izquierda |
| 01011 | Derecha | Izquierda |
| 01101 | Derecha | Izquierda |
| 01111 | Derecha | Avanzar |
| 10001 | **Sin regla: mantiene el último movimiento** | Izquierda |
| 10011 | Derecha | Izquierda |
| 10101 | **Sin regla: mantiene el último movimiento** | Izquierda |
| 10111 | Derecha | Izquierda |
| 11110 | Izquierda | Avanzar |

Lectura práctica: las diferencias aparecen cuando **los dos lados ven negro a la vez** (cruces, curvas cerradas, bordes anchos).
Ahí V2 prioriza la derecha y la lógica nueva la izquierda, o avanza si los 3 sensores centrales están activos.
Elige con una prueba real en tu pista: `--logica V2` (por defecto) o `--logica NUEVA`.
Además, con **V2** las combinaciones `10001` y `10101` no tienen regla: Zeno seguiría con el último movimiento sin límite. La lógica nueva no deja ninguna sin regla.

## Pasos

### 1. En tu PC
1. Descomprime el ZIP sobre el repo.
2. `python -m unittest discover -s zeno/tests` debe terminar en `OK`. Después `python -m unittest discover -s tests`.
3. `git add .`, `git commit -m "Zeno v3"`, `git push` (sin etiqueta: Zeno no va en el instalador del HMI).

### 2. En la Raspberry (con las ruedas motrices EN EL AIRE)
1. Trae el código (`git pull` o copia la carpeta `zeno/`). Conserva `ZENO_V2.py`.
2. **Sin motores:** `python3 -m zeno --prueba-sensor`. Pasa el sensor por la pista y compara con tu script. Repite con `--logica NUEVA`.
3. Crea el token: `python3 -m zeno --generar-token`. Cópialo a tu PC por un medio seguro (nunca por chat) a `~/.config/wesker/zeno_token` o `%USERPROFILE%\.config\wesker\zeno_token`.
4. Arranca: `python3 -m zeno`. Debe decir `autenticación ACTIVA`.
5. Desde la PC: `python -m zeno.cliente_prueba IP_DE_ZENO`. Escribe `MODE,MANUAL`, luego `F,30`, luego `S`. Las ruedas giran con el robot levantado.

### 3. Pruebas de seguridad (siempre con las ruedas en el aire)
1. Con `F,30` en marcha, cierra el cliente con Ctrl+C: debe frenar al instante.
2. Con `F,30` en marcha, suspende la PC o apaga su Wi-Fi sin cerrar nada: Zeno debe frenar en unos 2 s.
3. Vuelve a conectar: debe aceptar la nueva conexión sin reiniciar el programa.
4. Prueba un token equivocado: debe rechazarlo (`ERR,AUTH`).

### 4. En pista (velocidad baja y alguien con la mano en el paro físico)
1. `python3 -m zeno` en modo AUTO. Verifica la parada en estación (5 s), la salida y que **no se detiene dos veces** en el mismo QR.
2. Cambia de lógica (`--logica NUEVA`) y repite. Decide cuál queda por defecto (variable `ZENO_LOGICA`).

### 5. Arranque automático
1. Edita `zeno/deploy/zeno.service` (`User=` y `WorkingDirectory=`).
2. `sudo cp zeno/deploy/zeno.service /etc/systemd/system/` y `sudo systemctl enable --now zeno`.
3. Reinicia la Raspberry y comprueba con `journalctl -u zeno -f`. El servicio se reinicia solo si falla.

### 6. Si algo sale mal
Detén el servicio (`sudo systemctl stop zeno`) y vuelve a `python3 ZENO_V2.py`. Pégame lo que muestre la consola.

## Recomendaciones de hardware (el software no puede cubrirlas)
- **Resistencias pull-down** en las entradas RPWM y LPWM del BTS7960: si el programa muere con el PWM en alto, el motor no debe quedar encendido.
- **Paro físico** y fusible en la línea de la batería.
- Zeno **no tiene sensor de obstáculos**: la distancia que reporta es una constante (35 cm), igual que en V2.
