# Agilina

Scrum Master virtual que facilita la reunión diaria por voz: conduce la
ceremonia, cede la palabra, registra lo hablado y, al cerrar, convierte la
conversación en artefactos accionables sobre las herramientas donde el equipo
ya trabaja.

Opera en dos modos. En **modo soporte** hay un Scrum Master humano que la
supervisa y Agilina pide aprobación antes de ejecutar una acción. En **modo
autónomo** el equipo ha alcanzado la madurez para prescindir del rol y Agilina
asume la facilitación completa.

Trabajo integrador de la Maestría en Computación para el Desarrollo de
Aplicaciones Inteligentes, Universidad del Valle. Diego Bonilla y Angélica
Muñoz; asesor: Oscar Bedoya.

## Levantar el entorno

Solo necesitas Docker con Compose y `make` (más `bash`, `curl` y `openssl`, que
casi todo sistema ya trae); no se instala Python, Node ni nada más.

```bash
git clone git@github.com:diego7785/agilina.git && cd agilina
make up
```

`make up` crea el `.env` con claves locales generadas, construye las imágenes,
levanta Postgres, Keycloak, Mailpit, la API y la web, espera a que respondan y
aplica las migraciones. Después:

| Qué | Dónde |
| --- | --- |
| Aplicación web | <http://localhost:4200> |
| API y su documentación | <http://localhost:8000/docs> |
| Correo de pruebas (Mailpit) | <http://localhost:8025> |
| Base de datos (pgAdmin) | <http://localhost:5051> (credenciales: `make credentials`) |
| Keycloak | <http://localhost:8080> |

La web muestra el estado del entorno: es la comprobación de que las piezas se
hablan. La voz es opcional: `make stt` levanta la transcripción y `make agent` el
worker, que registra en LiveKit. Los logs, con `make logs s=api`.

Requisitos, qué corre dónde y qué hacer cuando algo falla:
[docs/entorno-local.md](docs/entorno-local.md).

## Probar y verificar

```bash
make test      # pruebas de los tres desplegables, el paquete común, las de integración y la web
make verify    # exactamente lo que corre el pipeline, en contenedores
```

`make verify` ejecuta formato, análisis estático, tipado estricto, reglas de
arquitectura, pruebas con cobertura, compilación de la web y sus pruebas. Si
pasa en local, el pull request no debería fallar por análisis ni por pruebas.
`make` sin argumentos lista todo lo demás.

## Estructura

```
agilina/
├── shared/    Modelos de dominio y contrato worker ↔ API (Python)
├── api/       API en FastAPI: un paquete por contexto, cada uno en cuatro capas
├── agent/     Worker de LiveKit Agents: todo lo que ocurre en la ceremonia
├── stt/       Servicio de transcripción con faster-whisper sobre GPU
├── web/       Aplicación web en Angular
├── infra/     Compose del entorno, Dockerfile de Python, realm versionado
├── docs/      Documentación técnica y decisiones arquitectónicas
└── .github/   Pipeline de verificación y plantillas
```

Un solo repositorio con tres desplegables y un paquete común. El worker vive y
muere con la ceremonia, la API es un proceso de larga vida y la transcripción
necesita GPU: por eso son tres procesos y no uno. Comparten repositorio para
que el contrato entre ellos sea código compartido y no documentación que se
desactualiza.

## Stack

| Pieza | Tecnología |
| --- | --- |
| Aplicación web | Angular con `livekit-client` |
| API | Python con FastAPI |
| Worker del agente | Python con LiveKit Agents |
| Transporte de audio | LiveKit |
| Reconocimiento de voz | faster-whisper autohospedado sobre GPU |
| Razonamiento | Gemini Flash |
| Síntesis de voz | ElevenLabs |
| Persistencia | PostgreSQL con SQLAlchemy y Alembic |
| Identidad | Keycloak autohospedado |
| Trabajo en segundo plano | Planificador con almacén en la base de datos |
| Integraciones | Slack, Jira y Microsoft Graph |

La justificación de cada elección está en el documento de arquitectura. Todos
los proveedores externos quedan detrás de puertos intercambiables: cambiar de
transcripción, de modelo de lenguaje o de síntesis es sustituir un adaptador.

## Configuración

Todo se lee de variables de entorno. `.env.example` declara las claves
esperadas sin ningún valor real; `make env` lo copia a `.env`, que nunca se
versiona. Ninguna credencial vive en el repositorio: es parte del Definition of
Done del equipo, no el criterio de una sola historia.

## Cómo se trabaja

Ramas, commits, pull requests y code review: [CONTRIBUTING.md](CONTRIBUTING.md).
Configuración del repositorio y protección de `main`: [docs/github.md](docs/github.md).

Cada release se etiqueta al cerrarse: `v1.0` para la primera versión local
(Release 1), `v2.0` para la primera versión en la nube (Release 2) y `v3.0`
para la versión final validada (Release 3).

## Estado

Release 1 (v1.0), la primera versión local. Un equipo puede recibir una invitación y activar su cuenta (Keycloak, un realm por organización), gestionar equipos, roles y el sprint, ver en el dashboard el día del sprint y la próxima daily, unirse a la sala de la daily con su micrófono, ver quién está y quién habla, y ver a Agilina entrar sola, saludar por voz con el contexto del sprint y quedar en espera. Para la sala se necesitan las claves de LiveKit en el `.env` y, para que Agilina hable, la de ElevenLabs (detalles en docs/entorno-local.md).

Lo que sigue, en los Releases 2 y 3: transcripción en vivo con atribución por hablante y en dos idiomas, iniciar y facilitar la daily, resumen estructurado, integraciones con Slack, Jira y Microsoft Graph, y el despliegue en la nube.
