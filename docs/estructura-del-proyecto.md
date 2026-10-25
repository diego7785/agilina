# Estructura del proyecto

Qué hay en cada carpeta, cómo se organiza el código por dentro y qué reglas de
arquitectura se verifican automáticamente. Para levantar el entorno, ver
[entorno-local.md](entorno-local.md); para el flujo de trabajo con git,
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Vista general

Un solo repositorio con **tres desplegables** (API, worker del agente y
servicio de transcripción), la **aplicación web** y un **paquete común** con el
contrato entre ellos.

```
agilina/
├── shared/    Contrato worker ↔ API, enums, reglas puras compartidas y textos i18n (Python)
├── api/       API en FastAPI: un paquete por contexto, cada uno en cuatro capas
├── agent/     Worker de LiveKit Agents: todo lo que ocurre durante la ceremonia
├── stt/       Servicio de transcripción con faster-whisper (GPU)
├── web/       Aplicación web en Angular
├── tests/     Pruebas de Python: un árbol por pieza, con unit/ e integration/ (ver testing.md)
├── infra/     Compose del entorno, Dockerfile de Python, realm versionado, scripts
├── docs/      Documentación técnica y decisiones arquitectónicas (ADR)
├── .github/   Pipeline de verificación, plantillas y validación de commits
├── Makefile   Punto de entrada: levantar, probar, verificar y actualizar los locks
└── pyproject.toml   Workspace de uv y configuración de ruff, mypy, pytest e import-linter
```

Los tres desplegables son procesos distintos porque tienen vidas distintas: el
worker vive lo que dura la ceremonia, la API es de larga vida y la
transcripción necesita GPU. Comparten repositorio para que el contrato entre
ellos sea código compartido y no documentación que se desactualiza.

## Arquitectura: limpia, hexagonal y por contextos

Cada pieza sigue **Clean Architecture** con puertos y adaptadores (hexagonal) y
se organiza por **contexto delimitado** (DDD) antes que por capa técnica.

### Las cuatro capas

| Capa | Qué contiene | Puede importar |
| --- | --- | --- |
| `domain` | Entidades, agregados, objetos de valor, eventos y reglas de negocio. Código puro: sin frameworks | Solo `domain` |
| `application` | Casos de uso (comandos y consultas), puertos de entrada y de salida, DTO | `domain` |
| `presentation` | Adaptadores de entrada: routers HTTP, esquemas de petición y respuesta, CLI, trabajos de la sala | `application` (y `domain` por sus tipos) |
| `infrastructure` | Adaptadores de salida: base de datos, Keycloak, correo, SDK de terceros, configuración | `application` y `domain` |

```mermaid
flowchart LR
  P[presentation] --> A[application]
  I[infrastructure] --> A
  A --> D[domain]
  B["bootstrap / main<br/>(raíz de composición)"] --> P
  B --> I
```

**La regla de dependencia:** las flechas solo apuntan hacia adentro.
`presentation` e `infrastructure` no se conocen entre sí: se encuentran
únicamente en la **raíz de composición** (`bootstrap/` en la API, `main.py` en
el worker y en la transcripción, `app.config.ts` en la web), que es el único
lugar donde se elige qué adaptador concreto atiende cada puerto.

Dos consecuencias prácticas:

- Cambiar de proveedor (Whisper por otro STT, SMTP por SES) es escribir un
  adaptador nuevo y cambiar una línea en la raíz de composición.
- La capa `presentation` declara lo que necesita (por ejemplo,
  `get_readiness_query`) y la raíz de composición se lo entrega con
  `dependency_overrides` de FastAPI. Así nunca importa infraestructura.

### Comandos y consultas (CQRS pragmático)

- **Comando:** cambia el estado. Carga el agregado por su repositorio, ejecuta
  el comportamiento, persiste con una unidad de trabajo y publica eventos.
- **Consulta:** solo lee. Va directo a SQL y devuelve DTO, sin pasar por los
  agregados.
- Una sola base de datos, sin *event sourcing* y sin bus genérico: cada
  endpoint recibe su manejador por inyección de dependencias.

