# 01 — Evaluación del repositorio

Agente: EVALUADOR (etapa 1). Fecha: 2026-10-11. Documentos previos leídos: ninguno (primera etapa).
Alcance: análisis de solo lectura. Lo único creado es este archivo.

---

## 1. Estado de git al iniciar

| Aspecto | Valor |
| --- | --- |
| Rama actual | `main` (102 commits; último `914fb3c`, merge del PR #15 de HU-04) |
| Modificado sin confirmar | `.gitignore`: la línea `web/.angular/` pasó a `.angular/` (ignora cualquier `.angular/`, p. ej. la de `spike-hu01/client/`) |
| Sin seguimiento | `.claude/` (contiene `workflows/hu-delivery.js`), `.secrets/` (secretos; **no leído**), `spike-hu01/` (spike de HU-01: `client/` con build de Angular, `logs/A.txt`, `B.txt`, `C.txt`, `metrics/` y un `.env` propio, **no leído**) |
| `handoff/` | Existe y estaba vacía; git no la muestra hasta que tenga archivos |
| Ganchos de git instalados | Ninguno (`.git/hooks` solo tiene los `.sample`); `pre-commit` no corre salvo que alguien ejecute `make hooks` |

Archivos sensibles presentes y **no abiertos**: `.env` (raíz), `.secrets/`, `spike-hu01/.env`. `.env.example` sí es público (declara claves sin valores); de él solo se consultaron nombres de variables.

> **Aviso para los agentes posteriores:** el `README.md` de la raíz es el README del proyecto
> Agilina (descripción, cómo levantar el entorno, stack, estructura). **No debe sobrescribirse.**
> El README del banco de pruebas debe ir dentro de su propia carpeta (ver §9).

---

## 2. Estructura general

Monorepo con tres desplegables Python, un paquete común, una web Angular e infraestructura Docker:

```
agilina/
├── pyproject.toml   Raíz del workspace uv (no instalable, package = false) + config de ruff, pytest, coverage, mypy, import-linter
├── uv.lock          Lock único del workspace (~750 KB)
├── .python-version  3.12
├── shared/          agilina_shared: contrato worker↔API (Pydantic), enums, i18n, calendario del sprint
├── api/             agilina_api: FastAPI, contextos ceremonies/identity/teams/shared, 4 capas (≈327 .py)
├── agent/           agilina_agent: worker de LiveKit Agents (esqueleto)
├── stt/             agilina_stt: transcripción faster-whisper (modo simulado por defecto)
├── web/             Angular 22 (TypeScript)
├── tests/           Pruebas Python en árbol espejo: api/, agent/, shared/, stt/, e2e/ (Playwright)
├── infra/           docker-compose.yml, Dockerfiles, realm de Keycloak, Postgres
├── docs/            Documentación en español + ADR 0021–0031
├── .github/         ci.yml, plantilla de PR, CODEOWNERS, script de validación de commits
├── Makefile         Punto de entrada único (todo corre en contenedores)
├── CONTRIBUTING.md  GitHub Flow, Conventional Commits en español, PRs
└── README.md        README del PROYECTO Agilina (no tocar)
```

Lenguajes: **Python 3.12** (backend, agente, STT, contrato) y **TypeScript** (web). El banco de pruebas solicitado pertenece al lado Python.

---

## 3. Python, gestor de dependencias y dependencias

- `requires-python = ">=3.12"` en todos los `pyproject.toml`; `.python-version` = `3.12`; ruff `target-version = "py312"`; mypy `python_version = "3.12"`.
- Gestor: **uv** con workspace (`[tool.uv.workspace] members = ["shared", "api", "agent", "stt"]`), build backend `hatchling` en cada miembro, lock único `uv.lock`. `make lock` regenera el lock en un contenedor.
- Grupo `dev` (raíz): `pytest>=8`, `pytest-asyncio`, `pytest-cov`, `ruff>=0.14,<0.15`, `mypy`, `import-linter`, `httpx`, `pre-commit`.
- Dependencias por miembro:
  - `shared`: `pydantic>=2.8`.
  - `agent`: `agilina-shared`, `livekit-agents>=1.0` (lock: 1.8.4), `httpx`, `pydantic-settings`.
  - `stt`: `fastapi`, `uvicorn`, `pydantic-settings`, `python-multipart`; extra `gpu` = `faster-whisper`.
  - `api`: FastAPI, SQLAlchemy, Alembic, etc. (no relevante aquí).

### ¿Hay algo de LLM?

| Librería | ¿Presente? | Detalle |
| --- | --- | --- |
| `ollama` | No | Ni en `pyproject` ni en `uv.lock`; binario `ollama` no instalado (`which ollama` → not found) |
| `anthropic` | No | — |
| `openai` | **Solo transitiva** | `openai 2.54.0` está en `uv.lock` como dependencia obligatoria de `livekit-agents 1.8.4`. Ningún código del repo la importa |
| `langchain*`, `litellm`, `google-genai` | No | — |
| Gemini | **Solo configuración** | `.env.example` declara `AGILINA_GEMINI_API_KEY=` (vacía) y `AGILINA_GEMINI_MODEL=gemini-2.0-flash`; el `README.md` lista «Razonamiento: Gemini Flash». No hay adaptador ni código que lo use |

Conclusión: **no existe ningún adaptador de LLM ni llamada a un modelo en el código.**

---

## 4. Organización del código relevante para el banco de pruebas

### 4.1 `agent/` (worker)

Arquitectura hexagonal en capas (verificada con import-linter, contrato «Agent: layers»: `main` → `presentation | infrastructure` → `application` → `domain`; el dominio no puede importar `livekit`, `httpx`, `fastapi`, `sqlalchemy`).

| Archivo | Qué hay |
| --- | --- |
| `agent/src/agilina_agent/application/ports.py` | Puertos como `typing.Protocol` con `@runtime_checkable`: `Transcriber`, `SpeechSynthesizer`, `AgilinaApi`. **No hay puerto de LLM** |
| `agent/src/agilina_agent/domain/facilitation.py` | `FacilitationMachine` (estados `WAITING/GREETING/TURN/CLOSED/DEGRADED`), `ActionNotAllowedError`. Lo que Agilina dice sale de plantillas, **nunca del LLM** (AD-19) |
| `agent/src/agilina_agent/infrastructure/speech_synthesizers.py` | `ElevenLabsSynthesizer` (esbozo que lanza `NotImplementedError("... pending: HU-23 ...")`) y `RecordingSynthesizer` (registra lo que diría en `self.spoken` y en el log, sin llamar a nada) |
| `agent/src/agilina_agent/infrastructure/settings.py` | `Settings(BaseSettings)` con `env_prefix="AGILINA_"`, lee `.env`; `get_settings()` con `@lru_cache` |
| `agent/src/agilina_agent/infrastructure/http_agilina_api.py` | Adaptador HTTP a la API con reintentos |
| `agent/src/agilina_agent/main.py` | Raíz de composición: elige adaptadores concretos |
| `agent/src/agilina_agent/presentation/room_job.py` | Job de LiveKit (adaptador de entrada) |

### 4.2 `stt/` (patrón de proveedor simulado elegido por configuración)

`stt/src/agilina_stt/infrastructure/transcribers.py` es el **modelo más cercano a lo que pide el REQUISITO del MockProvider**:

- `SimulatedTranscriber`: responde un texto fijo por idioma (`SIMULATED_TEXT`), determinista, y marca `simulated=True`.
- `WhisperTranscriber`: adaptador real con **importación perezosa** de `faster_whisper` dentro del `__init__`; si falta, lanza `RuntimeError` con instrucciones. Así el código corre sin la dependencia instalada.
- `build_transcriber(settings)`: fábrica que elige el adaptador según `settings.simulated` (variable `AGILINA_STT_SIMULATED`, por defecto `true`).

### 4.3 `shared/` (contrato)

`shared/src/agilina_shared/contract/`: `CeremonyResult` (lo que el worker entrega al cerrar: `ceremony_id`, `status`, `started_at`, `closed_at`, `present_participants`, `absent_participants`, `segments: list[TranscriptSegment]`, `degraded`, `degradation_detail`) y `TranscriptSegment` (`user_id`, `room_identity`, `text`, `start_ms`, `end_ms`). Base `ContractModel` con `extra="forbid", frozen=True`. Enums útiles: `Language` (`es`/`en`; su docstring dice que parametriza «las instrucciones del modelo de lenguaje» y «el idioma del resumen»), `OperationMode` (`support`/`autonomous`: la única diferencia es si Agilina pide aprobación antes de ejecutar una acción).

### 4.4 `api/`

- `api/src/agilina_api/ceremonies/presentation/http/router.py`: `GET /v1/ceremonies/{id}/context` y `POST /v1/ceremonies/{id}/result` responden 501 (pendiente HU-56).
- Correo real: puerto `Mailer` (`api/src/agilina_api/shared/application/ports/mailer.py`), `EmailMessage`, `MailDeliveryError`; adaptador `SmtpMailer` en `api/src/agilina_api/shared/infrastructure/mail/smtp_mailer.py`. Se usa para invitaciones, **no** para action items.
- Contextos **planeados, sin código** (`docs/estructura-del-proyecto.md`): `postprocessing` («Resumen, action items, flujo de aprobación», Release 2–3) e `integrations` («adaptadores de Slack, Jira y Graph», Release 3).

### 4.5 ¿Existe ya lo que el banco de pruebas debe imitar?

| Pieza | ¿Existe? | Dónde está la referencia |
| --- | --- | --- |
| Cierre de ceremonia / post-procesamiento con LLM | **No implementado.** Solo definido | `docs/glossary.md`: «Post-processing: el razonamiento con el LLM, una sola vez al cerrar la ceremonia (AD-19)». Según AD-19 ocurre en la API (contexto `postprocessing`), no en el worker. AD-19 no está en `docs/adr/` (vive en el documento de arquitectura externo) |
| Extracción de action items | **No.** Solo glosario | `ActionItem`: «Acción derivada de la ceremonia, con su estado: propuesto, aprobado, rechazado, ejecutado o fallido. Rechazar no borra». `ApprovalRequest`: en modo soporte, mensaje de Slack con una casilla por action item. También «Blocker» e «Issue mention» (referencia a un ticket de Jira) |
| Prompt de sistema | **No** | Ninguno en el repo |
| Adaptador de LLM | **No** | Solo `AGILINA_GEMINI_*` en `.env.example` |
| Herramientas Jira / correo / OneDrive | **No** (para action items) | Integraciones previstas: Slack, Jira y Microsoft Graph (OneDrive y correo vía Graph). El único correo implementado es SMTP de invitaciones en la API |
| Entrada «transcripción» | Sí, como contrato | `TranscriptSegment` / `CeremonyResult.segments` (texto atribuido por `room_identity`) |

Por tanto, el banco de pruebas **define por primera vez** el formato de salida (resumen + action items con destino y contenido). Debería alinearse con el vocabulario del glosario (`ActionItem`, destinos Jira/correo/OneDrive, idioma `es`/`en`) sin depender del código de Agilina.

---

## 5. Convenciones

| Tema | Regla | Fuente |
| --- | --- | --- |
| Idioma | Identificadores, nombres de archivo, comentarios, docstrings, campos JSON y variables de entorno en **inglés**; commits, PRs, ADR y `docs/` en **español** | `docs/code-conventions.md` §Idioma |
| Formato/lint | ruff, `line-length = 100`, comillas dobles, reglas `E,F,I,B,UP,N,S,ASYNC` (S = bandit: p. ej. `S311` random, `S603/S607` subprocess, `S108` rutas temporales, `S105/S106` contraseñas; `S101` assert ignorado) | `pyproject.toml` `[tool.ruff]` |
| Tipado | `mypy --strict`, solo sobre `shared/src api/src agent/src stt/src` | `pyproject.toml`, `Makefile` (`PYPACKAGES`) |
| Arquitectura | import-linter sobre `agilina_api`, `agilina_agent`, `agilina_stt`, `agilina_shared` | `pyproject.toml` `[tool.importlinter]` |
| Puertos | `typing.Protocol` en `application`; la raíz de composición es el único lugar que elige el adaptador concreto | `docs/code-conventions.md`, `agent/.../ports.py` |
| Clases | Una clase por archivo en `api/src` y `shared/src` (hay una prueba que lo exige); no aplica a `agent/` ni a carpetas nuevas | `docs/code-conventions.md` |
| Código limpio | Sin valores mágicos, sin banderas booleanas como parámetro, comentarios que explican el porqué, `TODO(HU-nn)` | `docs/code-conventions.md` |
| Configuración | Todo por variables de entorno con clave en `.env.example`; nada real en el repo; logs sin secretos | `docs/code-conventions.md`, `README.md` |
| Pruebas | Árbol espejo `tests/<pieza>/{unit,integration}/<ruta del módulo>/test_<módulo>.py`; nombres que describen comportamiento; Data Builders; reloj y aleatoriedad inyectados; sin `uuid4()`/`datetime.now()` en pruebas de la API | `docs/testing.md`, `tests/CLAUDE.md` |
| editorconfig | UTF-8, LF, salto final, 2 espacios (4 en `.py`), tabs en Makefile | `.editorconfig` |
| pre-commit | trailing-whitespace, end-of-file-fixer, check-yaml, **check-json**, check-added-large-files (1 MB), detect-private-key, ruff-check `--fix`, ruff-format, conventional-pre-commit; mypy e import-linter en pre-push | `.pre-commit-config.yaml` |
| Ramas | GitHub Flow; nombre `tipo/HU-nn-descripcion-corta` (el id de historia es obligatorio) | `CONTRIBUTING.md` |
| Commits | Conventional Commits en español, `Refs: HU-nn`; un solo autor, sin `Co-Authored-By` ni atribución | `CONTRIBUTING.md`, `tests/CLAUDE.md` |
| Guías para agentes | `api/CLAUDE.md`, `tests/CLAUDE.md`, `web/CLAUDE.md` | — |

---

## 6. Cómo se corren las pruebas y la verificación

- Oficial: **todo en contenedores** vía `make` (Docker 27.3.1 está instalado):
  - `make test-python` → `pytest` en el contenedor `tools`.
  - `make lint` → `ruff check .` (sobre **toda la raíz**) + lint de la web.
  - `make verify` → `ruff format --check . && ruff check . && mypy $(PYPACKAGES) && lint-imports`, cobertura, build y pruebas de la web.
- CI (`.github/workflows/ci.yml`): `uv sync --locked --all-packages --all-groups`, `uv run ruff format --check .`, `uv run ruff check .`, mypy, lint-imports, pytest con cobertura (100 % en `api/src` y `shared/src`).
- Configuración de pytest en la raíz: `testpaths = ["tests"]`, `pythonpath = [".", "shared/src", ...]`, `asyncio_mode = "auto"`, `addopts = "-q --strict-markers --import-mode=importlib -m 'not integration and not keycloak'"`, marcadores `integration` y `keycloak`.

---

## 7. Herramientas disponibles localmente (verificado, nada instalado)

| Comando | Resultado |
| --- | --- |
| `which python3` | `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3` |
| `python3 --version` | `Python 3.12.4` |
| `which uv` | `/Users/diegobonilla/.local/bin/uv` |
| `uv --version` | `uv 0.11.6 (65950801c 2026-04-09 aarch64-apple-darwin)` |
| `which ollama` | no encontrado |
| `.venv` del proyecto | **no existe** (nunca se ejecutó `uv sync` en local) |
| Módulos en el Python global | `tomllib` sí (stdlib); `pydantic`, `pytest`, `ruff` **no**; `yaml` (PyYAML) sí, pero no es stdlib |

Implicación: con lo que hay instalado, el banco de pruebas solo corre sin instalar nada si usa **la librería estándar de Python 3.12** (`json`, `dataclasses`, `typing.Protocol`, `pathlib`, `argparse`, `tomllib`, `os`, `datetime`, `hashlib`, `re`, `csv`, `unittest`, `logging`). Ejecutar `uv sync` crearía `.venv` e instalaría todo el workspace (incluido `livekit-agents` y, transitivamente, `openai`), lo que contradice «no instalar dependencias de modelos ni servicios externos».

---

## 8. Riesgos e inconsistencias detectadas

1. **`ruff check .` y `ruff format --check .` recorren toda la raíz.** Cualquier `.py` nuevo fuera de las carpetas excluidas lo revisarán `make lint`, `make verify` y la CI. El código del banco debe cumplir la config de ruff (incl. bandit `S`) o excluirse explícitamente (`extend-exclude` en `pyproject.toml`), lo que sería tocar la config compartida.
2. **pytest de la raíz** solo busca en `tests/`; si las pruebas del banco van en su carpeta, `make test-python` no las ejecuta (bueno para no interferir), pero `pytest` no está instalado localmente. `unittest` (stdlib) evita ambos problemas.
3. **Nombre de rama sugerido** (`feat/purple-team-harness`) no lleva `HU-nn`, que `CONTRIBUTING.md` declara obligatorio. Como no habrá commits ni PR, es menor; lo decide el orquestador.
4. **Idioma:** el prompt del usuario está en español; la convención del repo exige código en inglés y documentación en español. Las transcripciones sintéticas de los casos pueden ir en español (el producto es bilingüe `es`/`en`).
5. **`.gitignore`** ignora `build/`, `dist/`, `*.bin`, `*.wav`, `modelos/`, `.env*`: evitar esos nombres para carpetas del banco que sí se quieran versionar. Hoy no ignora `outputs/` ni `inputs/`: si los registros de ejecución no deben versionarse, habrá que decidirlo (y eso modificaría `.gitignore`, que ya tiene un cambio local sin confirmar del usuario).
6. **pre-commit `check-json`** validará los `.json` del banco si algún día se instala; deben ser JSON válido (sin comentarios).
7. **Docker:** `infra/docker/python.Dockerfile` solo copia `pyproject.toml`, `uv.lock`, los `pyproject.toml` de los miembros, `shared/` y `api/`; una carpeta nueva en la raíz no entra a las imágenes. `.dockerignore` no la excluye del contexto de build (impacto mínimo).
8. **REQUISITOS vs. repo:** los REQUISITOS piden carpetas `cases/`, `inputs/`, `outputs/`; si se crean en la raíz se mezclarían con el monorepo. Ver recomendación de ubicación.
9. El orquestador pide al documentador escribir `README.md`: **debe ser el README de la carpeta del banco, no el de la raíz** (ver §1).

---

## 9. Recomendaciones para el planificador

1. **Ubicación aislada:** crear una única carpeta de primer nivel, por ejemplo `purple_team/` (o `purple-team-harness/`), que contenga todo: paquete Python, `cases/`, `inputs/`, `outputs/`, configuración, pruebas y su propio `README.md`. No agregarla a `[tool.uv.workspace].members`, no modificar `uv.lock`, ni los `pyproject.toml` existentes, ni `agent/`, `shared/`, `api/`, `tests/`. No usar el prefijo `agilina_` para el paquete (evita que import-linter, mypy, isort `known-first-party` o la cobertura lo traten como parte del producto).
2. **Solo librería estándar** de Python 3.12: es viable y es la única opción que corre hoy sin instalar nada. Config por variable de entorno (con un prefijo propio, p. ej. `PTH_PROVIDER=mock`, distinto de `AGILINA_` para no mezclarse con el `.env` del proyecto) y/o archivo de config en JSON o TOML (`tomllib`). Validación de la salida JSON a mano (sin Pydantic). Pruebas con `unittest` y ejecución con `python3 -m ...` desde la carpeta del banco.
3. **Reutilizar los patrones, no el código**, de Agilina:
   - Puerto como `typing.Protocol` con `@runtime_checkable` (`agent/src/agilina_agent/application/ports.py`) → p. ej. `ModelProvider`.
   - Fábrica que elige el adaptador por configuración (`build_transcriber(settings)` en `stt/src/agilina_stt/infrastructure/transcribers.py`) → `build_provider(config)`.
   - Proveedor simulado determinista (`SimulatedTranscriber`) → `MockProvider`.
   - Adaptador real con importación perezosa y error claro si falta la dependencia (`WhisperTranscriber`) o esbozo con `NotImplementedError` (`ElevenLabsSynthesizer`) → `OllamaProvider` y proveedor de nube (Gemini es el previsto por el proyecto: `AGILINA_GEMINI_MODEL=gemini-2.0-flash`). Para que «no se ejecuten», no deben importar nada al cargar el módulo.
   - Doble que registra en vez de actuar (`RecordingSynthesizer`) → herramientas simuladas Jira / correo / OneDrive que solo registran la acción solicitada.
   - Raíz de composición única (como `agent/.../main.py`) que lee la config y cablea proveedor, defensa y herramientas.
4. **Vocabulario:** usar los términos del glosario (`ActionItem`, «resumen», destinos Jira / correo / OneDrive, `Language` `es`/`en`). El formato de transcripción puede imitar `TranscriptSegment` (líneas atribuidas a un hablante), pero en texto plano y sin importar `agilina_shared`.
5. **Cumplir ruff de la raíz** (líneas ≤ 100, comillas dobles, isort, sin `random` no criptográfico, sin `subprocess`, sin rutas en `/tmp` codificadas, sin `eval`), tipado completo al estilo `mypy --strict` aunque mypy no lo revise, código y comentarios en inglés, documentación (`handoff/`, README del banco) en español.
6. **Determinismo:** identificadores de corrida inyectables o derivados de un reloj/argumento (p. ej. `--run-id`), para que las pruebas no dependan de la hora; el `MockProvider` debe responder igual cada vez (desde archivos por caso o reglas fijas), incluido un comportamiento que simule el efecto de la instrucción inyectada para que el registro tenga casos «con efecto» y «sin efecto».
7. **Datos sintéticos únicamente:** nada de `.env`, `.secrets/` ni datos reales; ninguna llamada de red en ningún camino ejecutable.
8. **Qué evitar:** `uv sync`/`uv add`, instalar `ollama`, `openai`, `anthropic`, `langchain` o similares; tocar `README.md` raíz, `.gitignore` (tiene un cambio del usuario sin confirmar), `pyproject.toml`, `uv.lock`, `Makefile`, `.claude/`, `spike-hu01/`; hacer commits.
9. **Registros:** JSON con `ensure_ascii=False` e indentación (legibles a mano y válidos para `check-json`); opcionalmente un CSV resumen por corrida. Decidir explícitamente si `outputs/` se versiona; si no, documentarlo en el README del banco en lugar de tocar el `.gitignore` raíz (o usar un `.gitignore` local dentro de la carpeta del banco).
