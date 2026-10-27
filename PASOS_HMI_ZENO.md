# Pasos: registrar la IP de Zeno y conectar el HMI al robot real (v1.5.0)

## Cómo funciona
1. **Las IPs no están en el código.** Un Admin las registra en la pantalla **«Nodos y red»**: una dirección por red (Casa, Equipo, Universidad…). Se guardan en Supabase, con auditoría.
2. **El HMI nunca te pregunta la IP.** Al elegir «Zeno real» prueba, por orden, todas las redes registradas para ZENO-01 hasta que una responde. Si cambias de red, solo agregas una fila.
3. **El token se guarda una vez**, **cifrado para tu cuenta de Windows**, en la PC que se conecta al robot.
4. **Solo la PC que está en la misma red que Zeno se conecta.** Los demás usuarios ven al robot por la nube en «Ver la planta», con la etiqueta «Zeno REAL».

## Pasos

### 1. Supabase (antes de publicar)
Ejecuta `supabase/04_endpoints_red.sql` en SQL Editor. Si no lo ejecutas, «Nodos y red» dirá «El registro de direcciones no está disponible».

### 2. Tu repo
1. Descomprime el ZIP sobre el repo.
2. `python -m unittest discover -s tests` y `python -m unittest discover -s zeno/tests` deben terminar en `OK`.
3. `python desktop/main.py`: inicia sesión como **Admin** y comprueba que existe la pantalla «Nodos y red».
4. Publica: `git add .`, `git commit -m "Enlace con Zeno real y registro de IPs"`, `git push`, `git tag v1.5.0`, `git push origin v1.5.0`. Revisa Actions.

### 3. En la Raspberry (Zeno v3, ruedas en el aire)
1. Averigua su IP: `hostname -I`.
2. En el router, **reserva esa IP para la Raspberry** (así no cambia). Es mejor que fijarla a mano en la Raspberry.
3. Arranca: `python3 -m zeno`. Debe decir `autenticación ACTIVA`.

### 4. El token
1. El token está en la Raspberry: `~/.config/wesker/zeno_token`. Copia ese archivo a tu PC.
2. En el HMI, **«Nodos y red» > «Importar desde archivo…»**, elige el archivo y acepta **sobrescribirlo y borrarlo**.
3. Debe decir «Token de Zeno: guardado (cifrado en esta PC)».
4. **Si el archivo estuvo en el Escritorio, Documentos o cualquier carpeta de OneDrive**, OneDrive ya lo sincronizó. Genera uno nuevo: en la Raspberry borra el archivo, ejecuta `python3 -m zeno --generar-token`, reinicia Zeno y vuelve a importarlo.
5. Nunca pegues el token en un chat ni lo dejes en un archivo suelto.

### 5. Registrar la IP (solo Admin)
En «Nodos y red»: nodo `ZENO-01`, red (por ejemplo `Casa`), la IP del paso 3, puerto `65432` > **Guardar dirección**. Selecciona la fila y pulsa **Probar conexión**: debe decir «Conectado. ZENO-01 | 4.0.0 | …».

### 6. Conectar
1. Página **Zeno (AGV)** > fuente **«Zeno real (conectar por red)»**.
2. Debe decir «Zeno real conectado por «Casa»» y el gemelo seguirá lo que haga el robot.
3. Origen: «Zeno REAL (esta PC)». El HMI **no cambia el modo del robot al conectar**: muestra el que Zeno informa.

### 7. Pruebas de seguridad (SIEMPRE con las ruedas en el aire)
1. Modo **Manual**, pulsa «Adelante»: las ruedas giran; «Alto»: se detienen. Cada orden queda en la auditoría.
2. Con «Adelante» en marcha, **cierra el HMI**: Zeno debe frenar.
3. Con «Adelante» en marcha, apaga el Wi-Fi de la PC: Zeno frena en unos 2 s.
4. Cambia la fuente a otra: se corta el enlace y el nodo se libera en la nube.
5. Con otra cuenta en otra PC: «Ver la planta» debe mostrar el gemelo con origen **Zeno REAL**; si apagas a Zeno, esa PC verá «sin señal».
6. Con un token equivocado debe decir «Zeno rechazó el token» y no reintentar.

### 8. Cambiar de red (Universidad)
Agrega otra fila `ZENO-01` con el nombre de la red nueva y su IP. No borres las anteriores: el HMI las prueba todas.

## Si algo falla
| Mensaje | Significa | Acción |
|---|---|---|
| «No hay ninguna IP de Zeno registrada» | Falta la fila en «Nodos y red» | Un Admin la agrega |
| «Zeno rechazó el token» | El token del HMI no es el de la Raspberry | Vuelve a importarlo (paso 4) |
| «No se pudo conectar…» | Zeno apagado, otra red o IP equivocada | Revisa que Zeno corra y la IP de `hostname -I` |
| «Tiempo agotado» | Firewall o red que aísla dispositivos (típico en redes de universidad) | Usa tu propio router o módem portátil |
| «El registro de direcciones no está disponible» | Falta el SQL 04 | Paso 1 |
| «Tu rol no permite esta acción» | Solo un Admin edita las IPs | Pídeselo a un Admin |

## Límites que debes conocer
- **El paro por software no es una función de seguridad.** Mantén el paro físico en la batería y las resistencias pull-down del BTS7960 (ver `zeno/README.md`).
- Solo existen botones de orden **única** (no «mantener para mover»): Zeno sigue con la última orden hasta que pulses «Alto». Lo protege el paro por falta de latido (2 s).
- La prueba de conexión y el enlace son solo para **Zeno**. El registro admite las IPs de Albert, pero aún no hay cliente de Albert.
- DPAPI solo existe en Windows y ata el token a tu cuenta: si cambias de usuario o reinstalas, vuelve a importarlo.
- Probado de punta a punta contra el servidor real de Zeno, pero con hardware y ventanas simulados: **no se probó en el robot físico, en una ventana real ni con DPAPI real**.
