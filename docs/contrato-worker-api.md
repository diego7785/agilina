# Contrato entre el worker y la API

El worker solo necesita dos operaciones contra la API. Todo lo demás que ocurre
durante la ceremonia se resuelve dentro del worker o por el canal de datos de
LiveKit.

| Operación | Cuándo | Qué viaja | Respuesta |
| --- | --- | --- | --- |
| `GET /v1/ceremonies/{ceremony_id}/context` | Antes de facilitar | — | `200` con `CeremonyContext` |
| `POST /v1/ceremonies/{ceremony_id}/result` | Al cerrar la ceremonia | `CeremonyResult` | `202` con `ResultReceipt` (`{"status": "received"}`) |

Los tipos viven en `shared/src/agilina_shared/contract/` y los importan los
dos desplegables: el contrato es código compartido, no documentación que se
desactualiza. Esta página explica el porqué; la forma exacta está en el tipo.
La versión del contrato es `CONTRACT_VERSION` (hoy `3.0`).

## Las dos operaciones

**Contexto.** Una sola llamada devuelve todo lo que el worker necesita para
facilitar: el `tenant`, el equipo, el sprint (`sprint_id`), el día N de M
(`sprint_day`, `sprint_total_days`), el idioma, el modo, los umbrales X e Y y
los participantes con su rol, su `room_identity` y su `turn_order` (desde 1;
el orden de turnos).

| Estado | Código | Cuándo |
| --- | --- | --- |
| 200 | — | El contexto de la ceremonia |
| 403 | `not_a_worker` | El token es válido pero es de una persona, no del worker |
| 404 | `ceremony_not_found` | La ceremonia no existe en ese tenant, su sprint ya no es el activo del equipo o está agendada antes de que empiece |

**Resultado.** Al cerrar, el worker entrega la transcripción atribuida
(`segments`, cada uno con `end_ms >= start_ms`; si no, 422 `validation_error`) y los eventos de la ceremonia (`events`, que puede venir vacía).
Cada `CeremonyEvent` tiene su tipo (`CeremonyEventType`: `ceremony_started`,
`turn_started`, `turn_ended`, `degraded`, `ceremony_closed`), su instante en
UTC (`at`) y, si es de un participante, su `user_id`.

| Estado | Código | Cuándo |
| --- | --- | --- |
| 202 | — | Resultado recibido, también cuando llega de nuevo el mismo |
| 404 | `ceremony_not_found` | Como en el contexto: la ceremonia no existe, su sprint ya no es el activo del equipo o está agendada antes de que empiece |
| 409 | `result_already_received` | La ceremonia ya tiene otro resultado |
| 422 | `validation_error` | Un segmento o un evento es de alguien que no es participante, el `ceremony_id` del cuerpo no es el del camino, o el cuerpo no cumple el contrato |

Las dos rutas comparten los errores de toda ruta con tenant, con el formato
único de error ([AD-30](adr/0030-un-solo-formato-de-error-http-y-un-catalogo-de-la-api.md)):
`400 tenant_required`, `404 tenant_not_found`, `401 not_authenticated` (antes
que cualquier `403`), `422 validation_error` y `500 internal_error`. El detalle
de cada ruta está en [api.md](api.md).

## Reglas

- **Autenticación.** El worker se autentica como servicio, con credenciales de
  cliente del cliente `agilina-worker` del realm `agilina-<tenant>`
  ([AD-29](adr/0029-un-tenant-es-una-organizacion-con-su-base-y-su-realm.md)),
  y nombra el tenant en `X-Agilina-Tenant`. Nunca usa el token de un usuario.
  Un token del worker de otro tenant responde `401`.
- **Nombre de la sala.** La sala de LiveKit se llama
  `room_name_for(tenant, ceremony_id)`, es decir `<tenant>-<ceremony_id>`. El
  worker obtiene el tenant y la ceremonia con `parse_room_name` antes de tener
  el contexto; la API usa la misma función al crear la sala. Las dos viven en
  `agilina_shared.room_name`.
- **Identidad de sala.** El `room_identity` de cada participante es
  `str(user_id)`: el token de LiveKit se firma con esa identidad y con ella se
  atribuye lo que dice.
- **Sin contexto no hay facilitación.** Pedir el contexto no reintenta: si la
  API no responde o responde con error, el worker lo anuncia en la sala y no
  facilita.
- **Idempotencia y reintento.** Entregar el mismo resultado otra vez responde
  `202` sin duplicar nada; otro resultado para la misma ceremonia responde
  `409`. «El mismo» es el mismo SHA-256 del JSON canónico del `CeremonyResult`. La entrega guarda el resultado en disco antes del primer intento
  (`<AGILINA_AGENT_PENDING_DIR>/<tenant>/<ceremony_id>.json`, por defecto en
  `infra/datos/agent-pending`, escrito en un temporal y movido con `os.replace`)
  y reintenta ante un error de transporte o un `5xx` con espera creciente: 2 s,
  duplicando hasta un tope de 60 s, mientras viva el job. Perder una ceremonia
  por un reinicio de la API no es aceptable. El archivo se borra solo con el
  `202`. Un `409` o un `422` no se reintentan: el archivo queda y el log lo
  dice. Al arrancar, el worker reenvía una vez lo que haya quedado en disco; lo
  que vuelva a fallar sigue ahí.
- **Fallar cerrado.** Un tenant cuyo slug no cumple `^[a-z][a-z0-9]{1,30}$`, o
  sin secreto del worker configurado, no pide token: el contexto se anuncia como
  no disponible. Sin secreto, la entrega queda en disco con un log de error; con
  un slug inválido no se arma ninguna ruta ni URL y la entrega falla (en la
  práctica no ocurre: sin contexto no hay facilitación ni resultado). El token
  nunca se registra en los logs.
- **Campos desconocidos.** Los modelos los rechazan. Una incompatibilidad entre
  versiones falla de inmediato en vez de perder datos en silencio.
- **Tiempos.** Todo en UTC.
- **Sin base de datos.** El worker no toca Postgres ni tiene credenciales de
  base de datos: la API es la única fuente de verdad del dominio.

## Cambiarlo

Un cambio incompatible es un `BREAKING CHANGE` declarado en el pie del commit y
sube `CONTRACT_VERSION` en `agilina_shared`. Agregar un campo opcional no lo es.

## Qué no cruza por aquí

Los controles de la ceremonia —iniciar la daily, terminar turno, cerrar— viajan
por el canal de datos de LiveKit directo al worker, que valida el permiso
contra el roster con la identidad que aporta el token firmado. No pasan por la
API y por eso no están en este contrato. Su implementación queda pendiente de
AGI-65.
