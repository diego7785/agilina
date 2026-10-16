# Catálogo de la API

Cada endpoint de la API con **todas** sus respuestas posibles. Es la referencia para quien
consume la API (la web, el worker) y para quien revisa un cambio. La especificación completa
y ejecutable está en `/docs` (OpenAPI); este archivo es el resumen que se lee de corrido.

> **Se mantiene junto al código.** Un endpoint nuevo, o una respuesta nueva de uno existente,
> se documenta aquí en el mismo cambio. Una prueba (`tests/api/unit/bootstrap/test_api_catalog.py`) falla
> si una ruta no está aquí, si una ruta de aquí ya no existe, o si un código de error no está en
> el catálogo.

## Convenciones

### Cabeceras

| Cabecera | Sentido | Dónde |
| --- | --- | --- |
| `X-Agilina-Tenant` | La organización a la que se refiere la petición ([AD-29](adr/0029-un-tenant-es-una-organizacion-con-su-base-y-su-realm.md)) | Toda ruta salvo `/health*` y la documentación |
| `Authorization: Bearer <token>` | Token de acceso del tenant (Keycloak): el de la persona, o el del worker del agente en las rutas de ceremonias | Las rutas «con sesión» |
| `X-Request-ID` | Identificador de la petición. Se acepta el que envíe el cliente si tiene de 8 a 64 caracteres `A-Za-z0-9._-`; si no, la API genera uno. Siempre vuelve en la respuesta | Todas |

### El formato de un error

Todo error HTTP tiene **el mismo cuerpo**, venga de donde venga (regla de negocio, validación,
ruta inexistente o fallo inesperado):

```json
{
  "error": {
    "status": 422,
    "code": "validation_error",
    "message": "The request is not valid.",
    "details": { "fields": [{ "field": "body.password", "reason": "string_too_long" }] },
    "request_id": "c1b9f0a2e47d4c1f"
  }
}
```

| Campo | Qué es |
| --- | --- |
| `status` | El mismo número de la respuesta HTTP |
| `code` | Estable: el cliente decide por él, y la web lo traduce al idioma de la persona |
| `message` | En inglés, para desarrolladores; genérico: nunca nombra personas, invitaciones ni tenants |
| `details` | Solo cuando el código lo define (abajo). **Nunca** repite un valor enviado |
| `request_id` | El de la cabecera `X-Request-ID`; se pide al reportar un problema y aparece en el registro |

Toda respuesta de error lleva `Cache-Control: no-store`.

### Errores que puede dar cualquier endpoint

| Estado | `code` | Cuándo |
| --- | --- | --- |
| 404 | `not_found` | La ruta no existe |
| 405 | `method_not_allowed` | La ruta existe pero no con ese método |
| 500 | `internal_error` | Un fallo inesperado; el detalle queda en el registro bajo el `request_id`, nunca en la respuesta. Cada endpoint lo declara también en su tabla |

### Catálogo de códigos

