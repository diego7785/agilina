# Agilina · Frontend (Angular)

Cliente web de Agilina, un Scrum Master virtual que facilita la Daily por voz. Es
uno de los componentes del monorepo, junto con la API (FastAPI), el worker del
agente (LiveKit Agents) y el servicio de transcripción (faster-whisper).

Esta guía es la fuente de verdad de cómo se construye la web. Lo que es común a
todo el repositorio (git, Definition of Done, glosario) vive en
[CONTRIBUTING.md](../CONTRIBUTING.md), [docs/code-conventions.md](../docs/code-conventions.md)
y [docs/glossary.md](../docs/glossary.md). El porqué de las decisiones de esta
guía está en [AD-26](../docs/adr/0026-organizar-y-equipar-la-aplicacion-web.md).

## Stack

| Pieza | Elección |
| --- | --- |
| Framework | Angular 22, **zoneless** y con **`OnPush` por defecto**. El estado se maneja con signals |
| Lenguaje | TypeScript 6 en modo estricto, con `noUncheckedIndexedAccess` y `exactOptionalPropertyTypes` |
| Sala de audio | `livekit-client`. No se usan los componentes prearmados de LiveKit, que son solo para React |
| Identidad | Keycloak (OIDC) con `keycloak-js`. La API emite el token de LiveKit |
| Textos | [Transloco](https://jsverse.gitbook.io/transloco) (`@jsverse/transloco`), español e inglés |
| Formularios | `FormsModule` (`ngModel`) atado a signals; la validación es una regla pura de `domain` |
| Análisis estático | ESLint con `angular-eslint`, `typescript-eslint` (reglas *type-checked*) e `import-x` |
| Estilos | Tailwind CSS 4, con tokens `--agl-*` como tema ([AD-27](../docs/adr/0027-dar-estilo-a-la-web-con-tailwind-css.md)) |
| Formato | Prettier, con el ordenador de clases de Tailwind |
| Pruebas | Jasmine con Karma sobre Chromium sin interfaz; de punta a punta, Playwright en `tests/e2e` (`make test-e2e`) |
| Ejecución | Todo corre dockerizado: en desarrollo `ng serve`, en producción nginx sin privilegios |

## Cómo se corre

Solo hacen falta Docker y `make`, desde la raíz del repositorio:

```bash
make up          # levanta todo; la web queda en http://localhost:4200
make test-web    # pruebas de la web en Chromium sin interfaz
make lint        # ESLint (y ruff para Python)
make format      # Prettier sobre la web (y ruff format sobre Python)
make verify      # exactamente lo que corre la CI
make lock        # tras cambiar package.json: regenera package-lock.json
```

Dentro de `web/`, los scripts de `package.json` son los mismos que usa la CI:
`lint`, `format`, `format:check`, `build`, `test:ci`.

## Reglas de arquitectura

- **El cliente no contiene reglas de autorización.** Solo oculta lo que la API
  ya protege: ocultar un elemento de la interfaz no cuenta como control de acceso.
- **Los controles de la ceremonia** (iniciar daily, terminar turno, cerrar ronda)
  se publican por el canal de datos de la sala de LiveKit, dirigidos al agente.
  No pasan por la API.
- **El cierre del turno es manual:** el participante pulsa «terminar turno». No
  se detecta por pausas.
- **La sala no muestra la transcripción en vivo.** Muestra los participantes
  conectados, quién está hablando, el turno en curso y el estado de Agilina.
- **Fechas en UTC.** Llegan y se envían en UTC y se muestran en la zona horaria
  del navegador. No existe zona horaria por equipo; la única zona que se envía a la API es la
  de captura de la hora de la daily (ver [Fechas y zonas horarias](#fechas-y-zonas-horarias)).
- **Configuración por variables de entorno.** Nunca se escriben credenciales,
  llaves ni URLs en el código (ver [Configuración](#configuración)).
- **La pestaña de configuración** solo se muestra a los roles Admin y SM. En el
  código ambos son el mismo rol interno `admin` (SM es su etiqueta visible en
  modo soporte, ver el [glosario](../docs/glossary.md)): la interfaz decide con
  el rol interno, nunca con la etiqueta.
  Configuración es una entrada del encabezado, junto a Dashboard, en todas las pantallas
  del equipo: no existe en el árbol de navegación del Miembro (`@if`, no se oculta con
  estilos). El encabezado la dibuja según `ShellTeam.canConfigure`, que
  `TeamShellFacade` saca de `GET /v1/teams/{id}` (`role === 'admin'`) y el dashboard de su
  propio `can_configure`. Configuración tiene dos pestañas, cada una con su ruta:
  Equipo (`/:tenant/teams/:teamId/settings`) y Sprint (`/:tenant/teams/:teamId/settings/sprint`).
  Ninguna lleva guard de rol: la pantalla pide los integrantes a la API y, si responde 403,
  muestra «sin acceso» (`settings-no-access`; un guard escondería esa respuesta). Las
  etiquetas de rol y los motivos por los que un control queda deshabilitado (`last_admin`,
  `sprint_in_progress`) también los manda la API; la pantalla solo los traduce.

## Estructura de carpetas

Primero por funcionalidad y después por capa, igual que la API
([AD-21](../docs/adr/0021-organizar-el-codigo-en-contextos-y-capas.md)):

```
web/
├── public/
│   └── i18n/{es,en}.json        Catálogos de textos
├── runtime-config.template.json  Plantilla de config.json (variables de entorno)
├── scripts/                      render-runtime-config.mjs (config.json en desarrollo)
└── src/
    ├── main.ts                   Carga config.json y arranca la aplicación
    ├── styles.css                Tailwind, tokens de diseño (--agl-*) y estilos globales
    ├── testing/                  Utilidades de prueba compartidas (@testing/*)
    └── app/
        ├── app.config.ts         Raíz de composición: enlaza puertos con adaptadores
        ├── app.routes.ts         Mapa de pantallas, todas con carga diferida
        ├── app.ts                Componente raíz: layout + router-outlet
        ├── core/                 Singletons de toda la aplicación (@core/*)
        │   ├── config/           RuntimeConfig, su validación y su carga
        │   ├── http/             Interceptores
        │   ├── i18n/             Transloco, idiomas y manejo de claves faltantes
        │   ├── logging/          Puerto Logger, adaptador de consola, ErrorHandler
        │   ├── tenant/           El tenant de la dirección: contexto, guards y puerto del catálogo (AD-29)
        │   ├── notifications/    Notifier: los toasts de la aplicación (ver «Notificaciones»)
        │   ├── time/             La zona horaria del navegador (BROWSER_TIME_ZONE) y el reloj (NOW)
        │   └── auth/             Sesión: puerto AuthSession, adaptador de keycloak-js, guards e interceptor
        ├── layout/               Marcos de pantalla (@layout/*): app-shell (con la cabecera) y
        │                         centered-layout (las pantallas antes de entrar a un equipo)
        ├── shared/               Reutilizable y sin estado (@shared/*)
        │   ├── ui/               Componentes de presentación genéricos
        │   ├── pipes/
        │   └── utils/            Funciones puras
        └── features/             Una carpeta por contexto (@features/*)
            └── <contexto>/
                ├── domain/
                ├── application/
                ├── infrastructure/
                └── presentation/
```

Una carpeta se crea cuando llega su primer archivo: no se dejan carpetas vacías
ni código a la espera de usarse.

### Funcionalidades

Los nombres salen de los contextos de la API y del glosario, para que un
concepto se llame igual en todo el sistema:

| Funcionalidad | Qué contiene | Estado |
| --- | --- | --- |
| `status` | Estado del entorno: prueba que la web habla con la API | Existe |
| `tenancy` | La página «no encontrada» de una dirección sin organización | Existe |
| `identity` | Activación de la cuenta desde la invitación (`/activate`); inicio y cierre de sesión; la página de cuenta no activa (`/account-not-active`) | Activación existe (HU-02); la página de cuenta no activa con su botón de cerrar sesión, también (AGI-123); el resto llega con HU-03/04 |
| `teams` | Equipo, integrantes, sprint, dashboard y pestaña de configuración (solo `admin`) | Existe: dashboard en `/:tenant/teams/:teamId` (HU-12), que lee `GET /v1/teams/{id}/dashboard` en una sola llamada y muestra el día N de M con su barra y el número del sprint («Sprint 12», que asigna la API), la próxima daily en la hora del navegador, el modo como etiqueta de solo lectura y la sala; «Unirse a la sala» es un enlace a la sala desde diez minutos antes de la daily hasta quince minutos después (`join-window.ts`, con un temporizador, sin recargar; en ese último tramo dice que la reunión diaria ya empezó) y fuera de la ventana un botón deshabilitado (AGI-60); Configuración → Sprint tiene el botón «Cerrar sprint activo» del mockup, sin función todavía (llega con AGI-81); el encabezado tiene las entradas Dashboard y Configuración y **Cambiar de equipo**, que lleva al selector aunque haya un solo equipo (`{ choose: true }`);  selector mínimo, creación y dashboard placeholder (HU-05); Configuración → Equipo en `/:tenant/teams/:teamId/settings` (HU-06): integrantes con su etiqueta de rol, invitar, cambiar el rol y eliminar; Configuración → Sprint en `/:tenant/teams/:teamId/settings/sprint` (HU-07): fechas, hora de la daily en la zona del navegador y participantes ordenados con subir y bajar, y la línea «Día N de M» del dashboard. El resto llega con sus historias |
| `ceremonies` | La sala de la Daily: LiveKit, turnos y controles hacia el agente | Existe la sala en `/:tenant/teams/:teamId/room` (AGI-60): pide el token a la API, entra con `livekit-client`, activa el micrófono, escucha a todos y muestra el estado de la conexión y del micrófono (ver «Sala de LiveKit»). Los participantes, quién habla y los controles llegan con AGI-61 y las historias de la ceremonia |

### Capas dentro de una funcionalidad

| Capa | Qué contiene | Puede importar |
| --- | --- | --- |
| `domain` | Modelos, objetos de valor y reglas puras (por ejemplo, de quién es el turno) | Solo su propio `domain`. Sin Angular, rxjs ni librerías |
| `application` | Puertos (clases abstractas) y *facades* con signals: el estado de la pantalla | `domain`, `@core/*`, `@shared/*` |
| `infrastructure` | Adaptadores: HTTP hacia la API, LiveKit, Keycloak. Mapean DTO ↔ dominio | `application`, `domain`, `@core/*` |
| `presentation` | Páginas y componentes | `application`, `domain`, `@core/*`, `@shared/*` |

`presentation` e `infrastructure` no se conocen: se encuentran solo en
`app.config.ts`, que decide qué adaptador atiende cada puerto. Cambiar de
proveedor es escribir un adaptador y cambiar una línea ahí.

### Fronteras que verifica ESLint

Romper una de estas reglas hace fallar `make lint`; cambiarla exige tocar
`eslint.config.js`, y eso se ve en el code review.

| Regla | Herramienta |
| --- | --- |
| Las capas apuntan hacia adentro; `presentation` no importa `infrastructure` | `import-x/no-restricted-paths` |
| Una funcionalidad no importa a otra (se hablan por la API o por el router) | `import-x/no-restricted-paths` |
| `core` no conoce `features` ni `layout`; `shared` no conoce `core`, `layout` ni `features`; `layout` no conoce `features` | `import-x/no-restricted-paths` |
| El dominio no importa Angular, rxjs ni ninguna librería | `no-restricted-imports` |
| `HttpClient`, `livekit-client` y `keycloak-js` solo en adaptadores (`infrastructure`, `core`) | `no-restricted-imports` |
| Nada escribe en la consola salvo el adaptador del `Logger` y `main.ts` | `no-console` |
| Sin ciclos de importación ni exportaciones por defecto | `import-x/no-cycle`, `import-x/no-default-export` |
| Ningún componente vuelve a `ChangeDetectionStrategy.Eager` | `no-restricted-syntax` |

## Convenciones de nombres

Todo el código va en inglés: identificadores, comentarios, nombres de archivo y
claves de i18n. Los textos que ve el usuario van en los catálogos, en español y
en inglés.

| Qué | Archivo | Clase o símbolo |
| --- | --- | --- |
| Página enrutada | `team-settings-page.ts` (+ `.html`) | `TeamSettingsPage`, selector `agl-team-settings-page` |
| Componente | `participant-tile.ts` | `ParticipantTile`, selector `agl-participant-tile` |
| Puerto | `room.port.ts` | `RoomPort` (clase abstracta) |
| *Facade* | `room.facade.ts` | `RoomFacade` |
| Adaptador HTTP | `http-teams.api.ts` | `HttpTeamsApi` |
| Otro adaptador | `livekit-room.adapter.ts` | `LiveKitRoomAdapter` |
| Modelo de dominio | `turn.ts` | `Turn` |
| Interceptor, *guard*, *pipe* | `auth.interceptor.ts`, `admin.guard.ts`, `local-date.pipe.ts` | `authInterceptor`, `adminGuard` (funciones), `LocalDatePipe` |
| Proveedores de un módulo de `core` | `provide-logging.ts` | `provideLogging()` |
| Prueba | junto al archivo, `*.spec.ts` | — |

- Archivos en `kebab-case`; clases y tipos en `PascalCase`; el resto en
  `camelCase`; constantes globales en `UPPER_CASE`. *(ESLint.)*
- **La etiqueta de un rol viene de la API** (`label`: `member`, `scrum_master`, `admin`) y se traduce
  con `app.role_labels.<label>`; el cliente no la deriva ni decide nada con ella. Lo que una pantalla
  ofrece sigue al `role` (`admin`/`member`). Los mensajes que nombran a quien administra el equipo
  reciben su etiqueta como parámetro (`{{ admin }}`) o se redactan sin nombrarla. El encabezado
  muestra el equipo y la etiqueta a través de `ShellContext` (`@core/shell`).
- **Una clase por archivo**, con el nombre de la clase en `kebab-case`: `TenantNotFoundError` va en
  `tenant-not-found-error.ts`. Una interfaz o un tipo viaja con la clase que describe
  ([code-conventions.md](../docs/code-conventions.md)).
- Los componentes no llevan sufijo `Component` (guía de estilo de Angular 20+).
- Selectores con prefijo `agl`. *(ESLint.)*
- Dentro de una misma funcionalidad, importaciones relativas; entre zonas,
  alias: `@core/*`, `@shared/*`, `@layout/*`, `@features/*` (este último solo
  en `app.config.ts` y `app.routes.ts`) y `@testing/*` en pruebas.
- Importaciones ordenadas por grupos (Angular y librerías, alias, relativas)
  y alfabéticamente. *(ESLint, se corrige con `--fix`.)*

## Componentes

- *Standalone* (el valor por defecto) y `OnPush` (el valor por defecto en
  Angular 22). No se escribe `standalone: true` ni `changeDetection`.
- Dependencias con `inject()`, nunca por constructor. *(ESLint.)*
- Entradas y salidas con `input()`, `input.required()`, `output()` y
  `model()`; consultas con `viewChild()` y `contentChild()`. *(ESLint.)*
- Plantilla en archivo aparte (`templateUrl`) y los estilos como clases de Tailwind en
  ella; control
  de flujo nativo (`@if`, `@for`, `@switch`), con `track` en todo `@for`.
- Lo que solo usa la plantilla es `protected`; lo que nadie fuera usa,
  `private`. Nunca `public` explícito. *(ESLint.)*
- Una página lee signals de su *facade* y le delega las acciones: no hace
  peticiones, no se suscribe a observables ni contiene reglas de negocio.
- Los componentes de `shared/ui` son de presentación pura: reciben entradas y
  emiten salidas, sin *facades* ni servicios.
- Nada de lógica en el constructor más allá de inicializar campos.

## Estado y reactividad

- **Signals para el estado,** rxjs solo en los bordes (HTTP, eventos de
  LiveKit). Un adaptador puede devolver `Observable`; la *facade* lo convierte
  en signals.
- Las lecturas de datos usan `rxResource` (o `resource`), que ya expone
  `isLoading`, `status`, `error` y `reload()`. Ver `StatusFacade`.
- Una *facade* expone signals de solo lectura (`computed` o `.asReadonly()`):
  la presentación no escribe el estado, llama métodos.
- Una *facade* se provee en la página (`providers: [RoomFacade]`) para que viva
  y muera con ella. Solo va a `providedIn: 'root'` si su estado debe sobrevivir
  a la navegación (por ejemplo, la sesión).
- Si un componente o una *facade* tiene que suscribirse a mano, lo hace con
  `takeUntilDestroyed()`. *(ESLint verifica que se use en un contexto válido.)*
- `effect()` solo para sincronizar con el mundo exterior (DOM, LiveKit,
  `localStorage`), nunca para derivar estado: para eso está `computed()`.

## Formularios

Un solo estilo para todos los formularios (el de `/:tenant/activate`, el de `/:tenant/teams/new`, el diálogo de invitar de `/:tenant/teams/:teamId/settings` y el del sprint de `/:tenant/teams/:teamId/settings/sprint`):

- **`FormsModule` con signals:** cada campo es un `signal` de la página, atado con
  `[ngModel]="name()"` y `(ngModelChange)="name.set($event)"`. No se usan `FormGroup` ni
  Reactive Forms. El formulario se envía con `(submit)="submit(); $event.preventDefault()"` y
  lleva `novalidate`: la validación es la nuestra, no la del navegador.
- **La regla vive en `domain`** como función pura (`teamNameProblem` en
  `features/teams/domain/team-name.ts`, `checkPasswordInput` en
  `features/identity/domain/password-input.ts`), con su prueba sin `TestBed`. La página la usa
  en un `computed` (o la *facade* al enviar); no se repite la regla en otro lado.
- **La validación del cliente es comodidad; la autoridad es la API.** La API aplica la misma
  regla y responde con un `code` estable; la *facade* lo convierte en un problema que la
  pantalla traduce, o en un error genérico traducido cuando no hace falta distinguirlo.
- **Un error de la API se lee en un solo lugar:** `readApiError` (`@core/http/api-error`) extrae
  `error.code`, `error.details.reasons` y `error.request_id` del cuerpo único
  ([AD-30](../docs/adr/0030-un-solo-formato-de-error-http-y-un-catalogo-de-la-api.md)). El
  `message` es para desarrolladores y no se muestra; el adaptador decide siempre por `code`.
- El botón de enviar (`aglButton`) queda deshabilitado mientras el formulario no se pueda
  enviar o se esté guardando. Los mensajes de validación se muestran cuando el usuario ya
  escribió en el campo o salió de él.
- Todo control (`input[aglTextField]`) tiene su `<label for>`, y el mensaje de error se asocia
  con `aria-describedby` y `aria-invalid`; un error del envío se anuncia con `role="alert"`.
- El envío lo hace la *facade*; la página solo decide adónde navegar con el resultado.

## Comunicación con la API

- Solo los adaptadores de `infrastructure` usan `HttpClient`. *(ESLint.)*
- La URL base sale de `RUNTIME_CONFIG.apiUrl`; nunca se escribe una URL.
- El adaptador define la forma del JSON de la API (`HealthResponse`) y la mapea
  al modelo de dominio: el contrato no se filtra a `application` ni a la
  pantalla. Los campos del JSON conservan el nombre de la API.
- Un cambio que rompe el contrato con la API se marca con `BREAKING CHANGE`.

## Sala de LiveKit

- `livekit-client` solo se importa en el adaptador de la sala, dentro de
  `features/ceremonies/infrastructure`, detrás de un puerto que habla el
  lenguaje del dominio (participantes, turno, estado de Agilina).
- El token de la sala lo pide el adaptador HTTP a la API; nunca se genera en
  el cliente.
- Los controles de la ceremonia viajan como mensajes por el canal de datos de
  la sala, dirigidos al agente. Su formato es un contrato con el worker y se
  documenta en [docs/contrato-worker-api.md](../docs/contrato-worker-api.md)
  cuando se defina.
- La pantalla no muestra transcripción en vivo.
- **Puertos** (AGI-60): `RoomAccessPort` (el token, `HttpRoomAccessApi` sobre
  `POST /v1/teams/{team_id}/dailies/current/token` de AGI-59) y `RoomPort` (la sala,
  `LiveKitRoomAdapter`). `RoomFacade`, provista en `RoomPage`, los orquesta; salir de la página
  sale de la sala.
- **Cada conexión pide un token nuevo** (la primera, **Reintentar** y la que sigue a un token
  rechazado, una sola vez): el token vive en memoria para esa conexión y no se guarda ni se
  registra. La URL del servidor (`livekit_url`) llega con él, así que la web no tiene ninguna
  variable ni credencial de LiveKit.
- **El micrófono se pide primero**, al abrir la sala y antes de conectar (`RoomPort.requestMicrophone`):
  la persona responde la pregunta del navegador y entra con él listo, que se publica al conectar
  (`enableMicrophone`). Pedirlo antes también hace que el navegador muestre a WebRTC sus direcciones
  reales (sin permiso, Chromium las esconde tras nombres mDNS). Si se niega (`NotAllowedError`), no hay (`NotFoundError`),
  está ocupado o la página no es segura (HTTPS o `localhost`, `SECURE_CONTEXT`), la persona entra
  igual como **oyente**, con una alerta que explica qué hacer y **Reintentar micrófono**. Los
  errores del dispositivo se leen con `MediaDeviceFailure` del SDK.
- **Reconexión:** el SDK reintenta solo con las esperas de `reconnect-budget.ts`. Como un intento
  que se cuelga alarga la espera, `RoomFacade` además lleva su propio reloj: si 30 s
  (`RECONNECT_BUDGET_MS`) después de «Reconectando…» no volvió, sale de la sala y muestra
  «Desconectado» con **Reintentar** y **Volver al dashboard**. LiveKit nota la caída por sus pings,
  así que «Reconectando…» puede tardar unos segundos en aparecer.
- **Audio de los demás:** cada pista de audio se reproduce con un `<audio>` en un contenedor oculto
  que crea el adaptador. Si el navegador bloquea la reproducción automática, la pantalla ofrece
  **Activar audio** (`room.startAudio()`, en un gesto de la persona).
- La prueba del adaptador usa un `Room` falso que entrega `LIVEKIT_ROOM_FACTORY`: ninguna prueba
  unitaria abre una conexión.

## Tenants: una organización por dirección ([AD-29](../docs/adr/0029-un-tenant-es-una-organizacion-con-su-base-y-su-realm.md))

Cada tenant es una organización con su propia base de datos, su propio realm y su propio login. En la
web es el **primer segmento de la dirección**: `/acme/teams`, `/acme/activate#t=…`, `/acme/status`.

- `/:tenant` solo abre las rutas de la organización si el segmento puede ser un nombre de tenant
  (`tenantMatch`); si no, o si la API dice que no existe (`tenantGuard` pregunta a `GET /v1/tenant`
  antes de llevar a nadie a iniciar sesión en un realm que no está), es la página «no encontrada».
  `/` no nombra ninguna organización.
- `TenantContext` (en `core/tenant`) guarda el tenant de la dirección y arma las rutas de la
  organización: `tenant.path('teams', id)` para `routerLink` y `navigate`, `tenant.url(...)` para una
  dirección. **Ningún enlace interno escribe `/teams`**: lleva el tenant.
- `authInterceptor` pone `X-Agilina-Tenant` en toda llamada a la API (y solo a la API); sin él la API
  responde `400`. La comprobación del tenant va sin sesión (`WITHOUT_SESSION`).
- El realm es `AGILINA_TENANT_REALM_PREFIX` más el nombre del tenant (`agilina-acme`) y cada tenant
  tiene su propia sesión de `keycloak-js`: estar dentro de uno no te mete en otro.

## Autenticación y autorización

- La sesión la resuelve Keycloak (OIDC, *authorization code* con PKCE), con la **página de login
  de Keycloak** y `keycloak-js` directo ([AD-28](../docs/adr/0028-iniciar-sesion-con-keycloak.md)).
  La integración vive en `core/auth`, detrás del puerto `AuthSession`: nadie más importa
  `keycloak-js`.
- La sesión se pide **cuando algo la necesita**, no al arrancar: `authGuard` (rutas restringidas),
  `entranceGuard` (`/:tenant`) y `authInterceptor`. Las pantallas públicas (`/:tenant/activate`,
  `/:tenant/status`) nunca llevan a iniciar sesión.
- `authInterceptor` envía el token **solo a la API** (nunca a Keycloak ni a otro host) y, ante un
  401, lleva a iniciar sesión y de vuelta a la página donde estaba. Un *guard* también vuelve a la
  página pedida.
- **Una sesión válida sin cuenta activa en la organización no vuelve a iniciar sesión** (AGI-123):
  la API responde `403 account_not_active` y el interceptor lleva a `/:tenant/account-not-active`
  (`AccountNotActivePage`, de `identity`), que explica el caso y ofrece **Cerrar sesión**
  (`AuthSession.signOut()`). Un 401 que llega justo después de volver del login (antes de que la
  API acepte la sesión: `AuthSession.justSignedIn()`) va a la misma página en vez de a Keycloak,
  porque iniciar sesión otra vez solo repetiría el rebote. Pasada la primera respuesta
  exitosa (`confirmSession()`), un 401 vuelve a significar token vencido.
- El token vive **solo en memoria**: nunca en `localStorage` ni `sessionStorage`.
- Las rutas restringidas usan un *guard* y los elementos restringidos se
  ocultan según el rol interno, pero **la autorización es de la API**: un
  *guard* es comodidad para el usuario, no seguridad.
- Con un solo equipo, el selector (`/:tenant/teams`) entra directo a él. Cerrar sesión y la expiración
  por inactividad son HU-09.

## Fechas y zonas horarias

- La API envía y recibe instantes en ISO 8601 con zona UTC (`...Z`) y fechas de calendario
  como `AAAA-MM-DD`, sin hora.
- Al enviar, `date.toISOString()`. Al mostrar, `Intl.DateTimeFormat` con el
  idioma activo como *locale* y sin `timeZone`, de modo que usa la del
  navegador. Todo eso vive en funciones puras de `shared/utils/local-date-time.ts`:
  `localDateTimeToIso` (una hora de pared en una fecha, al instante UTC), `localTimeOf`,
  `formatLocalDateTime` y `formatCalendarDate` (una fecha de calendario se arma a medianoche
  local y se formatea en la misma zona, así nunca se corre un día).
- Lo que cambia con la hora (la sala abierta, la daily que ya empezó) lee el instante del token
  `NOW` (`core/time/now.ts`), que una prueba fija con `TestClock` (`@testing/now`) en vez de
  depender de la hora de la máquina. `formatLocalTime` y `formatShortLocalDate` dan la hora y el
  día corto («02:15 p. m.», «jue, 17 de sept») de un instante en la zona del navegador.
- No se guarda ni se calcula con zonas horarias por equipo: no existen. La única excepción es la
  **zona de captura de la hora de la daily**
  ([AD-31](../docs/adr/0031-guardar-la-hora-de-la-daily-en-utc-con-su-zona-de-captura.md)): al
  guardar el sprint, la web envía la hora elegida en el día de inicio como instante UTC junto con
  la zona IANA del navegador de quien guarda (`BROWSER_TIME_ZONE`, de `core/time`, que una prueba
  puede fijar). La API fija con ella el calendario del sprint y calcula la próxima daily
  (`next_daily_at`); la web solo la formatea en la zona de quien la ve, sin recalcular el horario
  de verano.

## Textos e i18n

- Ningún texto de usuario en el código ni en las plantillas: siempre una clave
  de los catálogos `public/i18n/es.json` y `en.json`.
- Claves en inglés, anidadas por funcionalidad y en `snake_case`:
  `status.error_hint`, `teams.settings.title`. Lo común a toda la aplicación,
  bajo `app`.
- En plantillas, la directiva estructural con prefijo, una vez por plantilla:

  ```html
  <section *transloco="let t; prefix: 'status'">
    <h1>{{ t('title') }}</h1>
  </section>
  ```

- En código (raro: casi todo texto vive en plantillas), `translateSignal()`.
- El idioma inicial es el del navegador; el definitivo es un atributo del
  equipo y llega de la API. `<html lang>` se actualiza solo.
- Una clave faltante se registra como advertencia y se muestra como la clave
  misma: un error visible, no un hueco en blanco.
- Una prueba falla si una clave existe en un idioma y no en el otro, o si un
  texto está vacío.
- **La interfaz sigue el idioma activo, aunque el mockup no lo haga.** Los mockups (Lovable)
  mezclan inglés en la versión en español: «Daily», «Retro», «Review», «Daily Stand-up». No se
  copian: cada texto va en el idioma de la persona y, en español, la ceremonia es **la reunión
  diaria** («Hora de la reunión diaria», «Orden de turnos de la reunión diaria»), no «la daily».
  Lo mismo vale para los nombres de ceremonias, estados y acciones. Se quedan igual en todos los
  idiomas los nombres propios y las marcas (Agilina, Scrum Master, Slack, Jira, Keycloak). En
  inglés el término es «daily» o «daily stand-up». Cuando el mockup y esta regla no coinciden,
  manda la regla (ver «Diferencias con el backlog» en `context/mockups.md`).

## Notificaciones (toasts)

Un **toast** es un aviso corto que confirma que una acción salió bien o que no funcionó. Aparece
abajo a la derecha (en el móvil, abajo y a todo el ancho) **sin mover lo que hay en la pantalla**.
Es la única forma de confirmar una acción; ninguna pantalla pinta su propio «Guardado.» dentro de
la página.

| Tipo | Cuándo | Aspecto | Dura |
| --- | --- | --- | --- |
| `success` | La acción salió bien: «Sprint guardado.», «Rol de Ana Gil actualizado.» | Verde (`success`), ícono `circle-check` | 5 s; no se va mientras el puntero o el foco estén sobre él |
| `error` | La acción falló y hay algo que leer o reintentar | Rojo (`danger`), ícono `circle-alert` | Hasta que se cierra con la X |

- **Cómo se pide:** `inject(Notifier)` (`@core/notifications/notifier`) y
  `notifier.success('teams.sprint.saved')` o `notifier.error('teams.sprint.save.failed', {…})`. Se
  le da la **clave** del texto y sus parámetros, nunca el texto: se traduce al idioma activo en el
  momento. Los dos textos (ES y EN) se agregan a los catálogos como cualquier otro.
- **Dónde se dibuja:** una sola vez, en el componente raíz (`agl-toast-list`, de `shared/ui`), así
  que un aviso sobrevive a un cambio de pantalla y sale por encima de cualquier marco. Muestra
  hasta 3 a la vez: uno nuevo desplaza al más antiguo.
- **Colores:** solo de los tokens (`success` y `danger`, en `tokens.css`), con su ícono: el color
  no es la única señal. No se escriben colores sueltos.
- **Accesibilidad:** las dos regiones (`role="status"` para los éxitos y `role="alert"` para los
  errores) existen siempre en la página, vacías si no hay avisos, porque un lector de pantalla
  anuncia lo que se agrega a una región que ya estaba, no una región que aparece con su mensaje. El
  foco no se mueve al aviso. El botón de cerrar tiene nombre (`app.notifications.close`).
- **Qué NO es un toast:**
  - un error de **validación** va junto a su campo, con `aria-describedby`, porque señala qué
    corregir;
  - un error **dentro de un diálogo** (invitar, eliminar a alguien) se queda en el diálogo: el
    diálogo modal tapa cualquier toast y la persona sigue ahí para corregir o reintentar;
  - un estado de **carga** («Cargando…») o de **página** («No tienes acceso», la cuenta activada)
    es contenido de la página.
- **Cómo se prueba:** el servicio con `jasmine.clock()` (ver `notifier.spec.ts`); una pantalla
  comprueba lo que pidió con `TestBed.inject(Notifier).notifications()` y no busca el texto en
  su plantilla; en los e2e se busca por `data-testid` (`toast-success`, `toast-error`,
  `toast-message`).

## Errores y registro

El estándar es un **puerto `Logger`** (`@core/logging/logger`) con entradas
estructuradas. Hoy lo atiende `ConsoleLogger`; enviar los registros a otro
destino es un adaptador nuevo en `provide-logging.ts`, sin tocar a quien
registra.

- **Forma de una entrada:** `level`, `message`, `timestamp` (ISO 8601 en UTC),
  `context` (objeto con claves en `camelCase`) y `error` cuando lo hay.
- **Niveles:** `debug` (diagnóstico), `info` (hitos: entrar a la sala), `warn`
  (algo anómalo que se recupera: una clave faltante, un reintento) y `error`
  (algo falló). El mínimo sale de `AGILINA_LOG_LEVEL`.
- **Mensajes** en inglés, cortos y estables, para poder buscarlos: `'HTTP
  request failed'`, no frases con datos interpolados. Los datos van en
  `context`.
- **Nunca** se registran tokens, contraseñas, correos completos, cuerpos de
  petición ni audio. El interceptor registra método, URL sin *query* y estado.
- **Un error se registra una vez, donde se maneja:**
  - los errores HTTP, en `httpErrorLoggingInterceptor`;
  - los no manejados, en `GlobalErrorHandler` (incluye los del `window`);
  - los demás (LiveKit, Keycloak), en el adaptador que los recibe.
- La *facade* convierte el error en estado de pantalla (`failed`) y la
  pantalla muestra un mensaje traducido; nunca se traga un error en silencio
  ni se muestra el mensaje técnico al usuario.
- `console.*` está prohibido fuera del adaptador. *(ESLint.)*

## Configuración

Lo que cambia entre entornos se lee de **variables de entorno en tiempo de
ejecución**: una sola imagen sirve para todos los entornos y no hay URLs
compiladas en el bundle.

```
variables de entorno ─▶ runtime-config.template.json ─▶ /config.json ─▶ main.ts ─▶ RUNTIME_CONFIG
```

- En desarrollo, `scripts/render-runtime-config.mjs` la genera antes de
  `ng serve` en `runtime/` (ignorada por git). En producción, nginx la genera
  con `envsubst` al arrancar el contenedor.
- `main.ts` la descarga y la valida (`parseRuntimeConfig`) **antes** de
  arrancar Angular, de modo que cualquier proveedor la lee de forma síncrona
  con `inject(RUNTIME_CONFIG)`. Una variable faltante impide arrancar, con un
  mensaje que dice cuál.
- `config.json` es público por naturaleza: **nunca lleva secretos.**

Variables que lee la web: `AGILINA_API_PUBLIC_URL`, `AGILINA_KEYCLOAK_URL`,
`AGILINA_TENANT_REALM_PREFIX` (el realm de un tenant es ese prefijo y su nombre),
`AGILINA_KEYCLOAK_WEB_CLIENT` y `AGILINA_LOG_LEVEL`.

Para agregar una: declárala en `.env.example`, pásala al servicio `web` en
`infra/docker-compose.yml`, agrégala a `runtime-config.template.json`, a
`RuntimeConfig` y a su validación (con prueba), y a `TEST_RUNTIME_CONFIG`.

## Estilos

Tailwind CSS 4 ([AD-27](../docs/adr/0027-dar-estilo-a-la-web-con-tailwind-css.md)): los
estilos de una pantalla son **clases de utilidad en su plantilla**.

- Los colores salen de los tokens `--agl-*` de `styles.css`, que Tailwind lee como tema:
  `bg-surface`, `bg-background`, `text-foreground`, `text-muted`, `text-accent`,
  `text-accent`, `text-accent-foreground` (texto sobre el color de acento), `text-danger`, `text-success`,
  `border-border`; con opacidad cuando hace falta un tono suave (`bg-accent/10`). **No se
  escriben colores sueltos** (`#fff`, `bg-blue-500`): un tema nuevo cambia los valores de las
  variables y nada más. Los valores son la paleta clara de los mockups (prototipo de Lovable).
- Tipografía: Inter para el texto y Plus Jakarta Sans para los títulos (`font-display`),
  autoalojadas con `@fontsource` (en `angular.json`): ninguna fuente se pide a un servidor
  externo.
- El marco de cada pantalla lo elige su ruta en `app.routes.ts`: `AppShell` (cabecera arriba)
  o `CenteredLayout` (marca centrada sobre una sola tarjeta, para el selector de equipo y su
  formulario).
- Lo que se repite no se copia: es una pieza de `shared/ui`. Hoy hay `agl-toast-list` (los
  avisos, ver «Notificaciones»), `aglButton`
  (con `variant="primary" | "secondary" | "danger"`; `danger` para lo que no se deshace, como
  eliminar a alguien del equipo), que va sobre un `<button>` o, si navega, sobre un
  `<a routerLink>` (un enlace sigue siendo enlace), `button[aglIconButton]` (solo ícono, con
  `aria-label`: el ojo y el bote de la tabla de integrantes), `input[aglTextField]` y
  `select[aglSelect]`: directivas sobre el elemento nativo. Una contraseña va dentro de
  `<agl-password-field [toggleLabel]="…">`, que agrega el botón para mostrarla u ocultarla (con
  `aria-pressed`) sin quitarle su `<label for>`. Una fecha de calendario se elige con
  `<agl-date-picker inputId="…" [(value)]="…">` y no con `<input type="date">`, cuyo calendario
  dibuja el navegador y no se puede agrandar ni darle estilo: abre un calendario propio con el
  teclado del patrón de WAI-ARIA (flechas, Re Pág/Av Pág, Inicio/Fin, Escape), los nombres de
  `Intl` en el idioma activo y `min` para los días que no se pueden elegir. El espacio y el ancho
  los pone quien coloca la pieza (`class="mt-4 w-full"`).
- Los diálogos usan `agl-dialog`, un componente sobre el `<dialog>` nativo (`showModal()`):
  el navegador atrapa el foco, deja inerte el resto de la página y lo cierra con Escape, sin
  dependencias. Se abre al colocarlo y se cierra al quitarlo, así que quien lo coloca decide
  con un `@if`; `(dismissed)` avisa que la persona lo cerró, y al cerrarse el foco vuelve a
  donde estaba. Lleva `labelledBy` con el id de su título, y `[dismissible]="false"` mientras
  guarda, para que Escape no lo cierre antes de saber el resultado.
- El orden de las clases lo decide Prettier (`make format`); no se discute en el review.
- Nada de estilos en línea (`style="…"`). *(ESLint.)*
- Un `.scss` de componente (`styleUrl`) es la excepción, solo para lo que las utilidades no
  expresan (por ejemplo una animación); se justifica en el pull request.
- Una prueba no busca un elemento por su clase de estilo: usa el texto, el rol o la etiqueta. Las
  de punta a punta (`tests/e2e`) usan `data-testid` (ver [docs/testing.md](../docs/testing.md)).
- Adaptable por defecto: se escribe primero para móvil y se amplía con `sm:`, `md:`…

## Accesibilidad

- Las reglas de accesibilidad de `angular-eslint` están activas: texto
  alternativo, etiquetas asociadas a sus controles, eventos de teclado junto a
  los de ratón y `type` en todo botón. *(ESLint.)*
- HTML semántico primero (`button`, `nav`, `main`, `dl`) y ARIA solo cuando no
  alcanza. En la sala, quién habla y el turno en curso se anuncian también en
  una región `aria-live`, no solo con color.

## Pruebas

| Qué | Cómo |
| --- | --- |
| `domain` y funciones puras | Pruebas unitarias sin `TestBed` |
| *facades* | Con el puerto falso (una clase que extiende el puerto), sin HTTP |
| Adaptadores HTTP | `provideHttpClientTesting()` y `HttpTestingController`: verifican URL, método y mapeo |
| Páginas y componentes | `TestBed` con el puerto falso y los catálogos reales (`provideTestI18n()`); verifican lo que ve el usuario |
| `core` | Cada pieza con sus dobles: `provideFakeLogger()`, `provideTestRuntimeConfig()` |

- Una prueba describe un comportamiento: `'warns when the API does not respond
  and retries on demand'`.
- Se afirma sobre el texto en español: si una clave se renombra o falta, la
  prueba falla.
- Sin zone.js: se espera con `await fixture.whenStable()`. Si una petición queda
  pendiente a propósito, `fixture.detectChanges()`.
- Las utilidades comunes viven en `src/testing` y se importan con `@testing/*`.
- Todo error corregido deja una prueba que lo habría detectado.

## Calidad (Definition of Done)

- Cero errores de análisis estático y ninguna advertencia nueva
  (`ng lint --max-warnings=0`).
- La lógica nueva lleva pruebas automatizadas, y el pipeline debe quedar en
  verde.
- Todo texto dirigido al usuario existe en español y en inglés.
- Los errores se manejan y se registran; no se tragan en silencio.
- No se revisa formato ni estilo en el Code Review: de eso se encargan Prettier
  y ESLint.

## Git

- GitHub Flow: `main` está protegida y todo entra por Pull Request.
- Las ramas se nombran `tipo/HU-nn-descripcion-corta`, en minúsculas y con
  guiones. Tipos: `feat`, `fix`, `chore`, `docs`, `spike`.
- Commits con Conventional Commits, en el formato `tipo(web): descripcion`, en
  español, en imperativo y en minúscula.
  - Tipos: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `build`,
    `ci`.
  - El cuerpo es opcional y explica el porqué, no el qué.
  - Todo commit termina con `Refs: AGI-nnn`.
  - Si se rompe un contrato con la API, se marca con `BREAKING CHANGE` en el pie.
- Cada commit tiene un solo autor. No se agrega `Co-Authored-By` ni líneas de
  atribución a Claude o a la sesión.

## Cómo agregar algo

**Una pantalla en una funcionalidad existente**

1. Si hay una regla nueva, va en `domain`, con su prueba sin `TestBed`.
2. Si necesita datos nuevos, declara el método en el puerto de `application` e
   impleméntalo en el adaptador de `infrastructure`, con su prueba.
3. Escribe o amplía la *facade* con signals de solo lectura.
4. Crea la página en `presentation`, con sus textos en los dos catálogos.
5. Agrega la ruta con `loadComponent` en `app.routes.ts`.
6. `make verify` en verde.

**Una funcionalidad nueva**

1. Crea `features/<contexto>/` con solo las capas que necesite. El nombre sale
   del glosario.
2. Enlaza sus puertos con sus adaptadores en `app.config.ts`.
3. Agrega su grupo de claves a los catálogos.
4. No hay que tocar `eslint.config.js`: las reglas de aislamiento se generan
   para cada carpeta de `features/`.

## Por decidir

Estos puntos no están decididos; se preguntan antes de decidir:

- Destino remoto de los registros (endpoint de la API, Sentry/GlitchTip u
  OpenTelemetry). Hoy solo consola.
- Migrar las pruebas de Karma a Vitest (el valor por defecto desde Angular 21;
  Karma está archivado).
- Librería de componentes (tablas, menús…) para `shared/ui`; si se adopta una, que se apoye
  en Tailwind (AD-27). Mientras tanto, los diálogos son `agl-dialog` sobre el `<dialog>`
  nativo (HU-06).
- Correr las pruebas de punta a punta (`make test-e2e`, Playwright) en la CI: hoy corren en
  local, contra el entorno levantado (AD-28).