Ya existen las dos clases. En `identity` están los comandos de las
invitaciones (`IssueInvitation`, `ActivateAccount`, `RequestNewInvitation`, de HU-02, e
`InviteToTeam`, de HU-06) y la consulta `GetInvitationStatus`. En `teams` están los
comandos `CreateTeam` y `AddTeamMember` (HU-02), `CreateTeamAsAdmin` (HU-05),
`ChangeMemberRole` y `RemoveMember` (HU-06) y `StartSprint` y `ReconfigureSprint` (HU-07), y
las consultas `ListMyTeams` y `GetTeam` (HU-05), `ListTeamMembers` (HU-06) y
`GetActiveSprint` (HU-07). En `shared` están las consultas de salud
(`GetLiveness` y `GetReadiness`).

### Contextos delimitados

Salen de los componentes de la API del documento de arquitectura. Cada uno es un
paquete directo bajo `agilina_api/`, con las capas que necesite, y **no importa
a otro contexto**: se hablan por los casos de uso o los eventos del otro.

| Contexto | Responsabilidad | Estado |
| --- | --- | --- |
| `ceremonies` | Contrato con el worker del agente | La tabla mínima `ceremony` y la consulta `GetCeremonyContext` (AGI-64), que arma el `CeremonyContext` compartido con el equipo y el sprint activo de `teams` (puerto `CeremonyRoster`) y los nombres de `identity` (puerto `ParticipantNames`); el agregado `Ceremony`, que recibe un único resultado y solo de participantes, y el comando `DeliverCeremonyResult` (AGI-126), que lo guarda con su transcripción y sus eventos bajo el bloqueo de la ceremonia (`SELECT … FOR UPDATE`); API HTTP en `GET /v1/ceremonies/{ceremony_id}/context` y `POST /v1/ceremonies/{ceremony_id}/result`, solo para el worker (`current_worker`). Para las personas, el comando `JoinCurrentDaily` (AGI-59), que a un participante de la daily abierta le guarda la ceremonia de esa daily, le abre la sala en LiveKit (puerto `Rooms`, adaptador `infrastructure/livekit/`) y le firma el token, en `POST /v1/teams/{team_id}/dailies/current/token` (`dailies_router`, `current_team_member`); y la consulta `GetCurrentDailyParticipants` (AGI-61), que a un participante de la daily del sprint activo le da los convocados en orden de turno con su identidad en la sala, su nombre y su correo de `identity` (puerto `ParticipantContacts`), en `GET /v1/teams/{team_id}/dailies/current/participants` |
| `identity` | Invitaciones, activación de cuenta, vínculo con Keycloak, etiqueta del rol | Invitaciones (HU-02) completas: en el servidor, dominio, casos de uso, persistencia, API HTTP, adaptador de Keycloak y `make invite`; en la web, la pantalla `/activate`; el inicio de sesión (HU-03: validación del token de Keycloak en la API, `core/auth` y la entrada en la web). HU-06 agrega la invitación de un Administrador a su equipo (`InviteToTeam`, `POST /v1/teams/{team_id}/invitations`): a un correo sin cuenta le llega el enlace de activación y una cuenta existente entra directo al equipo con un aviso; invitar de nuevo revoca la invitación pendiente (`Invitation.revoke`), también en `make invite`. HU-04 después |
| `teams` | Equipos, membresía, sprint, modo, idioma, preferencias | Equipo y membresías: dominio (con el nombre como objeto de valor `TeamName`; cambio de rol y remoción de un integrante, HU-06, con la regla del último Administrador en el agregado y en el paquete `member_rules/`, que también usa el listado), comandos (`CreateTeam` y `AddTeamMember` de HU-02, `CreateTeamAsAdmin` de HU-05, `ChangeMemberRole` y `RemoveMember` de HU-06), consultas (administradores, `ListMyTeams`, `GetTeam`, la membresía de un usuario y `ListTeamMembers`, que trae nombre y correo de `identity` por el puerto `MemberContactsDirectory`), persistencia (el repositorio bloquea la fila del equipo con `SELECT … FOR UPDATE` al cargarlo) y API HTTP (`/v1/teams`, HU-05; `/v1/teams/{team_id}/members`, HU-06). Sprint (HU-07, sobre la tabla mínima de HU-06): el agregado `Sprint` con sus objetos de valor `SprintPeriod` y `DailyTime` (instante UTC de anclaje más la zona de captura, AD-31) y los participantes de la daily en orden de turno (tabla `sprint_participant`), su repositorio (`get_active`), los comandos `StartSprint` y `ReconfigureSprint`, que cargan y bloquean primero el equipo, y la consulta `GetActiveSprint`, que calcula el día N de M y la próxima daily con `agilina_shared.sprint_calendar` y el `Clock`; API HTTP en `/v1/teams/{team_id}/sprints` y `/v1/teams/{team_id}/sprints/active`. «¿Hay sprint activo?» tiene un solo predicado (`is_active_sprint_of`), que usan `team_has_active_sprint` (detrás del puerto `ActiveSprints`, que bloquea el cambio de rol y que el listado expone como motivo), el repositorio y la lectura del sprint… |
| `postprocessing` | Resumen, action items, flujo de aprobación | Planeado (Release 2–3) |
| `integrations` | Credenciales por equipo y adaptadores de Slack, Jira y Graph | Planeado (Release 3) |

