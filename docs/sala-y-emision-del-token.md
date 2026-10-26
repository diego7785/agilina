# La sala de la reunión diaria y la emisión del token

La web entra a la sala de la daily (AGI-60) con un token que emite la API (AGI-59). Las dos
historias se desarrollaron en paralelo y se integraron con el contrato que quedó en
[api.md](api.md). Esta página dice qué espera la web de ese endpoint y de la lista de convocados
de la pantalla de la sala (AGI-61), y qué falta verificar.

## Lo que la web espera de la API

### `POST /v1/teams/{team_id}/dailies/current/token`

Requiere tenant (`X-Agilina-Tenant`) y sesión. Sin cuerpo. Lo pide `HttpRoomAccessApi`
([http-room-access.api.ts](../web/src/app/features/ceremonies/infrastructure/http-room-access.api.ts))
**cada vez que la persona entra**: la primera vez, al pulsar **Reintentar** y una sola vez más si
LiveKit rechaza el token. La web nunca guarda ni reutiliza un token.

| Estado | `code` | Qué muestra la web |
| --- | --- | --- |
| 201 | — | Conecta a `livekit_url` con `token` |
| 403 | `not_a_team_member`, `not_a_daily_participant` | «No tienes acceso a esta sala.» y **Volver al dashboard** |
| 409 | `no_active_sprint` | El equipo no tiene sprint activo, y **Volver al dashboard** |
| 409 | `daily_not_open` | La reunión diaria no está abierta ahora, y **Volver al dashboard** |
| 503 | `room_service_unavailable` | «La sala no está disponible en este momento.» y **Reintentar** |
| Cualquier otro | — | «Algo salió mal al entrar a la sala.» y **Reintentar** |

`401 not_authenticated` y `403 account_not_active` los maneja `authInterceptor`, como en toda la web.

```json
{"room_name": "acme-3f2c9a1e-8d4b-4c7a-9e21-5b6f0d1a2c3e", "token": "eyJhbGciOi…", "expires_at": "2026-10-20T16:15:00Z", "livekit_url": "wss://agilina.livekit.cloud"}
```

Tres requisitos que el endpoint debe cumplir para que la sala funcione como está escrita:

1. **La respuesta trae `livekit_url`.** La web no tiene ninguna variable ni credencial de LiveKit
   (DoD de AGI-60): la dirección del servidor llega con el token.
2. **La ventana para unirse es la misma que la del dashboard.** El dashboard habilita «Unirse a la
   sala» desde diez minutos antes de la daily hasta quince minutos después, para quien llega tarde
   (`join_opens_at` y `join_closes_at` de `GET /v1/teams/{team_id}/dashboard`). La daily que se
   puede unir la da `joinable_daily_at`
   ([joinable_daily_at.py](../shared/src/agilina_shared/sprint_calendar/joinable_daily_at.py)): el
   endpoint elige la daily y decide si emite el token con **esa misma función** (y `join_opens_at`
   para no emitirlo antes de tiempo); fuera de la ventana responde `409 daily_not_open`.
3. **El nombre de la sala sale de `room_name_for(tenant, ceremony_id)`**
   ([room_name.py](../shared/src/agilina_shared/room_name.py)), el que el worker sabe leer.

### `GET /v1/teams/{team_id}/dailies/current/participants`

Requiere tenant, sesión, un sprint activo y que quien pide sea convocado de su daily (ser miembro
no basta, tampoco para el admin), pero no la ventana para unirse. Lo pide `HttpDailyParticipantsApi`
([http-daily-participants.api.ts](../web/src/app/features/ceremonies/infrastructure/http-daily-participants.api.ts))
en cada conexión a la sala (AGI-61), para dar nombre y correo a la lista **Participantes**. La web
espera, de cada convocado y en orden de turno, `room_identity` (la misma identidad que firma su
token, para unirlo con quien está en la sala), `full_name` y `email` (el contrato completo está en
[api.md](api.md)).

```json
{"participants": [{"room_identity": "6f1c2a9e-8b4d-4c3a-9e7f-2d5b8a1c0e93", "full_name": "Ana Pérez", "email": "ana@example.com"}]}
```

Cualquier error deja la sala igual de usable: la lista muestra solo a quienes están en la sala
(como «Participante», sin correo) y el fallo ya lo registró `httpErrorLoggingInterceptor`.