| Estado | `code` | Significado | `details` |
| --- | --- | --- | --- |
| 400 | `tenant_required` | La petición no trae `X-Agilina-Tenant` | — |
| 404 | `tenant_not_found` | El tenant no existe, está suspendido o el nombre no es válido (la misma respuesta para los tres) | — |
| 401 | `not_authenticated` | Falta el token, o no es válido (firma, emisor, audiencia o vigencia). Lleva `WWW-Authenticate: Bearer` | — |
| 403 | `account_not_active` | El token es válido, pero su dueño no es usuario activo de la organización: no tiene cuenta en ella o está desactivada. La persona tiene sesión, así que la web no la manda a iniciar sesión otra vez | — |
| 403 | `not_a_team_member` | El usuario no es miembro activo del equipo (ajeno, retirado o inexistente: la misma respuesta) | — |
| 403 | `not_a_team_admin` | El usuario es miembro del equipo, pero no uno de sus admins (según el rol guardado) | — |
| 403 | `not_a_worker` | El token es válido, pero no es del worker del agente: la ruta es solo suya (`azp` distinto de `agilina-worker`) | — |
| 422 | `validation_error` | El cuerpo, un parámetro o una cabecera no es válido | `fields[]`: `{field, reason}` (en el resultado de una ceremonia, `reason` también puede ser `not_a_participant` o `does_not_match_path`) |
| 404 | `invitation_not_found` | El enlace se alteró o nunca existió | — |
| 410 | `invitation_used` | La invitación ya se usó | — |
| 410 | `invitation_expired` | La invitación venció | — |
| 410 | `invitation_revoked` | La invitación se revocó | — |
| 409 | `account_already_exists` | Ese correo ya tiene cuenta | — |
| 409 | `invitation_still_valid` | El enlace aún sirve; no hace falta pedir otro | — |
| 409 | `no_admins_to_notify` | El equipo no tiene a quién avisar | — |
| 422 | `password_policy` | La contraseña incumple la política | `reasons[]`: códigos estables |
| 422 | `password_mismatch` | La contraseña y su confirmación difieren | — |
| 503 | `identity_provider_unavailable` | El proveedor de identidad no responde | — |
| 502 | `mail_unavailable` | No se pudo enviar el correo | — |
| 422 | `invalid_team_name` | El nombre del equipo está en blanco o es demasiado largo una vez recortado | — |
| 404 | `team_not_found` | El equipo no existe | — |
| 404 | `member_not_found` | La persona no es miembro activo del equipo: nunca lo fue o ya la retiraron | — |
| 409 | `last_admin` | El cambio dejaría al equipo sin admin: a su único admin no se le baja el rol ni se le retira, tampoco por su propia mano | — |
| 409 | `sprint_in_progress` | El equipo tiene un sprint en curso: los roles no cambian mientras dure | — |
| 404 | `no_active_sprint` | El equipo no tiene un sprint activo que editar | — |
| 409 | `active_sprint_exists` | El equipo ya tiene un sprint activo: se edita, no se crea otro | — |
| 422 | `sprint_ends_before_start` | La fecha de fin del sprint es anterior a la de inicio | — |
| 422 | `invalid_time_zone` | La zona horaria no es una zona IANA conocida | — |
| 422 | `no_daily_participants` | La daily no tiene ningún participante | — |
| 422 | `duplicate_daily_participant` | Un participante de la daily aparece más de una vez | — |
| 422 | `daily_participant_not_a_member` | Un participante de la daily no es miembro activo del equipo | — |
| 422 | `invalid_email` | El correo no es una dirección válida | — |
| 422 | `invalid_full_name` | El nombre de la persona está en blanco | — |
| 409 | `already_a_team_member` | La persona ya es miembro activo del equipo | — |
| 409 | `account_disabled` | La persona tiene cuenta, pero está desactivada | — |
| 409 | `pending_invitation_exists` | Otra invitación a la misma persona se emitía en ese mismo instante | — |
| 404 | `ceremony_not_found` | La ceremonia no existe, su sprint ya no es el activo del equipo o está agendada antes de que empiece (la misma respuesta) | — |
| 409 | `result_already_received` | La ceremonia ya tiene otro resultado: se cierra una sola vez | — |

## Salud

### `GET /health`

Sonda de vida. Sin tenant, sin sesión.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | `{version, environment, status: "alive"}` | Siempre que el proceso responde |
| 500 | error `internal_error` | Fallo inesperado |

### `GET /health/ready`

Sonda de disponibilidad: comprueba la base del catálogo. Sin tenant, sin sesión.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | `{version, environment, status: "ready", database: "up"}` | La base responde |
| 503 | `{version, environment, status: "not_ready", database: "down"}` | La base no responde. **No** usa el formato de error: es el cuerpo de la sonda, que lee el orquestador |
| 500 | error `internal_error` | Fallo inesperado |

## Tenant

### `GET /v1/tenant`

Los datos públicos del tenant que nombra la petición. La web lo pregunta antes de iniciar sesión.
Requiere tenant; sin sesión.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | `{slug, display_name, language}` | El tenant existe y está activo |
| 400 | error `tenant_required` | Falta la cabecera |
| 404 | error `tenant_not_found` | No existe, está suspendido o el nombre no es válido |
| 422 | error `validation_error` | La especificación la declara porque la cabecera es un parámetro, pero es opcional: en la práctica no ocurre |
| 500 | error `internal_error` | Fallo inesperado |

