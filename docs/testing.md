# Cómo se prueba

Guía práctica de las pruebas de Python. La decisión y sus motivos están en
[AD-25](adr/0025-organizar-las-pruebas-con-arbol-espejo-builders-y-cobertura-total.md); las
reglas generales de código, en [code-conventions.md](code-conventions.md).

## Dónde van

```
tests/
├── api/
│   ├── builders/       Data Builders: cómo se arman los datos
│   ├── doubles/        Dobles en memoria de los puertos
│   ├── conftest.py     Reloj de identificadores, entorno y cliente HTTP
│   ├── unit/           Sin servidores: corre en segundos
│   │   ├── shared_kernel/  shared/{application,infrastructure,presentation}/
│   │   ├── identity/{domain,application,presentation,infrastructure}/
│   │   ├── teams/{domain,application}/   ceremonies/presentation/   bootstrap/
│   └── integration/    PostgreSQL y Keycloak reales, misma estructura que unit/
├── agent/unit/   stt/unit/   shared/unit/
```

**La ruta de una prueba es la de su módulo en `src/`.** Para saber dónde probar
`identity/application/commands/activate_account.py`, busca
`tests/api/unit/identity/application/commands/test_activate_account.py`. Los nombres de
archivo se repiten entre `unit/` e `integration/`; por eso pytest usa
`--import-mode=importlib`.

`tests/shared/unit/` sigue el mismo espejo, un subpaquete de `agilina_shared` por carpeta:
`agilina_shared/sprint_calendar/sprint_day_at.py` se prueba en
`tests/shared/unit/sprint_calendar/test_sprint_day_at.py`. Las pruebas que ya estaban en la
raíz (`test_contract.py`, `test_i18n.py`) cubren módulos de la raíz del paquete o varios
subpaquetes a la vez.

## Qué se prueba en cada capa

| Capa | Cómo | Árbol |
| --- | --- | --- |
| `domain` | Unitarias puras, con builders, sin dobles | `unit/` |
| `application` | Casos de uso con los dobles en memoria de `doubles/` | `unit/` |
| `presentation` | La aplicación real con un cliente HTTP y los casos de uso doblados | `unit/` |
| `infrastructure` | Repositorios y consultas contra PostgreSQL real; Keycloak con `httpx.MockTransport` y, además, contra el real; SMTP con un `smtplib` falso. Los errores que un servidor real casi no produce (una restricción desconocida, un fallo de red) se simulan con `doubles/database.py` | `integration/` y `unit/` |
| `bootstrap` | El grafo se construye sin conectarse, la aplicación registra sus rutas, el ciclo de vida arranca y para el planificador, y los comandos del operador (`make invite`, `make mail-test`) leen sus argumentos | `unit/`; los flujos con base de datos, en `integration/` |

## Los *Data Builders*

```python
from tests.api.builders import InvitationBuilder, TeamBuilder, next_id

invitation = InvitationBuilder().for_team(team_id).as_admin().build()
used       = InvitationBuilder().accepted_by(next_id()).build()
overdue    = InvitationBuilder().past_its_deadline().build()
replaced   = InvitationBuilder().revoked().build()
left       = TeamBuilder().with_admin(ana).with_removed_member(bruno).build()
await InvitationBuilder().for_team(team.id).saved_in(uow.invitations)
```

| Builder | Qué arma |
| --- | --- |
| `TeamBuilder` | Un equipo; `with_member`, `with_admin` y `with_removed_member` (entra y luego sale por `Team.remove_member`, así que el único admin no se puede remover tampoco aquí) |
| `InvitationBuilder` | Una invitación pendiente; `accepted_by`, `past_its_deadline`, `expired` y `revoked` (reemplazada por otra, con `Invitation.revoke`) |
| `AppUserBuilder` | Una cuenta de Agilina; `disabled` (una cuenta desactivada: ningún comportamiento la desactiva todavía, así que se restaura tal como se guarda) |
| `IssueInvitationBuilder`, `ActivateAccountBuilder`, `RequestNewInvitationBuilder` | Los comandos de invitación y activación (HU-02) |
| `InviteToTeamBuilder` | Un admin invita a alguien a su equipo (HU-06); `by_admin(user_id, membership_id)` fija quién invita y la membresía que queda como autora |
| `ChangeMemberRoleBuilder`, `RemoveMemberBuilder` | Un admin cambia el rol de un integrante o lo saca del equipo (HU-06) |
| `SprintBuilder` | Un sprint activo del 2026-10-05 al 2026-10-16 con la daily a las 09:00 de America/Bogota (HU-07); `for_team(equipo)` llama a la daily a sus integrantes activos, `with_period`, `with_daily_time`, `with_participants` (en orden de turno) y `closed()` / `planned()` (se restauran tal como se guardan: cerrar un sprint llega con HU-10) |
| `StartSprintBuilder`, `ReconfigureSprintBuilder` | Un admin configura el sprint o edita el activo (HU-07), con los mismos valores por defecto que `SprintBuilder` |
| `ContactBuilder`, `TeamContactsBuilder`, `EmailMessageBuilder` | Datos de lectura y mensajes de correo |
| `CeremonyBuilder`, `RosterBuilder` | Una ceremonia guardada, programada en la daily por defecto (AGI-64); `for_sprint(sprint)` la pone en ese sprint de su equipo y `scheduled_at_instant` cambia el instante. El *roster* es lo que ceremonies lee de teams: idioma, modo, calendario del sprint y `with_participant` en el siguiente turno. En integración, `stored_ceremony(session_factory, CeremonyBuilder().for_sprint(sprint))` escribe la fila, porque nada crea ceremonias todavía |

