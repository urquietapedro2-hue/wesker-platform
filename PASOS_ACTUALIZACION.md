# Pasos de actualización: V.E.R.A. 0.2.0 (voz que no suena + secretos cifrados)

Este ZIP solo cambia `vera/`, `scripts/`, `tests/` y `CONTEXT.md`. **No cambia el HMI**: no hay que publicar versión nueva ni crear etiqueta (`git tag`).
El ZIP no contiene `.env` ni claves.

## Qué hace y qué no hace el sistema (según tu reporte)

| | Antes (V.E.R.A. 0.1) | Ahora (0.2.0) |
|---|---|---|
| Sonido `login_fallo.wav` | Lo reproduce **el HMI**, no V.E.R.A. (es un archivo local) | Igual: es independiente de la voz |
| Evento al servicio | El HMI envía `login_fallo` y V.E.R.A. lo convierte en la frase «Acceso denegado.» | Igual |
| Fallo del proveedor de voz | Se guardaba en silencio; **la consola no mostraba nada** | Se imprime en consola con el motivo del proveedor |
| Motor `silencioso` por no leer el `.env` | Silencio total sin aviso | Aviso explícito al arrancar y en el diagnóstico |
| `.env` guardado por PowerShell (UTF-16) o con BOM | No se leía → motor `silencioso` sin aviso | Se lee y se avisa |
| Eventos repetidos en menos de 20 s | Descartados sin avisar | Descartados, pero registrados en consola |
| Clave | Texto plano en `.env` | Cifrada con tu cuenta de Windows (DPAPI) |

Con tu reporte **no se puede saber cuál** de estas causas ocurre en tu equipo: el paso 3 lo determina.

## Pasos

### 1. Aplicar el ZIP
1. Cierra V.E.R.A. (Ctrl+C) y el HMI.
2. Descomprime el ZIP **sobre la carpeta del repo** y acepta reemplazar.
3. Tu `vera\.env` actual no se toca (el ZIP no lo trae).

### 2. Dependencias
```
cd vera
pip install -r requirements.txt
```

### 3. Diagnóstico (antes de cambiar nada)
```
python -m vera --diagnostico
```
Cada línea es `[OK]`, `[INFO]`, `[AVISO]` o `[FALLA]`. No imprime tu clave. Qué significa cada resultado:

| Línea | Significa | Acción |
|---|---|---|
| `[FALLA] Motor efectivo: SILENCIOSO` | V.E.R.A. no leyó `VERA_MOTOR=elevenlabs`. Mira las líneas `.env leído` / `.env no encontrado` | Haz el paso 4 |
| `[AVISO] .env guardado como UTF-16 / BOM` | Se leyó, pero otras herramientas no lo leerían | Haz el paso 4 |
| `[FALLA] ... HTTP 401` | Clave rechazada, revocada, sin cuota o cuenta restringida | Crea una clave nueva (paso 5) |
| `[FALLA] ... HTTP 402` | Tu plan no permite ese uso por API. Suele pasar con voces de la biblioteca en plan gratuito | Usa una voz propia, otra voz o un plan que lo permita |
| `[FALLA] ... HTTP 404` | Ese `voice_id` no existe en esta cuenta | Copia el `voice_id` desde «My Voices» de la cuenta dueña de la clave |
| `[FALLA] ... HTTP 400/422` | `voice_id` o modelo mal escritos | Repite `--guardar-secretos` |
| `[AVISO] ... HTTP 429/5xx` o «sin respuesta» | Fallo pasajero, límite de ritmo o sin internet | Reintenta; revisa conexión y firewall |
| `[OK] El proveedor respondió` pero no se oye | La síntesis funciona; falla la salida de audio de Windows | Revisa volumen y dispositivo de salida predeterminado |
| `en_pausa=True` en «V.E.R.A. en ejecución» | El proveedor falló antes y V.E.R.A. está en pausa | Lee «último error» y corrige la causa |

Si el diagnóstico sale con `[FALLA]`, **pégame la salida completa** (no tiene claves) y la corrijo.

