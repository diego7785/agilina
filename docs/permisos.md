# Matriz de permisos

Qué puede hacer cada rol en cada acción de la API. Es la referencia de quien revisa un cambio de
autorización; la prueba `tests/api/unit/bootstrap/test_permissions.py` falla si esta tabla y el
código dejan de coincidir.

## El modelo (HU-04)

- Hay **exactamente dos roles por equipo**, guardados en `team_member.role`: `admin` y `member`. Una
  persona puede tener roles distintos en equipos distintos.
- La interfaz muestra **tres etiquetas**, que se derivan del rol y del modo del equipo y **no se
  guardan** (`agilina_shared.role_label`):

  | Rol | Modo soporte (`support`) | Modo autónomo (`autonomous`) |
  | --- | --- | --- |
  | `admin` | Scrum Master (`scrum_master`) | Administrador (`admin`) |
  | `member` | Miembro (`member`) | Miembro (`member`) |

- **La etiqueta no cambia permisos.** Lo único que varía entre los modos es si Agilina pide
  aprobaciones antes de actuar. Toda regla de autorización se evalúa contra el **rol interno**
  (`current_team_member`, `current_team_admin`), nunca contra la etiqueta: una prueba verifica que
  solo la lectura (presentación y consultas) importa la etiqueta.
- Cambiar el modo del equipo no modifica ningún registro de rol.
- Un rol que llega en una petición (`PATCH /v1/users/{user_id}`, `POST /v1/users/invitations`) es el rol
  interno (`admin` o `member`); una etiqueta como `scrum_master` es un `422 validation_error`.

## La matriz

Todas las rutas exigen tenant y sesión (AD-29, AD-28). «Mínimo» es el rol que la ruta exige. Una
sesión válida de alguien que no es usuario activo de la organización (sin `app_user`, o
desactivado) recibe `403 account_not_active` en toda ruta con sesión, antes de mirar rol alguno; un
token que falta o no vale recibe `401 not_authenticated`.

| Acción | Endpoint | Mínimo | Miembro | Administrador / Scrum Master |
| --- | --- | --- | :-: | :-: |
| Crear un equipo (y quedar como su admin) | `POST /v1/teams` | usuario | ✅ | ✅ |
| Ver mis equipos | `GET /v1/teams` | usuario | ✅ | ✅ |
| Ver un equipo | `GET /v1/teams/{team_id}` | miembro | ✅ | ✅ |
| Ver el dashboard del equipo | `GET /v1/teams/{team_id}/dashboard` | miembro | ✅ | ✅ |
| Verme en un equipo (encabezado) | `GET /v1/users/me` | miembro | ✅ | ✅ |
| Ver los usuarios de un equipo y sus roles | `GET /v1/users` | admin | ❌ | ✅ |
| Ver a un usuario de un equipo | `GET /v1/users/{user_id}` | admin | ❌ | ✅ |
| Cambiar el rol de un usuario | `PATCH /v1/users/{user_id}` | admin | ❌ | ✅ |
| Quitar a un usuario del equipo | `DELETE /v1/users/{user_id}` | admin | ❌ | ✅ |
| Invitar a alguien al equipo | `POST /v1/users/invitations` | admin | ❌ | ✅ |
| Configurar el sprint del equipo | `POST /v1/teams/{team_id}/sprints` | admin | ❌ | ✅ |
| Ver el sprint activo | `GET /v1/teams/{team_id}/sprints/active` | miembro | ✅ | ✅ |
| Editar el sprint activo | `PUT /v1/teams/{team_id}/sprints/active` | admin | ❌ | ✅ |

Las rutas de `/v1/users` nombran el equipo en la query (`?team_id=`): un usuario tiene un rol distinto
en cada equipo. `GET /v1/users/me` solo devuelve a quien llama; las demás rutas de usuarios son del
admin del equipo.

La columna del administrador es la misma en los dos modos. Un miembro que pide una ruta de admin
recibe `403 not_a_team_admin`; quien no es miembro activo recibe `403 not_a_team_member` (la misma
respuesta si el equipo es ajeno, lo retiraron o no existe).

Las rutas públicas (`/health*`, `GET /v1/tenant`, `/v1/invitations/*`) y las de ceremonias están
fuera de esta matriz: no dependen de un rol (ver `test_authentication.py`).

## Acciones planeadas

Cuando existan, se agregan aquí y al inventario de la prueba. Hoy se prevé que sean del administrador:
cerrar el sprint (HU-10), cambiar el modo (HU-11) y aprobar las acciones de
Agilina en modo soporte.