`shared/` no es un contexto: contiene lo transversal (configuración, base de
datos, planificador, sondas de salud, quién llama y a qué equipo pertenece, y el
formato de error común) con las mismas cuatro capas.

El **tenant es la organización** ([AD-29](adr/0029-un-tenant-es-una-organizacion-con-su-base-y-su-realm.md)):
cada una tiene su base de datos, su realm de Keycloak y su login, y contiene equipos. El tenant se
elige en el borde, una vez por petición (`X-Agilina-Tenant`, `shared/presentation/http/tenancy.py`),
y `bootstrap/tenants.py` da a cada tenant su propio grafo de objetos; lo que hay detrás no lo sabe.
Dentro de un tenant, el **equipo** sigue aislado por `team_id`: todo repositorio y toda consulta de un
contexto con datos de equipo deben exigir el `team_id` en su firma. La única consulta que filtra
por usuario en lugar de por equipo es la que lista los equipos de quien pregunta
(`ListMyTeams`).

Toda ruta HTTP sobre un equipo lleva `{team_id}` en el camino y declara
`Depends(current_team_member)` (en `shared/presentation/http/access.py`). Esa dependencia
resuelve a quien llama con `current_user_id` (`401 not_authenticated` si no hay un
usuario) y comprueba su membresía activa guardada en la base (`403 not_a_team_member` si no
la tiene). Una regla sobre el rol (solo un `admin` puede…) es otra dependencia encima de
esa: `Depends(current_team_admin)` (HU-06; `current_team_*_by_query` en las rutas de `/v1/users`, que nombran el equipo en `?team_id=`) responde `403 not_a_team_admin` a un integrante
que no es Administrador, con el rol guardado en la membresía. La autorización nunca vive en
la web.

## Cada pieza por dentro

### `api/`

```
api/
├── pyproject.toml
├── alembic.ini
├── migrations/                       Alembic, dos entornos (AD-29); la URL la da quien migra
│   ├── tenant/versions/              El esquema de la base de cada tenant
│   └── platform/versions/            El catálogo de tenants
├── src/agilina_api/
│   ├── bootstrap/                    Raíz de composición: app.py (fábrica, lifespan, cableado), container.py (todo cableado a sus adaptadores reales), context_adapters/ (lo que conecta identity con teams), tenants.py (un grafo por tenant), migrate.py y tenant_admin.py (`make migrate`, `make tenant-add`) e invite.py (`make invite`)
│   ├── shared_kernel/                Bloques base del dominio: Entity, AggregateRoot, DomainEvent, DomainError
│   ├── shared/
│   │   ├── application/              Consultas de salud, los puertos Clock, UnitOfWork, Mailer y EmailRenderer, y los de acceso (AuthenticatedUsers y TeamAccess)
│   │   ├── infrastructure/           settings, logging, base de datos, planificador, reloj, sonda SQL, correo SMTP y plantillas de correo (Jinja2)
│   │   └── presentation/http/        Router de salud, dependencias declaradas, acceso (current_user_id, current_team_member y current_team_admin) y el formato de error único (catálogo `ApiError`, manejadores, `request_id`; una tabla de errores por contexto)
│   ├── identity/                     Contexto (HU-02): dominio (Invitation, AppUser), puertos y DTO de lectura, persistencia
│   ├── teams/                        Contexto (HU-02 lo creó; HU-05 en adelante lo amplía): dominio (Team con sus membresías y TeamName), comandos, consultas, persistencia y API HTTP
│   └── ceremonies/                   Contexto (AGI-64): dominio (Ceremony), los comandos de la entrega del resultado y de la entrada a la daily, la consulta del contexto, sus puertos, persistencia, LiveKit, el router del contrato del agente y el de las personas (`dailies_router`)
```