Reglas:

- Los valores por defecto son **válidos y fijos**; un fallo se reproduce igual cada vez.
- Cada `with_…`/`as_…` devuelve **un builder nuevo**: un builder compartido como punto de
  partida no se altera.
- `build()` usa las **reglas del dominio** (`Invitation.issue`, `Team.create`): si el
  dato es inválido, falla igual que en producción.
- Un estado se alcanza **por comportamiento** (`accepted_by` llama a `accept`, `revoked` a
  `revoke`, `with_removed_member` a `Team.remove_member`), nunca escribiendo atributos
  privados. Un estado guardado al que ningún comportamiento llega se restaura con
  `restored_as(...)`.
- `saved_in(repositorio)` sirve para el doble en memoria y para el repositorio SQL.
- **Multitenencia ([AD-29](adr/0029-un-tenant-es-una-organizacion-con-su-base-y-su-realm.md)):** en
  integración, el *fixture* `platform_databases` crea, con un prefijo aleatorio, el catálogo y las
  bases de `acme` y `ecomoda`, todas migradas. `session_factory` y `engine` son las de `acme`;
  `ecomoda_session_factory` y `ecomoda_engine`, las del otro. Una prueba de aislamiento usa las dos
  y comprueba que nada se mezcla (`integration/shared/presentation/http/test_multitenancy_flow.py`).
  En las unitarias, `TenantBuilder` y `FakeTenantDirectory` dan el catálogo, y el cliente HTTP
  (`client`) va sin encabezado de tenant: cada prueba nombra el suyo.
- En integración, `tests/api/integration/support.py` guarda con *commit* un equipo, un
  usuario o una invitación como datos de partida. La base impide dos invitaciones con el
  mismo token o dos usuarios con el mismo correo: `with_unique_token()` y
  `with_unique_email()` evitan el choque. Un integrante removido se guarda con
  `stored_team(session_factory, TeamBuilder()….with_removed_member(user_id))`, no con un
  `UPDATE` directo. Un sprint se guarda igual, por su repositorio:
  `stored_sprint(session_factory, SprintBuilder().for_team(equipo).closed())`; sus
  participantes deben ser integrantes del equipo, porque la base lo exige.
- Si te falta un builder, **agrégalo en `builders/`**, no en el archivo de la prueba.

## Los dobles

En `tests/api/doubles/`, uno por puerto, en memoria. Los que más se usan:

| Doble | Puerto | Qué permite |
| --- | --- | --- |
| `FakeClock` | `Clock` | Fija la hora y la avanza |
| `FakeMailer`, `FakeRenderer` | `Mailer`, `EmailRenderer` | Ver lo enviado (`sent`), hacer fallar el envío (`fail = True`) y leer la plantilla y sus parámetros en el cuerpo |
| `FakeTokenGenerator` | `ActivationTokenGenerator` | Entrega los tokens que le das, en orden |
| `FakeIdentityProvider` | `IdentityProvider` (Keycloak) | Crea o borra cuentas, rechaza una contraseña o se cae |
| `FakeAuthenticatedUsers` | `AuthenticatedUsers` | Reemplaza la validación del token de Keycloak (HU-03): cada token es un usuario |
| `FakeTeamAccess`, `FakeTeamQueries` | `TeamAccess`, `TeamQueries` | La membresía y el rol de cada usuario, y lo que leen las consultas |
| `FakeActiveSprints` | `ActiveSprints` | Los equipos que tienen un sprint en curso |
| `InMemorySprintRepository`, `FakeSprintQueries` | `SprintRepository`, `SprintQueries` | Los sprints guardados (copias, como la base) y su lectura: `FakeSprintQueries(repositorio)` lee lo que el repositorio guardó, así que una ruta que guarda y luego lee ve lo guardado |
| `FakeMemberContacts` | `MemberContactsDirectory` | El nombre y el correo de cada integrante; los demás no tienen cuenta |
| `FakeAuthenticatedWorkers` | `AuthenticatedWorkers` | El token del worker y el de una persona; cualquier otro no es válido (AGI-64) |
| `FakeCeremonyQueries`, `FakeCeremonyRoster`, `FakeParticipantNames` | `CeremonyQueries`, `CeremonyRoster`, `ParticipantNames` | Las ceremonias, el *roster* del sprint activo de cada equipo y los nombres de los participantes (AGI-64) |

