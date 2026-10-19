# Glosario del dominio (lenguaje ubicuo)

Un concepto tiene **un solo nombre** en el código, en la base de datos, en la
API y en la conversación del equipo. Esta tabla fija ese nombre en inglés (el
del código) y su equivalente en español (el de la documentación y el producto).
Si aparece un concepto nuevo, se agrega aquí antes de usarlo.

## Equipos y personas

| Código (EN) | Español | Qué es |
| --- | --- | --- |
| `Tenant` | Organización | Una empresa que usa Agilina: tiene su propia base de datos, su realm de Keycloak y su login, y contiene equipos (AD-29). Se nombra con un *slug* (`acme`) |
| `Team` | Equipo | Conjunto de personas que hace la daily. Dentro de un tenant, todo dato de negocio pertenece a un equipo |
| `TeamMember` (membresía) | Integrante | La pertenencia de una persona a un equipo, con su rol. Una persona puede tener roles distintos en equipos distintos |
| `AppUser` | Usuario | La identidad de una persona en Agilina; su contraseña y sus sesiones viven en Keycloak |
| `TeamRole` | Rol | El rol **interno** por equipo: `admin` o `member`. Es lo único contra lo que se autoriza |
| `admin` | Administrador | Rol que gestiona el equipo. En modo soporte se muestra como **Scrum Master** |
| `member` | Miembro | Rol de quien participa en la daily |
| Visible label | Etiqueta visible | Cómo se rotula un rol en pantalla: `scrum_master` (Scrum Master), `admin` (Administrador) o `member` (Miembro). Se **deriva** de rol + modo con `role_label`; no se guarda y nunca autoriza |
| Platform operator | Operador de la plataforma | Quien administra la instalación (no es un integrante); emite la invitación del primer Administrador |
| `TeamSelector` | Selector de equipo | Pantalla con los equipos a los que pertenece el usuario, para entrar a uno o crear uno nuevo |
| `TeamDashboard` | Dashboard del equipo | Pantalla de entrada a un equipo, a la que se llega desde el selector o al crearlo. Muestra el día N de M del sprint, la próxima daily, el modo (solo lectura) y la entrada a la sala. La lee `GET /v1/teams/{team_id}/dashboard` en una sola llamada (HU-12) |

## Acceso

| Código (EN) | Español | Qué es |
| --- | --- | --- |
| `Invitation` | Invitación | Permiso de un solo uso para entrar a un equipo con un rol. No hay registro público |
| `ActivationToken` | Token de activación | Secreto de un solo uso que viaja en el enlace de la invitación. Solo se guarda su hash |
| Activation | Activación | Aceptar una invitación: definir la contraseña y quedar como integrante del equipo con el rol asignado |
| `InvitationStatus` | Estado de la invitación | `pending`, `accepted`, `expired` o `revoked`. Caduca a los 7 días |
| Keycloak subject | Sujeto de Keycloak | El `sub` del token; la única unión entre `AppUser` y el proveedor de identidad |

## Modo y configuración

| Código (EN) | Español | Qué es |
| --- | --- | --- |
| `OperationMode` | Modo de operación | `support` (soporte) o `autonomous` (autónomo). Su único efecto: si Agilina pide aprobación antes de ejecutar una acción |
| `support` | Modo soporte | Un Scrum Master humano aprueba las acciones |
| `autonomous` | Modo autónomo | Agilina ejecuta y luego informa |
| `Language` | Idioma | `es` o `en`. Atributo del equipo; parametriza transcripción, plantillas, voz y resumen |
| `Sprint` | Sprint | Periodo de trabajo del equipo. Puede estar `planned`, `active` o `closed` |
| `SprintStatus` | Estado del sprint | `planned`, `active` o `closed`. Un equipo tiene a lo sumo un sprint `active`; mientras dura no se cambian roles (HU-06) |
| `SprintPeriod` | Periodo del sprint | Las fechas de calendario de inicio y fin (`start_date`, `end_date`), sin hora y ambas incluidas. Pueden caer cualquier día de la semana, y **todos los días del periodo cuentan**, sábado y domingo incluidos (AD-31) |
| `SprintPhase` | Fase del sprint | `not_started`, `in_progress` o `finished`, según la fecha de hoy en la zona de captura. Se **calcula**, no se guarda, y no es el `SprintStatus`: un sprint `active` puede no haber empezado o haber terminado ya |
| `SprintDay` | Día de sprint (día N de M) | M es la cantidad de días del periodo; N, el día en curso según la zona de captura: 0 antes del inicio, de 1 a M durante el sprint y M después del fin |
| `DailyTime` | Hora de la daily | La hora de pared a la que se convoca la daily, única para todo el equipo. Se guarda como un instante UTC de anclaje (`daily_time_utc`) más la zona de captura; cada integrante la ve en la zona de su navegador (AD-31) |
| `daily_time_zone` | Zona de captura | Zona IANA del navegador de quien guardó el sprint. Fija la hora de pared de la daily y el calendario del sprint (qué fecha es «hoy») |
| `MemberPreference` | Preferencia del integrante | Hora y zona del recordatorio matutino; lo único que el rol Miembro configura |

## La ceremonia