Las pruebas de la API no están aquí sino en `tests/api/`, con la misma estructura
(ver [testing.md](testing.md)).

La forma que tendrá cada contexto con dominio (por ejemplo `identity`):

Una clase por archivo ([code-conventions.md](code-conventions.md)): donde esta guía nombra
`errors`, `dtos` o `schemas`, es un paquete con una clase por archivo.

```
identity/
├── domain/            model/ (agregados y objetos de valor), events.py, errors/, repositories/
├── application/       ports/ (inbound y outbound), commands/, queries/, dtos/, errors/
├── presentation/      http/ (router, schemas, presenters), cli/
└── infrastructure/    persistence/ (modelos ORM, mapeadores, repositorio, consultas), keycloak/, mail/
```

Dónde va cada puerto: las **interfaces de repositorio** hablan el lenguaje de
los agregados y van en `domain`; los demás puertos de salida (proveedor de
identidad, correo, reloj, consultas de lectura) responden a lo que necesita el
caso de uso y van en `application/ports/outbound`. Los modelos ORM **no** son
las entidades del dominio: viven en `infrastructure` y se convierten con
mapeadores.

La app arranca con `agilina_api.bootstrap.app:app` (`make api`).

### `agent/`

```
agent/src/agilina_agent/
├── main.py                       Raíz de composición y punto de entrada de LiveKit
├── domain/facilitation.py        Máquina de estados de la daily (sin LiveKit, audio ni red)
├── application/ports.py          Transcriber, SpeechSynthesizer, AgilinaApi
├── presentation/room_job.py      Lo que el worker hace una vez por ceremonia
└── infrastructure/               Adaptadores: cliente HTTP de la API, STT, TTS, ajustes, logs
```

El worker **no accede a la base de datos**: solo usa dos operaciones de la API
(obtener el contexto y entregar el resultado), con una cuenta de servicio. Ver
[contrato-worker-api.md](contrato-worker-api.md).

### `stt/`

```
stt/src/agilina_stt/
├── main.py                        Raíz de composición: app, transcriptor y ServiceInfo
├── domain/transcription.py        Resultado de transcribir un segmento
├── application/ports.py           Transcriber y ServiceInfo
├── presentation/http/             router, schemas y dependencias declaradas
└── infrastructure/                settings y transcriptores (simulado y faster-whisper)
```

En modo simulado (`AGILINA_STT_SIMULATED=true`) no carga el modelo, de modo que
corre en cualquier máquina y en el pipeline.

### `shared/`

```
shared/src/agilina_shared/
├── contract/      CeremonyContext, CeremonyResult, ParticipantContext, TranscriptSegment (un archivo por clase)
├── enums/            OperationMode, TeamRole, Language, CeremonyType, CeremonyStatus (un archivo por clase)
├── sprint_calendar/  daily_occurrences, sprint_day_at, SprintDay, SprintPhase (un archivo por clase o función)
└── i18n.py           Plantillas de lo que Agilina dice, en español e inglés
```

Es el *lenguaje publicado* entre desplegables, no un dominio. No puede importar
ninguno de los tres desplegables. Un cambio incompatible sube
`CONTRACT_VERSION` y se declara con `BREAKING CHANGE` en el pie del commit.

Aloja también las **reglas puras** que más de un desplegable debe calcular igual: hoy,
`sprint_calendar/` (las ocurrencias de la daily y el día N de M), que usan la API, el agente y
el planificador ([AD-31](adr/0031-guardar-la-hora-de-la-daily-en-utc-con-su-zona-de-captura.md)).
Una regla así usa solo la biblioteca estándar, no lee el reloj ni la base de datos y recibe el
instante como parámetro.

### `web/`