### 4. Cifrar tus datos
Elige una opción:

- **Ya tienes un `.env` con la clave:** `python -m vera --migrar-env`
  Cifra la clave, el `voice_id` y el modelo, **comprueba que se descifran** y solo entonces sobrescribe y borra el `.env`.
- **Partir de cero:** `python -m vera --guardar-secretos` (la clave se escribe sin mostrarse).

Los datos quedan en `%APPDATA%\WESKER\vera_secretos.dat`: atados a **tu cuenta de Windows** (otra cuenta u otro equipo no pueden descifrarlos), fuera del repositorio y fuera de OneDrive.

Comprueba: `python -m vera --diagnostico` debe decir `Almacén cifrado: existe y se descifró` y `origen: almacén cifrado`.
Si dice «Windows no pudo cifrar los datos», avísame: es la parte que no pude probar en Windows real.

### 5. Rotar la clave (obligatorio en tu caso)
Tu proyecto está en `...\OneDrive\Escritorio\wesker-platform`: OneDrive ya sincronizó tu `.env` a la nube, que puede conservar versiones y papelera.
1. En el panel de ElevenLabs, genera una **clave nueva** (invalida la anterior).
2. `python -m vera --guardar-secretos` y escribe la clave nueva.
3. Opcional: borra las copias viejas del `.env` en OneDrive (web → Papelera y «Historial de versiones»).

### 6. Comprobar que nada secreto llegó a GitHub
```
git ls-files | findstr /i "\.env vera_secretos"
git log --all --oneline -- .env vera/.env
```
Ambos comandos deben salir **vacíos** (solo puede aparecer `.env.example`). Si el segundo muestra commits, esa clave estuvo publicada: rótala (paso 5) y pídeme ayuda para limpiar el historial.

### 7. Bloquear commits con secretos
Desde la raíz del repo:
```
python scripts\verificar_secretos.py --instalar-hook
python scripts\verificar_secretos.py --todo
```
Desde ahora git rechaza cualquier commit con `.env`, claves o llaves privadas. Para verificarlo: `echo prueba > vera\.env`, luego `git add -f vera\.env` y `git commit -m prueba`: debe decir `COMMIT BLOQUEADO`. Después `git reset`.

### 8. Probar la voz
1. Terminal 1: `cd vera` y `python -m vera`. Debe mostrar `motor: elevenlabs (origen: almacén cifrado)`.
2. Terminal 2: abre el HMI y escribe mal la contraseña.
3. En la terminal 1 debes ver, paso a paso: `evento login_fallo -> "Acceso denegado."`, `voz generada por elevenlabs (...)` y `audio reproducido`. Cualquier fallo aparece ahí con su motivo.
4. Las frases se guardan en caché: la segunda vez suena sin llamar al proveedor.
5. El evento `login_fallo` solo se anuncia una vez cada 20 s por diseño; las repeticiones aparecen como «omitido».

### 9. Pruebas
```
python -m unittest discover -s tests
cd vera
python -m unittest discover -s tests
```
Ambas deben terminar en `OK`.

### 10. Publicar los cambios
```
git add .
git commit -m "V.E.R.A. 0.2.0: secretos cifrados, diagnostico y registro visible"
git push
```
Sin etiqueta. Si el hook bloquea el commit, quita lo que indique y rota esa clave.

## Límites que debes conocer
- DPAPI solo existe en Windows y ata los datos a tu cuenta: si reinstalas Windows o cambias de usuario, vuelve a ejecutar `--guardar-secretos`. Guarda la clave en un gestor de contraseñas.
- Cualquier programa que corra con **tu** cuenta de Windows puede pedirle a Windows que descifre el archivo: esto protege contra copias, GitHub, OneDrive y otros usuarios, no contra malware que ya esté en tu sesión.
- El adaptador de ElevenLabs solo se probó con respuestas simuladas, nunca contra su servicio. Los textos de las causas de HTTP 401/402/404 son orientativos.
- Nunca pegues la clave en un chat, correo o captura.