## Invitaciones

Públicas: la persona aún no tiene cuenta y el token del cuerpo la autoriza. Requieren tenant. Nada
se guarda en caché. El token viaja en el cuerpo, nunca en la URL.

### `POST /v1/invitations/status`

Qué muestra la página de activación sobre un enlace. Cuerpo: `{token}`.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | `{email, full_name, role, status, expires_at}` | La invitación está pendiente |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 404 | error `invitation_not_found` | El enlace se alteró o nunca existió |
| 410 | error `invitation_used` / `invitation_expired` / `invitation_revoked` | La invitación ya no sirve |
| 422 | error `validation_error` | Cuerpo mal formado |
| 500 | error `internal_error` | Fallo inesperado |

### `POST /v1/invitations/activate`

Elige una contraseña y activa la cuenta. Cuerpo: `{token, password, confirmation}`.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 201 | `{email, team_id, role}` | La cuenta quedó activa |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 404 | error `invitation_not_found` | El enlace se alteró o nunca existió |
| 409 | error `account_already_exists` | Ese correo ya tiene cuenta |
| 410 | error `invitation_used` / `invitation_expired` / `invitation_revoked` | La invitación ya no sirve |
| 422 | error `validation_error` | Cuerpo mal formado (falta un campo, contraseña de más de 256 caracteres…) |
| 422 | error `password_mismatch` | `password` y `confirmation` difieren |
| 422 | error `password_policy` | La política la rechaza; `details.reasons` dice por qué. El enlace sigue vigente |
| 503 | error `identity_provider_unavailable` | Keycloak no responde |
| 500 | error `internal_error` | Fallo inesperado |

### `POST /v1/invitations/request-new`

Pide a los admins del equipo una invitación nueva. Cuerpo: `{token}`.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 202 | `{status: "requested"}` | Se avisó a los admins |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 404 | error `invitation_not_found` | El enlace se alteró o nunca existió |
| 409 | error `invitation_still_valid` | El enlace aún sirve |
| 409 | error `no_admins_to_notify` | Nadie a quien avisar |
| 422 | error `validation_error` | Cuerpo mal formado |
| 502 | error `mail_unavailable` | No se pudo enviar el correo |
| 500 | error `internal_error` | Fallo inesperado |

## Equipos

Quién puede hacer qué está en la [matriz de permisos](permisos.md).

Todas requieren tenant y sesión: el usuario es siempre el del token, nunca uno del cuerpo.

### `POST /v1/teams`

Crea un equipo en una sola transacción; quien lo crea queda como su `admin`. El equipo nace en
modo `support` e idioma `en`. Cuerpo: `{name}` (un campo desconocido se rechaza).

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 201 | `{id}`; cabecera `Location: /v1/teams/{id}` | Equipo creado |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 422 | error `validation_error` | Falta `name`, no es texto o hay un campo desconocido |
| 422 | error `invalid_team_name` | El nombre está en blanco o es demasiado largo una vez recortado |
| 500 | error `internal_error` | Fallo inesperado |

### `GET /v1/teams`

Los equipos del usuario, con su rol, el modo del equipo y la etiqueta visible del rol en cada uno,
ordenados por nombre sin distinguir mayúsculas. La etiqueta se resuelve equipo por equipo
([permisos](permisos.md)): `scrum_master` para el admin de un equipo en modo soporte, `admin` en
modo autónomo y `member` para un miembro; solo se muestra, los permisos siguen al `role`.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | `[{id, name, role, mode, label}]` (vacía si no tiene equipos) | Siempre que hay sesión |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 500 | error `internal_error` | Fallo inesperado |

### `GET /v1/teams/{team_id}`

Un equipo del usuario: nombre, modo, idioma y el rol de quien pregunta.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | `{id, name, mode, language, role, label}` | El usuario es miembro activo |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 403 | error `not_a_team_member` | No es miembro: ajeno, retirado o inexistente (la misma respuesta) |
| 404 | error `team_not_found` | El equipo dejó de existir entre la verificación de acceso y la lectura (solo una carrera) |
| 422 | error `validation_error` | `team_id` no es un UUID |
| 500 | error `internal_error` | Fallo inesperado |