## Probar la sala contra LiveKit

Cada desarrollador usa su propio proyecto de LiveKit Cloud: `AGILINA_LIVEKIT_URL`,
`AGILINA_LIVEKIT_API_KEY` y `AGILINA_LIVEKIT_API_SECRET` en su `.env` y `make up`. Las claves solo
las lee la API (abre la sala y firma el token); la web no las necesita. Un entorno creado antes de
AGI-59 no tiene la tabla `ceremony` (la migración inicial se reescribió): se reconstruye con
`make clean` y `make up`.

Verificado contra LiveKit Cloud el 2026-10-25:

- `make test-e2e`: las tres pruebas de la sala de AGI-60
  ([room.spec.ts](../tests/e2e/specs/room.spec.ts)) pasan en Chromium contra la API real (entrar
  con el micrófono, negarlo y quedar como oyente, salir). Las cuatro de AGI-61 (la fila propia,
  las acciones, salir y el celular) todavía no se corrieron contra LiveKit.
- **Firefox no corre en Playwright:** el que trae Playwright no establece el audio (ICE) con
  LiveKit, ni local ni Cloud, tampoco por TURN. Firefox de escritorio va en la verificación manual.

Pendiente: las verificaciones manuales de AGI-135 y AGI-61; cuando estén hechas, esta lista se
puede borrar.

- **Verificación manual (AGI-135)**, con dos personas del equipo convocadas a la daily, una en Chrome
  y otra en Firefox de escritorio, con audífonos:
  1. Al pulsar **Unirse a la sala** el navegador pide el micrófono; al darlo aparecen **Conectado** y
     «Micrófono activo», y las dos personas se escuchan.
  2. Con el micrófono bloqueado (ícono a la izquierda de la dirección) y la página recargada: la
     alerta con instrucciones, la persona sigue en la sala como oyente y **Reintentar micrófono**
     funciona al permitirlo.
  3. Con la red cortada (DevTools → Network → Offline, o el wifi apagado): «Reconectando…»; si
     vuelve antes de 30 s, **Conectado**; si no, **Desconectado** con **Reintentar** y **Volver al
     dashboard**.
  4. Alguien del equipo que no está convocado a la daily ve «No tienes acceso a esta sala.».
  5. Pasada la hora de la daily, el dashboard dice «La reunión diaria ya empezó: todavía puedes
     entrar.» y la API emite el token; a los quince minutos ya no.

  La evidencia (capturas o video) va en el pull request.
- **Verificación manual de la pantalla de la sala (AGI-61)**, con tres personas convocadas a la
  daily al mismo tiempo (dos en escritorio y una en un celular, o en el modo de dispositivo de
  DevTools a 375 px de ancho) y el worker levantado con `make agent`. Lo de una sola persona ya
  lo comprueba [room.spec.ts](../tests/e2e/specs/room.spec.ts); esto es lo que necesita varias:
  1. **Altas y bajas:** cada persona que entra pasa de Desconectado a Conectado en la lista de las
     otras dos, y vuelve a Desconectado (atenuada) cuando pulsa **Salir de la sala**, que la lleva
     al dashboard. Medir el tiempo (video a 30 cuadros por segundo o marcas de tiempo): menos de
     1 s.
  2. **Quién habla:** al hablar cada una, su fila muestra el ícono de voz, «Hablando» y el anillo
     en las tres pantallas (también en la propia), en menos de 1 s, medido igual; al callar se
     apaga.
  3. **«· tú»:** cada persona ve «· tú» solo en su fila, con su nombre y su correo.
  4. **Agilina:** con `make agent`, la tarjeta Estado de Agilina dice «En la sala» y Agilina no
     aparece como fila de Participantes; cuando habla, el indicador de voz sale en la tarjeta.
     Confirmar en los registros del worker (o en la consola de LiveKit) que entra como
     participante de tipo agente (`participant.isAgent`); si no, la web la mostraría como
     «Participante».
  5. **Celular:** en 375 px la sala se apila en una columna (Estado de Agilina, Turno de,
     Participantes y Acciones), nada se desplaza de lado y **Salir de la sala** se alcanza y
     funciona.
  6. **Sin transcripción:** ninguna pantalla muestra texto de lo que se dice.

  La evidencia (el video o las capturas con las mediciones) va en el pull request.
