# Contrato HMI ↔ V.E.R.A. (versión 1)

V.E.R.A. no conoce al HMI ni el HMI a V.E.R.A.: solo comparten este contrato. Cualquiera de los dos puede cambiar por dentro
mientras respete esto.

## Descubrimiento
V.E.R.A. escribe `%APPDATA%\WESKER\vera_local.json` al arrancar (`{"puerto": N, "token": "...", "pid": N}`) y lo borra al salir.
El token es aleatorio y distinto en cada arranque; nunca se guarda en el repositorio. Si el archivo no existe, V.E.R.A. no está corriendo.

## Evento
`POST http://127.0.0.1:<puerto>/v1/evento` con las cabeceras `Content-Type: application/json` y `X-Vera-Token: <token>`.

```json
{"v": 1, "codigo": "nodo_sin_senal", "nivel": "warn", "nodo": "ZENO-01", "usuario": "", "datos": {}}
```

| campo | regla |
|---|---|
| `v` | opcional, debe ser 1 |
| `codigo` | `sesion_iniciada`, `login_fallo`, `nodo_en_linea`, `nodo_sin_senal`, `nube_perdida`, `nube_restablecida`, `error_publicacion`, `estado_invalido` |
| `nivel` | `info`, `warn` o `error` (por defecto `info`) |
| `nodo`, `usuario` | texto corto; se eliminan caracteres de control (máx. 30 y 40) |
| `datos` | objeto de hasta 10 campos con valores simples |

Respuestas: `202` aceptado (`resultado`: `encolado`, `enfriamiento` o `cola_llena`), `400` evento inválido, `401` sin token / token malo / host distinto de
127.0.0.1 o localhost, `404` ruta inexistente, `411` falta Content-Length, `413` cuerpo mayor de 4096 bytes.

`GET /v1/estado` (con token) devuelve `{ok, motor, cola, ultimo_error, en_pausa}`.

## Compatibilidad
Un código nuevo exige cambiar `vera/eventos.py` (lista permitida) y `vera/dialogo.py` (frase). V.E.R.A. ignora lo que no entiende con un 400, nunca falla.