### `GET /v1/teams/{team_id}/dashboard`

Lo que muestra el dashboard del equipo (HU-12), en una sola lectura: el equipo, su sprint activo con
el día N de M, la próxima daily con el instante desde el que se abre la sala y si la interfaz dibuja
la entrada a Configuración. Cualquier miembro activo del equipo.

- `team`: `{id, name, mode, label}`. `label` es la etiqueta de quien pregunta en este equipo (igual
  que en `GET /v1/teams/{team_id}`); solo se muestra, los permisos siguen al rol.
- `sprint`: `{number, start_date, end_date, day: {number, total, phase}}` (`number` es el del sprint en
  su equipo, como en [Sprint](#sprint); fechas de calendario
  `AAAA-MM-DD`; `day` como en [Sprint](#sprint)), o `null` si el equipo no tiene sprint activo.
- `next_ceremony`: `{type: "daily", starts_at, join_opens_at}` en UTC, o `null` si no hay sprint
  activo o la última daily ya empezó. `starts_at` es el mismo instante que `next_daily_at` de
  `GET …/sprints/active`; `join_opens_at` es diez minutos antes: desde ahí hasta `starts_at` se
  puede entrar a la sala. La daily «en curso» todavía no se modela (llega con la ceremonia como
  registro).
- `can_configure`: `true` para un admin. Solo decide si se dibuja Configuración; la API sigue
  validando el permiso en cada ruta de configuración.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | `{team, sprint, next_ceremony, can_configure}` | El usuario es miembro activo |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 403 | error `not_a_team_member` | No es miembro: ajeno, retirado o inexistente (la misma respuesta) |
| 404 | error `team_not_found` | El equipo dejó de existir entre la verificación de acceso y la lectura (solo una carrera) |
| 422 | error `validation_error` | `team_id` no es un UUID |
| 500 | error `internal_error` | Fallo inesperado |

```json
{
  "team": {"id": "6f1c…", "name": "Equipo Atlas", "mode": "support", "label": "scrum_master"},
  "sprint": {"number": 12, "start_date": "2026-10-08", "end_date": "2026-10-21",
             "day": {"number": 4, "total": 14, "phase": "in_progress"}},
  "next_ceremony": {"type": "daily", "starts_at": "2026-10-12T14:15:00Z",
                    "join_opens_at": "2026-10-12T14:05:00Z"},
  "can_configure": true
}
```

## Usuarios

Las personas de un equipo, sus roles y su retiro (HU-06), y quien llama como miembro de un equipo
(HU-04). Un usuario tiene un rol distinto en cada equipo, así que **toda ruta nombra el equipo en la
query** (`?team_id=<uuid>`). Todas requieren tenant y sesión, y las mismas respuestas de acceso en el
mismo orden: sin sesión `401`, quien no es miembro activo del equipo `403 not_a_team_member` (la
misma respuesta si el equipo es ajeno, lo retiraron o no existe) y, en las rutas de admin, un miembro
que no lo es `403 not_a_team_admin`. Falta `team_id` o no es un UUID: `422 validation_error` con
`details.fields` `query.team_id`. Quién puede hacer qué: [matriz de permisos](permisos.md).

Un usuario del equipo (`UserInTeam`) es `{user_id, full_name, email, role, label, joined_at,
role_change_blocked_by, removal_blocked_by}`. `role` es el rol interno (`admin` o `member`) y
`label` el código de la etiqueta visible en ese equipo (`scrum_master`, `admin` o `member`). Los dos
`…_blocked_by` dicen por qué no se puede cambiar el rol o retirar a esa persona ahora (`null` si se
puede), con las mismas reglas que aplican los cambios: `sprint_in_progress` (solo el cambio de rol, y
va primero) o `last_admin`.

### `GET /v1/users?team_id=…`

Los usuarios activos del equipo, para su pantalla de configuración. Solo para los admins del equipo.
Ordenados por nombre sin distinguir mayúsculas (y por correo si se repite). `roles` son los roles que
un admin puede dar, con su etiqueta.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | `{roles: [{role, label}], users: [UserInTeam]}` | Quien pregunta es admin del equipo |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 403 | error `not_a_team_member` | No es miembro: ajeno, retirado o inexistente (la misma respuesta) |
| 403 | error `not_a_team_admin` | Es miembro, pero no admin del equipo |
| 422 | error `validation_error` | Falta `team_id` o no es un UUID |
| 500 | error `internal_error` | Fallo inesperado |

### `GET /v1/users/me?team_id=…`

Quien llama, como miembro del equipo: lo que muestra el encabezado de la app. Cualquier miembro
activo, y solo para sí mismo. Responde `{user_id, full_name, email, role, label, joined_at}`.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | `{user_id, full_name, email, role, label, joined_at}` | Quien llama es miembro activo del equipo |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 403 | error `not_a_team_member` | No es miembro: ajeno, retirado o inexistente (la misma respuesta) |
| 404 | error `member_not_found` | Lo retiraron entre la verificación de acceso y la lectura (solo una carrera) |
| 422 | error `validation_error` | Falta `team_id` o no es un UUID |
| 500 | error `internal_error` | Fallo inesperado |

### `GET /v1/users/{user_id}?team_id=…`

Un usuario activo del equipo, con los mismos datos que la lista: para el detalle de una persona. Solo
para los admins del equipo.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | `UserInTeam` | Quien pregunta es admin y la persona es miembro activo |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 403 | error `not_a_team_member` | No es miembro: ajeno, retirado o inexistente (la misma respuesta) |
| 403 | error `not_a_team_admin` | Es miembro, pero no admin del equipo |
| 404 | error `member_not_found` | `user_id` no es miembro activo del equipo (nunca lo fue o lo retiraron) |
| 422 | error `validation_error` | Falta `team_id` o `team_id` / `user_id` no es un UUID |
| 500 | error `internal_error` | Fallo inesperado |

### `PATCH /v1/users/{user_id}?team_id=…`

Da otro rol interno a un miembro activo, que puede ser el mismo admin que lo pide. Solo para los
admins del equipo. Cuerpo: `{role}` (`admin` o `member`; una etiqueta como `scrum_master` no es un
rol; un campo desconocido se rechaza). Dar el rol que ya tiene no cambia nada. Queda en el registro
quién cambió qué rol a quién.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 204 | — | Rol cambiado (o ya era ese) |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 403 | error `not_a_team_member` / `not_a_team_admin` | No es miembro del equipo, o lo es pero no es admin |
| 404 | error `member_not_found` | `user_id` no es miembro activo del equipo |
| 404 | error `team_not_found` | El equipo dejó de existir entre la verificación de acceso y el cambio (solo una carrera) |
| 409 | error `sprint_in_progress` | El equipo tiene un sprint en curso; nada cambia |
| 409 | error `last_admin` | Bajaría el rol al único admin, también si se lo pide a sí mismo; nada cambia |
| 422 | error `validation_error` | Falta `team_id`, `team_id` o `user_id` no es un UUID, falta `role`, el rol no existe o hay un campo desconocido |
| 500 | error `internal_error` | Fallo inesperado |

### `DELETE /v1/users/{user_id}?team_id=…`

Retira a un miembro activo **del equipo**, que puede ser el mismo admin que lo pide. Solo para los
admins del equipo. Termina la membresía (queda como `removed`, con su fecha): **la cuenta de la
persona no se borra**, porque puede estar en otros equipos, y se la puede volver a invitar. Un sprint
en curso no lo impide. Si la persona participa en la daily del sprint activo, sale de los
participantes en el mismo cambio y quienes iban después avanzan un turno (el orden sigue desde 1, sin
huecos), aunque la daily quede sin participantes. Queda en el registro quién retiró a quién.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 204 | — | Retirado del equipo |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 403 | error `not_a_team_member` / `not_a_team_admin` | No es miembro del equipo, o lo es pero no es admin |
| 404 | error `member_not_found` | `user_id` no es miembro activo del equipo |
| 404 | error `team_not_found` | El equipo dejó de existir entre la verificación de acceso y el cambio (solo una carrera) |
| 409 | error `last_admin` | Es el único admin, también si se retira a sí mismo; nada cambia |
| 422 | error `validation_error` | Falta `team_id`, o `team_id` o `user_id` no es un UUID |
| 500 | error `internal_error` | Fallo inesperado |

### `POST /v1/users/invitations?team_id=…`

Un admin invita a una persona a su equipo (HU-06). Solo para los admins del equipo. Cuerpo:
`{full_name, email, role}`, con `role` `member` por defecto (un campo desconocido se rechaza).
Qué pasa depende del correo:

- **sin cuenta en el tenant:** se guarda una invitación y se envía su enlace de activación de
  HU-02 (`/<tenant>/activate#t=…`, de un solo uso y válido siete días); al activarlo, la persona
  entra con el rol elegido. Responde `invitation_sent`.
- **con una cuenta activa:** entra al equipo de inmediato con el rol elegido (si la habían
  retirado, vuelve) y recibe un aviso con el enlace al equipo (`/<tenant>/teams/<team_id>`), sin
  enlace de activación. Responde `member_added`.

En ambos casos, una invitación pendiente de ese correo al equipo deja de servir: se revoca (o se
marca vencida si ya había vencido). El correo se envía antes de guardar nada, así que si el
servidor de correo lo rechaza no cambia nada.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 201 | `{outcome: "invitation_sent" \| "member_added"}` | Invitación enviada o cuenta agregada al equipo |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 403 | error `not_a_team_member` / `not_a_team_admin` | No es miembro del equipo, o lo es pero no es admin |
| 404 | error `team_not_found` | El equipo dejó de existir entre la verificación de acceso y la invitación (solo una carrera) |
| 409 | error `already_a_team_member` | La persona ya es miembro activo; nada se guarda ni se envía |
| 409 | error `account_disabled` | La persona tiene una cuenta desactivada; nada se guarda ni se envía |
| 409 | error `pending_invitation_exists` | Otra invitación a la misma persona se emitía en ese mismo instante |
| 422 | error `validation_error` | Falta `team_id` o no es un UUID, falta `full_name` o `email`, el rol no existe, un texto es demasiado largo o hay un campo desconocido |
| 422 | error `invalid_email` / `invalid_full_name` | El correo no es válido o el nombre está en blanco |
| 502 | error `mail_unavailable` | No se pudo enviar el correo; nada se guarda |
| 500 | error `internal_error` | Fallo inesperado |

## Sprint

El sprint activo del equipo (HU-07): su periodo, la hora de la daily y quiénes participan en
ella, en orden de turno. Requieren tenant y sesión. Leerlo lo puede cualquier integrante; crearlo y
editarlo, solo sus admins.

El cuerpo de crear y de editar es el mismo: `{start_date, end_date, daily_time, time_zone,
participants}` (un campo desconocido se rechaza).

- `start_date` y `end_date` son fechas de calendario (`AAAA-MM-DD`), sin hora y ambas incluidas.
  Pueden caer cualquier día de la semana y cuentan todos los días del periodo.
- `daily_time` es la hora de pared de la daily como un instante con su desfase (la web envía la
  del día de inicio en UTC, `Z`), y `time_zone` es la zona IANA del navegador de quien guarda
  ([AD-31](adr/0031-guardar-la-hora-de-la-daily-en-utc-con-su-zona-de-captura.md)). Se guarda el
  instante en UTC junto con la zona; la hora de pared y el calendario del sprint («hoy») son los de
  esa zona. Guardar reemplaza la zona por la de quien guarda.
- `participants` son los `user_id` de los integrantes que participan en la daily, en orden de
  turno: el primero habla primero.

Reglas al crear y al editar (si una se incumple, no se guarda nada):

- el fin no puede ser anterior al inicio (`sprint_ends_before_start`); pueden ser el mismo día;
- `time_zone` debe ser una zona IANA conocida (`invalid_time_zone`), con sus mayúsculas exactas;
- la daily necesita al menos un participante (`no_daily_participants`), ninguno repetido
  (`duplicate_daily_participant`) y todos miembros activos del equipo
  (`daily_participant_not_a_member`). Un integrante nuevo no se agrega solo, y uno retirado sale
  de los participantes del sprint activo (ver `DELETE …/members/{user_id}`).

La respuesta de las tres rutas es el sprint activo: `{id, number, start_date, end_date, daily_time,
time_zone, next_daily_at, participants: [{user_id, turn_order}], day: {number, total, phase}}`.
`number` es el número del sprint en su equipo («Sprint 12»): 1 para el primero y, desde ahí, el mayor
que el equipo haya tenido más uno, cerrado o no (nunca se reutiliza). Lo asigna la API al guardar el
sprint y no cambia al editarlo; **no se envía**: crear o editar con un campo `number` es un `422
validation_error`. No es el día del sprint (`day.number`).
`daily_time` es el instante de anclaje en UTC; `next_daily_at`, la próxima daily en UTC, calculada
por la API con el horario de verano incluido (`null` cuando ya empezó la última del sprint), y es
la que la web muestra en la zona del navegador. `turn_order` va desde 1. `day` es el día N de M en
el momento de la petición: `total` (M) son los días del periodo; `phase` es `not_started` (N = 0),
`in_progress` (N de 1 a M) o `finished` (N = M). La fase se calcula, no se guarda: un sprint
activo puede no haber empezado o haber terminado ya.

Un sprint guardado queda `active` aunque empiece en el futuro, y mientras lo esté no cambian los
roles del equipo (`409 sprint_in_progress` en `PATCH …/members/{user_id}`). Cerrarlo es la HU-10.

### `POST /v1/teams/{team_id}/sprints`

Configura el sprint del equipo, que queda activo. Solo para los admins del equipo. Un equipo tiene
a lo sumo un sprint activo: mientras lo tenga, se edita con `PUT …/sprints/active`. La API lo
comprueba con el equipo bloqueado y un índice único parcial de la base lo respalda; si dos
peticiones simultáneas llegan a la base, la segunda recibe el mismo `active_sprint_exists`.
Esa comprobación va antes que las reglas del sprint: con un sprint activo, la respuesta es el
`409` aunque el cuerpo también incumpla alguna regla de las `422`.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 201 | El sprint activo; cabecera `Location: /v1/teams/{team_id}/sprints/active` | Sprint guardado y activo |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 403 | error `not_a_team_member` / `not_a_team_admin` | No es miembro del equipo, o lo es pero no es admin |
| 404 | error `team_not_found` | El equipo dejó de existir entre la verificación de acceso y el cambio (solo una carrera) |
| 404 | error `no_active_sprint` | El sprint se guardó, pero dejó de estar activo antes de leerlo para responder (solo una carrera) |
| 409 | error `active_sprint_exists` | El equipo ya tiene un sprint activo, o una alta simultánea tomó el mismo número; nada se guarda |
| 422 | error `validation_error` | `team_id` no es un UUID, falta un campo, una fecha o un `user_id` no es válido, `daily_time` no trae desfase o hay un campo desconocido (`number` incluido) |
| 422 | error `sprint_ends_before_start` / `invalid_time_zone` | El fin es anterior al inicio, o la zona no es una zona IANA conocida; nada se guarda |
| 422 | error `no_daily_participants` / `duplicate_daily_participant` / `daily_participant_not_a_member` | La daily no tiene participantes, uno se repite o uno no es miembro activo del equipo; nada se guarda |
| 500 | error `internal_error` | Fallo inesperado |

### `GET /v1/teams/{team_id}/sprints/active`

El sprint activo del equipo con su día N de M y su próxima daily, para cualquier integrante (el
dashboard lo usa). Sin sprint activo responde `200` con `null`: es un estado normal, no un error.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | El sprint activo, o `null` si el equipo no tiene uno | El usuario es miembro activo |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 403 | error `not_a_team_member` | No es miembro: ajeno, retirado o inexistente (la misma respuesta) |
| 404 | error `team_not_found` | El equipo dejó de existir entre la verificación de acceso y la lectura (solo una carrera) |
| 422 | error `validation_error` | `team_id` no es un UUID |
| 500 | error `internal_error` | Fallo inesperado |

### `PUT /v1/teams/{team_id}/sprints/active`

Reemplaza toda la configuración del sprint activo: periodo, hora de la daily con la zona de quien
guarda y participantes con su orden. El sprint sigue activo. Solo para los admins del equipo.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | El sprint activo, con los cambios | Sprint editado |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido |
| 403 | error `account_not_active` | Token válido de alguien que no es usuario activo de la organización |
| 403 | error `not_a_team_member` / `not_a_team_admin` | No es miembro del equipo, o lo es pero no es admin |
| 404 | error `no_active_sprint` | El equipo no tiene un sprint activo; nada cambia |
| 404 | error `team_not_found` | El equipo dejó de existir entre la verificación de acceso y el cambio (solo una carrera) |
| 422 | error `validation_error` | `team_id` no es un UUID, falta un campo, una fecha o un `user_id` no es válido, `daily_time` no trae desfase o hay un campo desconocido (`number` incluido) |
| 422 | error `sprint_ends_before_start` / `invalid_time_zone` | El fin es anterior al inicio, o la zona no es una zona IANA conocida; nada cambia |
| 422 | error `no_daily_participants` / `duplicate_daily_participant` / `daily_participant_not_a_member` | La daily no tiene participantes, uno se repite o uno no es miembro activo del equipo; nada cambia |
| 500 | error `internal_error` | Fallo inesperado |

## Ceremonias (contrato del worker)

Las dos operaciones del worker del agente ([contrato](contrato-worker-api.md)). Las usa solo él,
con el token que el cliente `agilina-worker` del realm del tenant obtiene por *client credentials*:
un token válido de una persona es `403 not_a_worker`, y uno del worker de otra organización no lo
firma el realm del tenant, así que es `401 not_authenticated`.

### `GET /v1/ceremonies/{ceremony_id}/context`

Todo lo que el worker necesita antes de entrar a la sala, en una sola llamada: el tenant (el de
`X-Agilina-Tenant`), el equipo y el sprint, el nombre de la sala (`room_name_for(tenant,
ceremony_id)`), el idioma y el modo del equipo, el día N de M del sprint en el instante en que la
ceremonia está programada (en el calendario del sprint, AD-31) y los participantes del sprint
activo en orden de turno, desde 1, con su nombre, su rol guardado y su identidad en la sala
(`str(user_id)`). Los umbrales de silencio y de turno estancado llevan los valores por defecto
del contrato.

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 200 | `CeremonyContext` (contrato en `shared/`) | El worker pide una ceremonia del sprint activo de su equipo |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido para el realm del tenant (también el del worker de otra organización) |
| 403 | error `not_a_worker` | Token válido, pero no es del worker del agente |
| 404 | error `ceremony_not_found` | La ceremonia no existe, su sprint ya no es el activo del equipo o está agendada antes de que empiece |
| 422 | error `validation_error` | `ceremony_id` no es un UUID |
| 500 | error `internal_error` | Fallo inesperado |

### `POST /v1/ceremonies/{ceremony_id}/result`

El resultado que el worker entrega al cerrar la ceremonia (cuerpo: `CeremonyResult`): la
transcripción atribuida y los eventos, que se guardan en una sola transacción. La entrega se
reconoce por el SHA-256 del JSON canónico del `CeremonyResult`, así que el worker puede reintentar
la misma sin duplicar nada. No dispara el post-procesamiento (AGI-26) ni cierra la sala (AGI-63).

| Estado | Cuerpo | Cuándo |
| --- | --- | --- |
| 202 | `ResultReceipt` (`{"status": "received"}`) | Resultado guardado, o el mismo que ya se había recibido (no se escribe nada) |
| 400 / 404 | error `tenant_required` / `tenant_not_found` | Tenant ausente o inválido |
| 401 | error `not_authenticated` | Sin token, o no es válido para el realm del tenant (también el del worker de otra organización) |
| 403 | error `not_a_worker` | Token válido, pero no es del worker del agente |
| 404 | error `ceremony_not_found` | La ceremonia no existe, su sprint ya no es el activo del equipo o está agendada antes de que empiece |
| 409 | error `result_already_received` | La ceremonia ya tiene otro resultado; nada cambia |
| 422 | error `validation_error` | `ceremony_id` no es un UUID, el cuerpo no cumple el contrato, su `ceremony_id` no es el del camino (`reason`: `does_not_match_path`) o un segmento o un evento es de alguien que no es participante del sprint (`reason`: `not_a_participant`, sin el valor); nada cambia |
| 500 | error `internal_error` | Fallo inesperado |