```
web/
├── public/i18n/                     Catálogos es.json / en.json (Transloco)
├── runtime-config.template.json     config.json a partir de variables de entorno
└── src/app/
    ├── app.config.ts                Raíz de composición: enlaza puertos con adaptadores
    ├── app.routes.ts                Mapa de pantallas, con carga diferida
    ├── core/                        auth, config, http, i18n, logging, tenant y time
    ├── layout/                      Cabecera y marco de la aplicación
    ├── shared/                      Componentes, pipes y utilidades sin estado
    └── features/<contexto>/
        ├── domain/                  Modelos puros (sin Angular ni rxjs)
        ├── application/             Puertos (clases abstractas) y facades con signals
        ├── infrastructure/          Adaptadores: HTTP, LiveKit, Keycloak
        └── presentation/            Páginas y componentes
```

Hoy existen `features/status` (la pantalla de estado del entorno) y
`features/identity` (la pantalla `/activate`, HU-02) y `features/teams` (HU-05: el selector
mínimo, el formulario para crear un equipo y el dashboard del equipo, que por ahora muestra su
nombre y, a un Administrador, el enlace a Configuración; HU-06: Configuración → Equipo en
`/teams/:teamId/settings`, con su puerto `UsersPort` y su adaptador `HttpUsersApi` (la API
`/v1/users`), un ojito por integrante que abre su detalle y el equipo, la etiqueta del rol y el
nombre de la persona en el encabezado, sin guard: si la API responde 403, la pantalla muestra «sin
acceso»; HU-07: Configuración → Sprint en `/teams/:teamId/settings/sprint`, pestaña hermana de
Equipo, con su puerto `SprintsPort` y su adaptador `HttpSprintsApi`, y la línea «Día N de M» del
dashboard). `core/time` tiene `BROWSER_TIME_ZONE` (la zona IANA del navegador) y `shared/utils`,
las funciones puras de fechas (`local-date-time.ts`). `shared/ui` tiene `aglButton`,
`aglIconButton` (botón solo de ícono), `aglTextField`, `aglSelect` y `agl-dialog` (sobre el
`<dialog>` nativo). Las demás (`ceremonies` y el resto de `identity`) llegan con sus historias. El
detalle,
las convenciones y el porqué están en [web/README.md](../web/README.md) y en
[AD-26](adr/0026-organizar-y-equipar-la-aplicacion-web.md).

### `infra/` y los contenedores

Todo corre en contenedores (solo hacen falta Docker y `make`):

| Archivo | Para qué |
| --- | --- |
| `docker-compose.yml` | El entorno: `postgres`, `pgadmin`, `keycloak`, `mailpit`, `api` y `web`; con el perfil `voice`, `stt` y `agent`; con el perfil `tools`, los contenedores de un solo uso de las pruebas y verificaciones |
| `docker/python.Dockerfile` | Imagen de Python con varios objetivos: `dev` (todas las dependencias y las herramientas; el código se monta en `/app`) y `api` (producción: solo sus dependencias, código instalado, sin uv y sin root) |
| `../web/Dockerfile` | Imagen de la web: `dev` (`ng serve`), `test` (con Chromium), `build` y `prod` (nginx sin privilegios) |
| `keycloak/realm-agilina.json` | Realm, clientes y roles versionados: no se configura a mano |
| `postgres/01-extensions.sql` | Extensiones y zona UTC, solo al crear el volumen |
| `wait-for-services.sh` | Espera a que Postgres y Keycloak respondan antes de migrar |

Los contenedores de desarrollo corren con tu usuario (`HOST_UID` y `HOST_GID`,
que exporta el `Makefile`), de modo que los archivos que crean son tuyos. Por eso
conviene ejecutar siempre con `make` y no con `docker compose` a mano. Las
imágenes de producción de `stt` y `agent` llegan con el despliegue (HU-38).

## Reglas que se verifican solas

Se ejecutan con `make verify`, en la CI y (mypy e import-linter) antes de cada
`push`.