### Flujos de punta a punta

Una historia se prueba completa por HTTP contra PostgreSQL real, sin Keycloak, con
el patrón de `tests/api/integration/teams/presentation/http/test_teams_flow.py`:
`create_app()` con `dependency_overrides` hacia los *handlers* reales, `FakeAuthenticatedUsers`
en lugar de la validación del token, `SqlTeamQueries` como `TeamAccess` (la membresía se comprueba contra la
tabla) y solo el correo, los tokens y el reloj doblados.

Para los casos de uso que cruzan identity y teams sin pasar por HTTP,
`tests/api/integration/world.py` arma `World`: base real, repositorios reales y los mismos
dobles. Tiene la invitación y la activación de HU-02 y, de HU-06, `invite_to_team`,
`list_members`, `change_role` y `remove`; `admin_invites(team_id, admin_id, …)` invita
como lo hace la ruta, con la membresía del admin como autora. De HU-07 tiene
`start_sprint`, `reconfigure_sprint` y `active_sprint` (la lectura, con el reloj de `World`). Escribe los correos con
`FakeRenderer` (plantilla y parámetros); `World(session_factory, JinjaEmailRenderer())` usa
las plantillas reales cuando la prueba necesita leer lo que recibe la persona.

## Reglas de cada prueba

- Describe un comportamiento, no un método: `test_an_expired_link_cannot_be_used`.
- No depende de otra ni del orden; el reloj es `FakeClock` y los identificadores salen de
  `next_id()` (un contador que se reinicia en cada prueba).
- Una prueba no tiene condicionales sobre el entorno (`if status == 503`): si depende de
  un servidor, se simula o va a `integration/`.
- Todo error corregido deja una prueba que lo habría detectado.

## De punta a punta

`tests/e2e/` (Playwright, Chromium) recorre en un navegador real lo que ninguna otra prueba junta:
invitar → activar → iniciar sesión → entrar al equipo → volver a la página pedida. Lo hacen en los
dos tenants de desarrollo con **la misma persona** (el mismo correo, dos cuentas separadas), y
comprueban que los tenants no se mezclan y que una dirección sin organización no se encuentra. Corren
contra el entorno levantado, en un contenedor sobre la red del anfitrión (`make test-e2e`, que invita
a una persona nueva a un equipo nuevo de cada tenant en cada ejecución). Son pocas a propósito: cubren los recorridos, no las reglas, que
siguen en las pruebas de cada capa. Aún no corren en la CI.

Una prueba de punta a punta encuentra los elementos por su `data-testid` (`page.getByTestId(…)`),
nunca por su texto, su etiqueta, su rol o su clase: un texto o una etiqueta que cambian no la rompen.
Lo que la persona lee se sigue comprobando, sobre el elemento encontrado así
(`expect(page.getByTestId('login-error')).toHaveText(…)`). Los nombres van en kebab-case, con el
prefijo de la pantalla: `activate-password`, `login-submit`, `team-name`. Un elemento que una prueba
necesita y no tiene `data-testid` se le agrega en la plantilla (también en las del tema de
Keycloak); las piezas de `shared/ui` lo reciben por una entrada (`toggleTestId` de
`agl-password-field`).

## Comandos

| Quiero… | Comando |
| --- | --- |
| Las pruebas unitarias | `make test-python` |
| Las de integración (levanta PostgreSQL) | `make test-integration` |
| Las del adaptador de Keycloak real | `make test-keycloak` |
| Un recorrido completo en un navegador real, en los dos tenants | `make test-e2e` (con `make up`) |
| La cobertura, con el umbral del 100 % | `make coverage` |
| Todo lo que corre la CI | `make verify` |

## Cobertura

La API (`api/src`) y el contrato (`shared/src`) están en **100 % de líneas y ramas**,
sumando unitarias e integración, y la CI falla por debajo. Las pruebas de Keycloak real
(`make test-keycloak`) no cuentan para el umbral: el adaptador ya se cubre con el servidor
simulado, y la CI no levanta Keycloak. `agent/` y `stt/` no están en el umbral todavía.

Una línea que no se pueda probar se excluye con `# pragma: no cover` y una razón al lado,
o por las reglas de `pyproject.toml` (cuerpos de un `Protocol`, `if __name__ == "__main__"`).
Agregar una exclusión es una decisión que se revisa en el pull request.