| Código (EN) | Español | Qué es |
| --- | --- | --- |
| `Ceremony` | Ceremonia | Una ocurrencia de la reunión. Hoy solo existe el tipo `daily`: hay una ceremonia por cada ocurrencia de la daily (equipo, sprint e instante, únicos), y con ella una sala nueva cada día |
| Daily | Reunión diaria | La reunión diaria de pie (*stand-up*). En la interfaz y en los correos en español se dice «reunión diaria», no «daily» ni «Daily Stand-up»; en inglés, «daily» o «daily stand-up» (ver «Textos e i18n» en la guía de la web) |
| Join window (`join_opens_at`, `join_closes_at`) | Ventana para unirse | El tiempo en que un participante puede entrar a la sala de una ceremonia: desde diez minutos antes de su inicio (`JOIN_WINDOW_LEAD`) hasta quince minutos después (`JOIN_WINDOW_TAIL`, sin incluirlo), para que quien llega tarde todavía entre (AGI-60). Fuera de ella, «Unirse a la sala» está deshabilitado. La daily que se puede unir es `joinable_daily_at`: la que está en curso dentro de esos quince minutos o, si no, la siguiente. Cuando la ceremonia sea un registro (AGI-62, HU-17), la ventana terminará al cerrarse |
| `Sprint.number` | Número del sprint | El número del sprint en su equipo («Sprint 12»): 1 para el primero y, desde ahí, el mayor que el equipo haya tenido más uno, cerrado o no. Lo asigna la API al guardar (`SprintRepository.next_number`, con el equipo bloqueado), no se envía ni se edita y nunca se reutiliza. No es el día del sprint (`day.number`, el «N» de «día N de M») |
| Daily occurrence | Ocurrencia de la daily | El instante UTC de una daily concreta: la hora de la daily en la zona de captura en una fecha del periodo, convertida a UTC. Hay una por cada día del periodo (`daily_occurrences`) |
| Daily participant (`sprint_participant`) | Participante de la daily | Integrante del equipo convocado a la daily del sprint, con su `turn_order` desde 1. El orden de la lista es el orden de turnos |
| `CeremonyStatus` | Estado de la ceremonia | `scheduled`, `in_progress`, `completed`, `cancelled` y `degraded` (siguió sin facilitación automática porque la transcripción no respondió). El resultado guarda el estado con el que la cerró el worker |
| `CeremonyContext` | Contexto de la ceremonia | Lo que el worker necesita saber antes de entrar a la sala. Lleva el `tenant` de la ceremonia, con el que el worker elige el realm en el que se autentica |
| `CeremonyResult` | Resultado de la ceremonia | Lo que el worker entrega a la API al cerrar: la transcripción atribuida y los eventos |
| `CeremonyEvent` | Evento de la ceremonia | Algo que pasó en la ceremonia, con su instante UTC y, si es de un participante, su `user_id`. Su tipo (`CeremonyEventType`) es uno de `ceremony_started`, `turn_started`, `turn_ended`, `degraded` y `ceremony_closed` |
| `Roster` | Roster | Lista ordenada de los participantes convocados y su rol |
| Turn | Turno | El momento en que un participante habla; los turnos siguen un orden fijo |
| `turn_order` | Orden de turno | Posición del participante en la ronda, desde 1 |
| Silence threshold | Umbral de silencio (X) | Segundos de silencio tras los que Agilina pregunta |
| Stuck-turn threshold | Umbral de turno trabado (Y) | Segundos sin avance tras los que Agilina interviene |
| Wake word | Palabra de activación | Palabra con la que se le habla a Agilina durante la ceremonia |
| Degraded mode | Modo degradado | La transcripción no responde: Agilina lo anuncia y la ceremonia sigue sin facilitación automática |
| Room | Sala | La sala de audio de LiveKit de una ceremonia. Se llama `<tenant>-<ceremony_id>` (`room_name_for`) |
| Connection status | Estado de la conexión | Cómo está el participante en la sala: `connecting` (Conectando…), `connected` (Conectado), `reconnecting` (Reconectando…: se cayó la red y LiveKit lo intenta solo, hasta 30 s) y `failed` (Desconectado, con el motivo y, si sirve, **Reintentar**) |
| Listener | Oyente | Participante que está en la sala sin micrófono (lo negó, no tiene o requiere HTTPS): escucha al equipo, pero nadie lo escucha. Puede reintentar el micrófono sin salir |
| `room_identity` | Identidad de sala | Identidad con la que alguien entra a LiveKit, `str(user_id)`; con ella se atribuye lo que dice, sin diarización |
| `TranscriptSegment` | Segmento de transcripción | Fragmento final de texto atribuido a quien lo dijo, con marcas de tiempo |

## Lo que sale de la ceremonia

| Código (EN) | Español | Qué es |
| --- | --- | --- |
| Blocker | Bloqueo | Impedimento detectado en la ceremonia |
| Issue mention | Mención de issue | Referencia a un ticket del tablero (Jira) |
| `ActionItem` | Action item | Acción derivada de la ceremonia, con su estado: propuesto, aprobado, rechazado, ejecutado o fallido. Rechazar no borra |
| `ApprovalRequest` | Solicitud de aprobación | En modo soporte, el mensaje de Slack con una casilla por action item |
| Post-processing | Post-procesamiento | El razonamiento con el LLM, una sola vez al cerrar la ceremonia (AD-19) |

## Arquitectura

| Código (EN) | Español | Qué es |
| --- | --- | --- |
| Bounded context | Contexto delimitado | Frontera dentro de la cual un término tiene un solo significado (`identity`, `teams`, `ceremonies`…) |
| Aggregate / aggregate root | Agregado / raíz | Grupo de objetos que se modifica como una unidad a través de su raíz |
| Value object | Objeto de valor | Valor inmutable definido por sus atributos y validado al crearse |
| Port | Puerto | Interfaz que el núcleo declara para hablar con el mundo exterior |
| Adapter | Adaptador | Implementación concreta de un puerto para un proveedor |
| Command / query | Comando / consulta | Operación que cambia estado / operación que solo lee |
| Composition root | Raíz de composición | El único lugar que enlaza puertos con adaptadores |
