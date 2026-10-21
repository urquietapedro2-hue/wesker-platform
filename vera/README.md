# V.E.R.A. (Virtual Entity for Reasoning and Assistance)

Servicio **independiente** del HMI de WESKER: recibe eventos por un puerto local, decide qué decir y lo reproduce con voz.
Si V.E.R.A. no está corriendo, el HMI funciona igual. Se mejora, prueba y versiona por separado.

## Estructura (puertos y adaptadores)
```
vera/
  config.py     variables de entorno / .env (los secretos solo viven aquí)
  eventos.py    contrato de entrada y validación estricta
  dialogo.py    de evento a frase (hoy plantillas; aquí entrará un modelo de lenguaje)
  nucleo.py     cola, caché, enfriamiento y protección ante fallos del proveedor de voz
  cache.py      frases ya sintetizadas en disco (se pagan una sola vez)
  salida.py     reproducción (winsound en Windows, sin dependencias)
  servidor.py   HTTP solo en 127.0.0.1 con token
  voz/base.py   EL PUERTO: lo único que se exige a un proveedor (MotorVoz)
  voz/elevenlabs.py   adaptador del proveedor      voz/silencioso.py   sin voz (valor por defecto)
```

## Uso
```
cd vera
pip install -r requirements.txt
python -m vera --guardar-secretos     # clave y voice_id CIFRADOS para tu cuenta de Windows (no se muestran)
python -m vera --diagnostico          # comprueba la configuración y hace una síntesis real de prueba
python -m vera                        # arranca el servicio; la consola muestra cada evento y cada error
python -m vera --migrar-env           # si ya tenías un .env con la clave: lo cifra y destruye el .env
python -m vera --borrar-secretos      # elimina el almacén cifrado
python -m vera --probar "Hola"        # sintetiza, reproduce y termina
python -m unittest discover -s tests  # pruebas (no necesitan red ni claves)
```

## Dónde viven los secretos
Prioridad: variable de entorno > almacén cifrado (`%APPDATA%\WESKER\vera_secretos.dat`, DPAPI de Windows) > `.env` > valor por defecto.
El `.env` sigue funcionando, pero V.E.R.A. avisa si contiene una clave en texto plano. `.env` y el almacén están en `.gitignore`, y
`scripts/verificar_secretos.py --instalar-hook` hace que git bloquee cualquier commit con secretos.

## Conectar la voz (cuando exista)
1. Crear la voz en el panel del proveedor. **La clonación exige el consentimiento de la persona dueña de la voz**; el proveedor lo verifica y lo exige.
2. `python -m vera --guardar-secretos` (pide la clave sin mostrarla, el `voice_id` y el modelo).
3. `python -m vera --diagnostico`. Si algo falla, el mensaje dice qué y nunca incluye la clave.

## Cambiar de proveedor
Crear `voz/otro.py` con una clase que tenga `nombre`, `huella()` y `sintetizar(texto) -> AudioSintetizado`, y registrarla en `voz/__init__.py`.
Nada más cambia: el caché se invalida solo (la huella incluye proveedor, voz y modelo).

## Cómo falla (a propósito, sin caerse)
Sin red o límite de ritmo: tres fallos seguidos pausan la voz 60 s. Credencial rechazada o `voice_id` inválido: pausa de 10 min. En pausa, V.E.R.A. sigue
diciendo lo que ya está en caché y registrando; el estado se ve en `GET /v1/estado`.
