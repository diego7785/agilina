# Ciclo de vida del agente

Cómo llega Agilina a la sala de una ceremonia, qué hace mientras espera, cómo se entera la web de
su estado y qué pasa cuando no llega (AGI-62), y cómo habla y qué pasa cuando su voz falla
(AGI-69). Lo que el worker le pide a la API está en
[contrato-worker-api.md](contrato-worker-api.md); por qué Agilina no manda audio a los detectores
de LiveKit en la nube, en
[AD-32](adr/0032-no-enviar-audio-a-los-detectores-de-livekit-en-la-nube.md).

```
make agent ─► worker registrado en LiveKit (sin agent_name)
                │
la API crea la sala (CreateRoom, primer token)
                │
LiveKit despacha el trabajo ─► subproceso de esa ceremonia
                                 ├─ se une con AUDIO_ONLY
                                 ├─ pide el contexto a la API (una vez)
                                 ├─ publica agilina.state = standby | no_facilitation
                                 ├─ espera a la primera persona y saluda una vez
                                 └─ queda en espera, sin transcribir
                                      … hasta que la sala se cierra
```

## 1. Registro del worker

`make agent` levanta el servicio `agent` del compose (perfil `voice`), que corre
`python -m agilina_agent.main start`. Antes de registrarse, el worker reenvía una vez los resultados
que quedaron en disco sin que la API los aceptara (ver
[entorno-local.md](entorno-local.md#resultados-pendientes-del-worker)). Después abre una conexión
**saliente** a LiveKit con `AGILINA_LIVEKIT_URL`, `AGILINA_LIVEKIT_API_KEY` y
`AGILINA_LIVEKIT_API_SECRET`: no escucha en ningún puerto.

- **Modo `start`**, no `dev`: `dev` está deprecado, recarga el código y enciende por defecto los
  detectores en la nube (AD-32). `start` precalienta procesos para que el subproceso de una sala
  arranque rápido, escribe logs en `INFO` y **no se recarga solo**: después de cambiar `agent/src`
  hay que reiniciar el contenedor (`docker compose -f infra/docker-compose.yml --env-file .env
  restart agent`).
- **Carga:** con `start` el worker se declara no disponible cuando la carga de la máquina supera
  `load_threshold` (0,7 por defecto en livekit-agents). En un portátil muy cargado LiveKit puede
  dejar de despacharle salas; la web lo verá como «No disponible».
- **Sin `agent_name`:** el worker se registra sin nombre, así que LiveKit le despacha **toda sala
  nueva** del proyecto (despacho automático). Nadie tiene que invitar a Agilina.
- **Permisos** (`worker_options`, AGI-145): son los que LiveKit pone en el token del agente cuando
  le despacha una sala. El worker declara el mínimo que usa:

  | Permiso | Valor | Para qué |
  | --- | --- | --- |
  | `can_publish` | sí, solo la fuente `MICROPHONE` | La voz de Agilina; ni cámara ni pantalla |
  | `can_subscribe` | sí | Recibir el audio de la sala (en espera no se usa) |
  | `can_update_metadata` | sí | Publicar su atributo `agilina.state` |
  | `can_publish_data` | no | Agilina no manda nada por el canal de datos; recibir no necesita el permiso |
  | `hidden` | no | Aparece en la sala, como participante de tipo agente |

  `WorkerPermissions` no ofrece `roomAdmin`, así que el agente nunca lo tiene: no silencia ni saca
  a nadie.

## 2. Despacho al crear la sala

La API crea la sala `<tenant>-<ceremony_id>` en LiveKit (`CreateRoom`, solo con el nombre) cuando
emite el primer token de la daily ([sala-y-emision-del-token.md](sala-y-emision-del-token.md)).
LiveKit despacha en ese momento un trabajo al worker registrado, emite el token del agente con los
permisos de arriba y el worker lanza un **subproceso dedicado a esa ceremonia** (`entrypoint`). Un
fallo en una sala no afecta a las demás.

El despacho ocurre **una vez por sala**: mientras la sala siga abierta LiveKit no vuelve a
despachar, aunque el subproceso haya caído. Si Agilina cae, vuelve en la siguiente sala.

## 3. El subproceso de la ceremonia

`RoomJob.run` (`agent/src/agilina_agent/presentation/room_job.py`):

1. **Se conecta** con `AutoSubscribe.AUDIO_ONLY`: nunca recibe video.
2. **Pide el contexto** a la API (`GET /v1/ceremonies/{id}/context`), con el tenant y la ceremonia
   que salen del nombre de la sala. Es una sola petición, **sin reintento**: cualquier fallo, o una
   sala que no se llama como una ceremonia, deja la ceremonia sin facilitación.
3. **Publica su estado** en el atributo `agilina.state`: `standby` con contexto, `no_facilitation`
   sin él.
4. **Espera a la primera persona** (`wait_for_participant`, una sola vez): la API crea la sala justo
   antes de que la persona entre y el agente puede llegar primero. Así nunca saluda a una sala
   vacía, y saluda **una vez por sala**, no cada vez que alguien entra.
5. **Saluda** por voz:
   - con contexto, `standby_greeting` en el idioma del equipo (`context.language`), con el día N de
     M del sprint, e invita a pulsar «Iniciar reunión diaria»;
   - sin contexto, `context_unavailable` en el idioma por defecto del worker
     (`AGILINA_DEFAULT_LANGUAGE`): no va a facilitar y pueden continuar sin ella.

   Las plantillas están en `shared/src/agilina_shared/i18n.py`. La voz es real con
   `AGILINA_ELEVENLABS_API_KEY` (`ElevenLabsSynthesizer`, §9); sin llave es simulada
   (`RecordingSynthesizer`) y el texto sale en el log del worker como `[simulated voice · es] …`.
   Si la voz real no suena en 5 s o ElevenLabs la rechaza, el saludo se publica por escrito en
   `agilina.text` (§6), se registra el motivo y la reunión sigue.

## 4. En espera, sin transcribir

En `standby` Agilina está suscrita al audio de la sala, pero **no lo lee**:

- el transcriptor (`WhisperTranscriber`) se inyecta en `RoomJob` y en espera nunca se llama: no hay
  peticiones al servicio de transcripción ni consumo de GPU;
- la `AgentSession` de la voz solo habla: sin STT, sin LLM, `vad=None`, `audio_input=False`,
  fin de turno manual e interrupciones apagadas (AD-32);
- la sesión se abre con `record=False`: LiveKit no graba nada, aunque el proyecto lo tenga
  habilitado.

Nada de lo que se dice antes de iniciar la ceremonia se transcribe, se guarda ni se registra. Lo
que hace Agilina al pulsar «Iniciar reunión diaria» llega con AGI-65.

## 5. Fallo y salida

- **Si Agilina no llega**, o cae antes de decir su estado, la web no se bloquea: la tarjeta
  «Estado de Agilina» dice «Llegando…» y, **30 s** después de que la persona quedó conectada
  (`AGILINA_ARRIVAL_BUDGET_MS`), pasa a «No disponible» con el aviso «Agilina no pudo unirse; la
  reunión puede continuar sin ella». Si después llega con un estado, la tarjeta pasa a ese estado.
  Si sale de la sala después de quedar en espera, la tarjeta pasa a «No disponible» con el aviso
  y no vuelve en esa sala: LiveKit despacha una sola vez por sala (§2).
- **Si el subproceso falla** (por ejemplo, LiveKit rechaza la conexión), LiveKit termina el trabajo
  y corre sus *shutdown callbacks*: se cierran el cliente HTTP de la API, el del transcriptor y,
  con voz real, la sesión de ElevenLabs. Las personas siguen en la sala.
- **Salida normal:** el subproceso vive mientras viva la sala. La API crea la sala sin
  `empty_timeout`, así que LiveKit la cierra con su valor por defecto cuando se vacía; con eso
  termina el trabajo y corren los mismos *shutdown callbacks*.

## 6. Contrato con la web: `agilina.state`

Agilina publica su estado como **atributo de participante**, no como mensaje: es estado, no un
evento, y quien entra tarde lo lee de la presencia. Las personas no necesitan `canPublishData`.

| Clave | Valor | Lo publica | La web muestra |
| --- | --- | --- | --- |
| `agilina.state` | `standby` | El agente, con contexto | «En espera» |
| `agilina.state` | `no_facilitation` | El agente, sin contexto | «Sin facilitación» |
| — | sin atributo, dentro del plazo | — | «Llegando…» |
| — | sin atributo, plazo vencido | — | «No disponible» y el aviso |
| `agilina.text` | la última frase que su voz no pudo decir | El agente, cuando ElevenLabs falla o no suena en 5 s | «Agilina no pudo hablar y lo dejó por escrito:» y la frase, en una región `aria-live` |
| `agilina.text` | vacío | El agente, cuando su voz vuelve a sonar | Nada: el texto viejo desaparece |

- Cada clave vive en dos constantes, una en cada desplegable: `STATE_ATTRIBUTE` y
  `TEXT_ATTRIBUTE` en `agent/src/agilina_agent/presentation/room_job.py`, y
  `AGENT_STATE_ATTRIBUTE` y `AGENT_TEXT_ATTRIBUTE` en
  `web/src/app/features/ceremonies/infrastructure/livekit-room.adapter.ts`. No hay catálogo
  compartido entre Python y TypeScript: un valor nuevo se agrega en los dos lados en el mismo
  cambio.
- La web solo cuenta el atributo de un participante **agente** (`participant.isAgent`) con un valor
  que conoce: una persona no puede falsear el estado de Agilina ni escribir como ella, y un valor
  desconocido se trata como si no hubiera llegado.
- `agilina.text` es estado, no un evento: quien entra tarde ve la última frase no dicha. Lleva una
  plantilla en el idioma del equipo (no es transcripción) y la web la muestra escapada, nunca como
  HTML. Usa el mismo permiso que `agilina.state` (`can_update_metadata`); el canal de datos sigue
  cerrado.
- Las claves `lk.*` (como `lk.agent.state`, que escribe `AgentSession`) son de LiveKit: no se usan
  ni se escriben como contrato propio.

## 7. Una sola copia por entorno

LiveKit **reparte las salas entre todos los workers registrados** en un proyecto con despacho
automático. Con dos copias encendidas contra las mismas claves, una ceremonia puede caer en el
worker equivocado (otra máquina, otra versión del código, el del spike de HU-01) sin que nadie lo
note. Por eso:

- **un proyecto de LiveKit por entorno y por desarrollador**: nadie comparte las claves de LiveKit
  de su `.env` con otra persona ni con otro entorno;
- **un solo servicio `agent`**, con `container_name: agilina-agent` fijo en el compose, que impide
  levantar una segunda copia con `--scale`;
- **no correr a la vez** el spike de voz, otro `make agent` (otro checkout, otra máquina) ni un
  worker a mano contra el mismo proyecto.

El `container_name` solo protege dentro de un compose: LiveKit no impide dos workers con las
mismas claves. Si algún día hace falta compartir un proyecto, el despacho se vuelve explícito
con un nombre de agente (`LIVEKIT_AGENT_NAME`, o `LIVEKIT_AGENT_NAME_OVERRIDE`, que livekit-agents
lee al registrarse); eso exige que la API lo despache al crear la sala y no se hace hoy.

## 8. Cómo se verifica

- **Registro:** `make logs s=agent` muestra el registro del worker y, por cada sala, `received job
  request` con `"agent_name": ""` y `"enable_recording": false`. Un `true` ahí quiere decir que el
  proyecto de LiveKit tiene la grabación habilitada; la sesión igual no graba (`record=False`), pero
  se revisa en la consola de LiveKit Cloud que la observabilidad del proyecto siga apagada: se
  enciende desde la consola sin cambiar código.
- **Saludo:** «Agilina joined room …» y, sin llave de ElevenLabs, la línea `[simulated voice · …]`
  con el saludo; con llave, las líneas de la voz de §9 («ElevenLabs started speaking in N ms …» y
  «ElevenLabs spoke N characters …»).
- **Pruebas automáticas:** las de `tests/agent/` y las de la sala en Karma y en la e2e, descritas en
  [testing.md](testing.md#de-punta-a-punta). La verificación con varias personas está en
  [sala-y-emision-del-token.md](sala-y-emision-del-token.md#probar-la-sala-contra-livekit).

## 9. Voz de Agilina y consumo de ElevenLabs

Lo que dice Agilina sale de las plantillas (AD-19) y suena con ElevenLabs (AGI-69), en
`ElevenLabsSynthesizer` (`agent/src/agilina_agent/infrastructure/speech_synthesizers.py`).

- **Modelo y voz:** `eleven_v4_turbo` (`AGILINA_ELEVENLABS_MODEL`; `eleven_flash_v2_5` es la
  alternativa si el arranque se vuelve lento), con la voz predeterminada del plugin
  (`hpp4J3VqNfWAUOO0d1Us`) mientras `AGILINA_ELEVENLABS_VOICE_ES` y `…_VOICE_EN` estén vacías. El
  plan gratuito solo permite las voces predeterminadas: las de la *Voice Library* fallan con
  `paid_plan_required`.
- **Idioma:** antes de cada frase se fijan la voz y el código del idioma del equipo (`es`, `en`),
  que obliga al modelo a pronunciar y normalizar en ese idioma. El idioma sale del contexto, que se
  pide una vez por sala: si el equipo cambia de idioma, la siguiente ceremonia ya habla en el nuevo.
- **Latencia (criterio: menos de 2 s):** se mide desde que el agente decide la frase hasta que la
  sesión pasa a `speaking`, es decir, hasta que el primer audio está en la pista de la sala. Queda en
  el log como `ElevenLabs started speaking in N ms in room … (es)`, en `WARNING` si pasa de 2 s. El
  tiempo hasta el primer audio de ElevenLabs (TTFB, ≈ 0,5 s en el spike HU-01) va en la línea de
  consumo. Lo que tarda el audio en llegar a cada navegador depende de su red y no se mide aquí.
- **Cuando la voz no suena:** la sesión no reintenta (`max_retry=0`, conexión de 5 s). Si en
  **5 s** no hay audio, la frase se corta (con `interrupt(force=True)`, porque las interrupciones
  están apagadas por AD-32) y se muestra por escrito (§6). La sala sigue en todos los casos:

  | Respuesta de ElevenLabs | Motivo en el log | Nivel | En la sala |
  | --- | --- | --- | --- |
  | Audio en flujo | `started speaking in N ms` | INFO (WARNING si > 2 s) | Se oye |
  | 401, llave inválida | `rejected the API key` | ERROR | La frase por escrito |
  | 429, o `quota_exceeded` / `too_many_concurrent_requests` en el WebSocket | `quota or rate limit … after N characters (≈ C credits)` | WARNING | La frase por escrito |
  | 5xx, otro código u otro error (`paid_plan_required`) | `did not speak … (provider_error)` | WARNING | La frase por escrito |
  | Sin audio en 5 s | `did not speak … (timeout)` | WARNING | La frase por escrito |

  Después de cuatro fallos seguidos `AgentSession` se cierra sola; la siguiente frase abre otra, así
  que si el servicio vuelve, Agilina vuelve a hablar y el texto escrito desaparece.
- **Consumo:** `eleven_v4_turbo` y `eleven_flash_v2_5` cobran **0,5 créditos por carácter**. Cada
  frase deja `ElevenLabs spoke N characters (≈ C credits), first audio from ElevenLabs in N ms`, y
  al cerrar la sala, `ElevenLabs used N characters (≈ C credits) in room …`. Para ver lo gastado:
  `make logs s=agent | grep "ElevenLabs used"`. El saldo del mes se ve en la cuenta de ElevenLabs
  (*Subscription* o *Usage*).
- **Cupo (confirmado el 2026-10-28, AGI-155):** el plan gratuito trae **10.000 créditos al mes por
  cuenta**. Angélica y Diego tienen cada uno su cuenta y su llave. Con ≈ 160 créditos por daily de 6
  personas (estimación U6 del spike: ≈ 315 caracteres), caben **≈ 62 dailies al mes por cuenta**;
  una daily por día hábil (≈ 22 al mes) usa ≈ 3.520 créditos, el 35 % del cupo. Si el cupo se agota,
  Agilina sigue en la sala y sus frases salen por escrito hasta que se renueve.
- **La llave:** solo en el `.env` de cada desarrollador (`AGILINA_ELEVENLABS_API_KEY`), que git
  ignora. El worker la lee como `SecretStr`: no aparece en logs ni en `repr`. Se crea en
  elevenlabs.io → *Developers* → *API Keys*; si la cuenta lo permite, conviene restringirla a *Text
  to Speech* y ponerle un límite de créditos.
