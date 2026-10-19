# La sala de la reunión diaria y la emisión del token

La web entra a la sala de la daily (AGI-60) con un token que emite la API (AGI-59). Las dos
historias se desarrollaron en paralelo y se integraron con el contrato que quedó en
[api.md](api.md). Esta página dice qué espera la web de ese endpoint y qué falta verificar.

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

## Pendiente de verificar con LiveKit

AGI-59 ya está integrada y la web usa su contrato real. Falta probarlo contra un servidor de LiveKit
de verdad; cuando esté hecho, esta sección se puede borrar.

### 1. Configurar LiveKit

Llenar `AGILINA_LIVEKIT_URL`, `AGILINA_LIVEKIT_API_KEY` y `AGILINA_LIVEKIT_API_SECRET` en el `.env`
(LiveKit Cloud) y `make up`. Las claves solo las lee la API; la web no las necesita.

### 2. Verificar

- `make verify` y `make test-e2e`. Las pruebas de la sala
  ([room.spec.ts](../tests/e2e/specs/room.spec.ts)) dejan de saltarse en Chromium.
- **Firefox:** el Firefox de Playwright no estableció el audio con un LiveKit local. Con LiveKit
  Cloud (que tiene TURN) puede que sí. Si ahora pasa, se actualiza el comentario de `room.spec.ts` y
  la sección de punta a punta de [testing.md](testing.md); si no, queda documentado así.
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