| Herramienta | Qué hace cumplir |
| --- | --- |
| `import-linter` (`make arch`) | Capas de la API, del worker y de la transcripción; la raíz de composición va encima de todo; los contextos de la API no se importan entre sí y `shared` y `shared_kernel` quedan debajo; el dominio de la API (y `shared_kernel`) no conoce FastAPI, SQLAlchemy, Pydantic ni `httpx`; el dominio del worker no conoce LiveKit ni `httpx`; el contrato compartido no depende de ningún desplegable |
| ESLint (`make lint`) | En la web: capas hacia adentro, ninguna funcionalidad importa a otra, `core` y `shared` no conocen las funcionalidades, `domain` no conoce Angular ni rxjs, `HttpClient`/LiveKit/Keycloak solo en adaptadores y nada de `console.*` fuera del `Logger` |
| Prettier (`make format`) | Formato de la web; `make verify` y la CI lo comprueban |
| `mypy --strict` (`make typecheck`) | Tipado estricto en los cuatro paquetes de Python |
| `ruff` | Formato y reglas de estilo y seguridad |
| Pruebas | Prueba de que toda clave i18n existe en español e inglés |

Para romper una regla de capas hay que cambiar la configuración, y eso se ve
en el code review.

## Convenciones de nombres

- **Código en inglés:** identificadores, comentarios, archivos, rutas HTTP,
  campos JSON, variables de entorno y objetivos de `make`.
- **Español:** commits, pull requests y esta documentación. Los textos que ve
  el usuario van en español e inglés mediante i18n, nunca dentro del código.
- Los valores de los enums coinciden con los tipos de PostgreSQL
  (`support`, `autonomous`, `admin`, `member`…).
- Las claves i18n de la web se agrupan por funcionalidad (`status.title`).

## Cómo agregar algo nuevo

**Un caso de uso en un contexto existente**

1. Si hay una regla de negocio nueva, agrégala en `domain` y pruébala sin base de datos.
2. Escribe el comando o la consulta en `application` con sus puertos.
3. Implementa los puertos de salida en `infrastructure`.
4. Expón el caso de uso en `presentation` y cabléalo en la raíz de composición.
5. `make verify` en verde.

**Un contexto nuevo**

1. Crea el paquete bajo `agilina_api/` con solo las capas que necesite.
2. Agrégalo a los `containers` y a la lista de contextos hermanos (`a | b | c`) de
   los contratos de import-linter en el `pyproject.toml`, y su paquete `domain` al
   contrato de "el dominio no conoce frameworks".
3. Importa sus modelos ORM en `api/migrations/env.py` para que Alembic los vea.
4. Registra su router en `bootstrap/app.py`.

## Dónde está el porqué

- Cómo se da estilo a la web (Tailwind CSS con los tokens `--agl-*` como tema): [AD-27](adr/0027-dar-estilo-a-la-web-con-tailwind-css.md).
- Cómo responde la API a un fallo y dónde se listan sus endpoints: [AD-30](adr/0030-un-solo-formato-de-error-http-y-un-catalogo-de-la-api.md) y [api.md](api.md).
- Cómo se aíslan las organizaciones (una base, un realm y un login por tenant, y el tenant en cada petición): [AD-29](adr/0029-un-tenant-es-una-organizacion-con-su-base-y-su-realm.md).
- Cómo se inicia sesión (página de Keycloak con tema propio, `keycloak-js`, validación del token en la API): [AD-28](adr/0028-iniciar-sesion-con-keycloak.md).
- Cómo se organizan las pruebas (árbol espejo, *Data Builders*, cobertura del 100 %): [AD-25](adr/0025-organizar-las-pruebas-con-arbol-espejo-builders-y-cobertura-total.md).
- La decisión de organizar el código así: [AD-21](adr/0021-organizar-el-codigo-en-contextos-y-capas.md).
- Cómo se envía el correo (SMTP, Mailpit y el proveedor por configuración): [AD-23](adr/0023-enviar-correo-por-smtp-con-mailpit-y-proveedor-configurable.md).
- Las herramientas y la estructura de la web: [AD-26](adr/0026-organizar-y-equipar-la-aplicacion-web.md).
- Cómo nace el primer Administrador sin registro público: [AD-22](adr/0022-emitir-por-cli-la-invitacion-del-primer-administrador.md).
- Cómo se escribe el código dentro de esta estructura: [code-conventions.md](code-conventions.md).
- El vocabulario del dominio: [glossary.md](glossary.md).
