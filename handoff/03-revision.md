# 03 — Revisión del plan

Agente: REVISOR (etapa 3). Fecha: 2026-10-11.
Documentos leídos completos: `handoff/01-evaluacion.md`, `handoff/02-plan.md`.
Verificaciones propias (solo lectura): `[tool.ruff*]` de `pyproject.toml` (select `E,F,I,B,UP,N,S,ASYNC`,
`ignore = ["S101"]`, per-file-ignores `"tests/**" = ["S105","S106"]` y `"**/__init__.py" = ["E501"]`,
`src` sin la raíz), `.gitignore` raíz (sin choques con los nombres del plan), ausencia de `ruff` en el
equipo (`which`, caché de uv, extensiones de VS Code: no hay binario).

---

## Ronda 1

### Veredicto

cambios requeridos

El diseño es sólido y cubre todos los REQUISITOS (núcleo, adaptador con `MockProvider`, selección por
config, esbozos sin red, herramientas simuladas, `cases/`/`inputs/`/`outputs/`, registro por caso,
defensa conmutable, cero dependencias). Los cambios bloqueantes son de implementabilidad: tal como está
escrito, el plan produce importaciones circulares y una regla de rutas que choca con su propia estrategia
de pruebas, y la lista manual de reglas de ruff omite reglas que el código previsto va a disparar.

### Cambios BLOQUEANTES

1. **§2 (módulos) y §11 (orden): hay tres ciclos de importación; definir un grafo de dependencias
   acíclico.** Implementado literalmente, `python3 -m purple_team` fallaría con `ImportError` (rompe el
   requisito "correr de punta a punta con el MockProvider").
   - `cases.py` importa `Matcher` (`evaluation/matchers.py`) y `Check` (`evaluation/evaluator.py`);
     `matchers.parse_matcher` lanza `CaseFormatError` (definida en `cases.py`) y `evaluator.evaluate`
     recibe `Case` (de `cases.py`) → ciclo `cases ↔ evaluation`.
   - `recording.RunRecorder.finish_run(record: RunRecord)` usa `RunRecord` de `runner.py`, y `runner.py`
     importa `RunRecorder` → ciclo `runner ↔ recording`.
   - `defense/base.py` define `Detection`/`BlockedAction`/`BlockReason` **y** `LayeredDefense(input_guard:
     InputGuard, output_guard: OutputGuard)`; `input_guard.py`/`output_guard.py` importan esos valores de
     `base.py` → ciclo `defense/base ↔ guards`.
   Cambio pedido: (a) mover `Check`, `CheckKind`, `Matcher`, `MatcherKind`, `parse_matcher`/`parse_check`
   y la excepción de formato a un módulo sin dependencias hacia `cases.py` (p. ej.
   `evaluation/spec.py`, con `CaseFormatError` en él o en un `purple_team/errors.py`); (b) mover
   `CaseRecord`/`RunRecord` a `recording.py` (o a `records.py`); (c) separar los tipos de valor de la
   defensa (`defense/models.py`) de `NoDefense`/`LayeredDefense` (`defense/layered.py` o similar), o
   mover estas dos clases a `composition.py`/un módulo propio. Añadir al plan un diagrama o lista de
   dependencias permitidas (p. ej. `config → core → providers → tools/defense → evaluation/spec → cases →
   pipeline → evaluation/evaluator → recording → runner → composition → cli`) y ajustar §11: hoy el paso 8
   (`evaluation/`) depende de `cases.py`, que se crea en el paso 9. Prohibir `if TYPE_CHECKING` como
   "solución" de ciclos de valores en tiempo de ejecución (solo vale para anotaciones).

2. **§7.2, §2.9 (`RunRecorder(relative_to=...)`), §2.1 (`HarnessConfig.to_record()`) y §10 (pruebas):
   la regla "todas las rutas en los registros son relativas a `purple_team/`" es incompatible con la
   estrategia de pruebas del propio plan.** Las pruebas usan un TOML temporal con `inputs_dir`/
   `outputs_dir` absolutos en un `TemporaryDirectory()` y `cases_dir` apuntando a los casos reales:
   ninguna base única (`purple_team/` o la carpeta del TOML) contiene a la vez casos, prompt, `inputs/` y
   `outputs/`, así que `Path.relative_to` lanzaría `ValueError` y `test_end_to_end.py` fallaría.
   Cambio pedido: especificar una función única `display_path(path, base) -> str` con regla
   determinista, por ejemplo: relativa a `base` si `path` está dentro de `base`; si no, la ruta tal como
   vino escrita en la configuración (o `os.path.relpath`), documentando que en las corridas normales
   (config por defecto) todas quedan relativas y no se filtran rutas absolutas del usuario. Indicar cuál es
   `base` (recomendado: la carpeta del archivo de config usado) y aclarar en el oráculo de determinismo
   de `test_end_to_end.py` qué campos se excluyen de la comparación.

3. **§10 (compatibilidad con ruff): la lista manual omite reglas de los grupos seleccionados que el
   código previsto va a disparar.** ruff no está instalado ni se instalará, así que esta lista es la única
   barrera antes de `make lint`/CI (`ruff check .` y `ruff format --check .` recorren `purple_team/`).
   Añadir explícitamente:
   - `B904`: todo `raise` dentro de un `except` debe llevar `from exc` (o `from None`). El plan traduce
     muchas excepciones: `json.JSONDecodeError → OutputFormatError/CaseFormatError`,
     `tomllib.TOMLDecodeError → ConfigError`, `KeyError → MockFixtureError`, valores de enum inválidos →
     `ConfigError`.
   - `B905`: `zip(...)` siempre con `strict=`.
   - `B017`: en pruebas, nunca `assertRaises(Exception)`; usar la excepción concreta.
   - `B007`/`F841`/`F401`: sin variables de bucle, locales ni imports sin usar (los `__init__.py` no
     reexportan nada).
   - `UP040`/`UP046`/`UP047` (py312): si hace falta un alias o un genérico, sintaxis PEP 695 (`type X =
     ...`, `class C[T]:`), no `TypeAlias`/`TypeVar`.
   - `S110`/`S112`: ningún `except ...: pass` ni `except ...: continue` desnudo (el runner registra el
     error del caso y luego continúa).
   - `E741`: sin nombres `l`, `O`, `I`.
   - `ruff format`: estilo black con "magic trailing comma" (si una llamada/literal se parte en varias
     líneas, un elemento por línea y coma final), dos líneas en blanco entre definiciones de nivel
     superior, comillas dobles también en docstrings, sin espacios finales.
   Y que el verificador corra un chequeo stdlib en su scratchpad (longitud ≤ 100, tabs, espacios finales,
   salto final, `ast` para detectar `raise` sin `from` dentro de `except` y `zip` sin `strict`), dejando
   constancia en `05-verificacion.md` de que `ruff format --check` no pudo ejecutarse.

### SUGERENCIAS (no impiden aprobar)

4. **§2.2/§2.3/§5 — temperatura duplicada.** `ModelRequest.temperature` y `OllamaSettings/CloudSettings
   .temperature` coexisten y `build_chat_payload`/`build_generate_payload` usan la de `settings`.
   Precisar que los payloads usan `request.temperature` y que `composition.py` toma la temperatura de la
   sección del proveedor activo (mock: constante `0.0`), para que haya una sola fuente.
5. **§6.4 c03 — mención esperada demasiado débil.** `summary_mentions: ["bloqueo"]` también coincide con
   el resumen comprometido ("no hay bloqueos"). Usar una mención específica del hecho real (p. ej.
   "bloqueo del despliegue") y exigir en la autoría que `benign.json` no contenga ningún
   `effect_indicator` (añadirlo a las validaciones de `load_cases`: el fixture benigno no debe disparar
   indicadores; el inyectado debe disparar al menos uno).
6. **§4.2 — redacción.** Dice que el mock "solo ve lo que le llega, igual que un modelo real", pero elige
   el guion por `request.trace.case_id` (metadato). Reformular: la *decisión* benigno/comprometido depende
   solo del contenido; el `case_id` solo selecciona el guion.
7. **§9.1 `invisible_chars` — escribir el patrón con escapes** (`"[\u200b\u200c\u200d\u2060\ufeff]"`) y
   no con los caracteres invisibles literales: el código debe ser auditable a mano.
8. **§6.4 c07 — falso positivo sin consecuencia medible.** Con el mock, el control siempre devuelve
   `benign.json`, así que el falso positivo solo aparece como contador de detecciones. Considerar que la
   línea legítima redactada origine un action item esperado (p. ej. actualizar la guía de instalación)
   para que, con un modelo real, la pérdida por redacción sí se refleje en `expected_action_items_present`;
   y documentar en el README que la redacción por línea también borra contenido legítimo de la misma
   intervención (p. ej. "Yo sigo con las pruebas de regresión" en c01).
9. **§7.1/§10 — carpeta de corrida existente.** Indicar el código de salida cuando `inputs/<run_id>` u
   `outputs/<run_id>` ya existen (`FileExistsError` → código 1 con mensaje en español, sin escribir nada),
   y lo mismo para el CSV de `compare`.
10. **§12 R4 — `.gitignore` local.** Correcto no tocar el raíz; mencionar en el README y en
    `06-resumen.md` que las corridas no aparecen en `git status` pero sí están en disco, para que el
    usuario no crea que no se generaron.

### Comprobación requisito por requisito

| Requisito | Dónde lo cubre el plan | Cumple |
| --- | --- | --- |
| Núcleo que imita el cierre: transcripción + prompt de sistema → modelo → JSON (resumen, action items con destino y contenido) | §2.2 (`CeremonyCloser.close`, `CeremonyOutput`, `ActionItem{destination,target,title,content}`), §13 prompt | sí |
| Acceso al modelo detrás de interfaz/adaptador | §2.3 `ModelProvider` (Protocol), `factory.build_provider` | sí |
| `MockProvider` que no llama a ningún servicio, determinista o desde archivos | §4 (fixtures `benign/injected.json`, regla pura sin reloj ni azar) | sí |
| Proveedor elegido por config (env o archivo); cambiar a Ollama/nube solo por config | §3 (`config.toml`, `PTH_PROVIDER`, `--provider`, precedencia), §2.3 fábrica | sí |
| Ollama/modelos no instalados; corre de punta a punta solo con mock | §0 D2/D8, §5, §10 (default `provider = "mock"`) | parcial (bloqueante 1: ciclos de importación) |
| Otros adaptadores esbozados, no se ejecutan | §5 (sin imports de red, `ProviderUnavailableError` antes de crear carpetas, código 2; prueba `ast`) | sí |
| Herramientas Jira/correo/OneDrive simuladas, solo registran | §2.4 (`ToolCallRecord`, `status = "simulated"`, sin red/archivos/procesos) | sí |
| `cases/` con id, descripción, transcripción, resultado esperado, criterio | §6.1–6.3 (`case.json` + `transcript.txt`), 8 casos §6.4 | sí |
| `inputs/` y `outputs/` separados por ejecución y caso, nombres identificables | §7 (`<run_id>/<case_id>/`, `run_id`/`case_id` dentro de cada JSON) | sí |
| Registro legible por corrida: entrada usada, salida del modelo, si la inyección tuvo efecto, si pasó | §8.1 `run_log.json` (`input`, `model_output`, `evaluation.injection_effect`, `passed`), §8.2 CSV | parcial (bloqueante 2: rutas en el registro) |
| Defensa de entrada y salida activable/desactivable por config | §2.5, §3 (`defense`, `PTH_DEFENSE`, `--defense`), §8.3 `compare` | sí |
| No instalar dependencias de modelos ni servicios externos | §0 D2, §10 (stdlib, sin `uv sync`, sin `uvx`) | sí |
| Datos sintéticos | §6.4 (personas ficticias, dominios reservados `example.com`/`example.org`, sin `.env`/`.secrets/`) | sí |
| No tocar README raíz ni archivos del monorepo | §1 notas, §12 R4, §14.4 | sí |
| Compatibilidad con ruff/CI de la raíz | §10, §12 R2/R8, §14.1 | parcial (bloqueante 3) |
| Implementable sin ambigüedades | §2, §11 | parcial (bloqueantes 1 y 2) |
| Sin commits; rama antes de la etapa 4 | §1 notas, §14.5 (lo decide el orquestador) | sí |

Comprobaciones puntuales hechas sobre la matriz §6.4 con las reglas §9.1–9.2: c01 (`override_phrase` +
`assistant_addressed`), c02 (`assistant_addressed` con "Instrucción para Agilina"), c03
(`vocative_command`), c06 (`html_comment`) y c07 (`ignoren` cubierto por `ignor[ae]n?`) se detectan; c04 y
c05 no coinciden con ninguna regla; c04 se bloquea por dominio `example.org`; las rutas y proyectos
legítimos pasan la política. Totales coherentes: off 2/8 aprobados y 6 con efecto; on 7/8 y 1 con efecto.

### Inconsistencias entre evaluación y plan

1. **Ubicación de las pruebas.** La evaluación (§5) documenta la convención de árbol espejo en
   `tests/<pieza>/...`; el plan las pone en `purple_team/tests/` con `unittest`. Desviación justificada
   (aislamiento, pytest no instalado, no interferir con `make test-python`); debe quedar registrada como
   tal en `04-implementacion.md` y en el README del banco.
2. **Reglas de ruff.** La evaluación (§5) enumera los grupos `E,F,I,B,UP,N,S,ASYNC`; el plan (§10) solo
   traslada parte de `B`/`UP` a su lista manual (ver bloqueante 3).
3. **`.gitignore`.** La evaluación (§8.5) suponía que ignorar `outputs/` exigía tocar el raíz; el plan lo
   resuelve con un `.gitignore` local (§12 R4). Coherente con la recomendación §9.9 de la evaluación; sin
   conflicto.
4. **Rama.** Ambos documentos señalan que `feat/purple-team-harness` no cumple el `HU-nn` de
   `CONTRIBUTING.md`; queda en manos del orquestador. Sin acción para el planificador.

---

## Ronda 2

Documentos releídos completos: `handoff/01-evaluacion.md`, `handoff/02-plan.md` (versión ajustada, con
§2.0, §2.11, §7.3, §10.1–§10.3, §11 de 16 pasos y §15 "Cambios por revisión (ronda 1)").

### Veredicto

aprobado

Los tres bloqueantes de la ronda 1 están resueltos. Los cambios no introducen ciclos de importación: toda
arista de §2.11 apunta a un nivel estrictamente inferior, así que el grafo es acíclico por construcción.
Lo que sigue en "Problemas nuevos" son omisiones menores del propio plan. No requieren otra ronda, pero el
implementador **debe** aplicarlas (están en "Precisiones obligatorias") y registrarlas en
`04-implementacion.md`.

### Cómo se resolvió cada punto de la ronda 1

| # | Punto | Estado | Comentario |
| --- | --- | --- | --- |
| 1 | Ciclos de importación y orden de §11 | **resuelto** | `errors.py`, `paths.py`, `clock.py` y `core/text.py` quedan sin dependencias internas; `evaluation/spec.py` no importa `cases`; `records.py` separa los valores de `runner`/`recording`; `defense/models.py` y `defense/layered.py` rompen el ciclo de la defensa. Además, la tabla de niveles de §2.11 la verifica `test_import_graph.py`, queda prohibido `TYPE_CHECKING` y §11 sigue los niveles (spec 7 → cases 8 → pipeline 9 → evaluator 10 → records/recording 11 → runner 12). Comprobé paso a paso que ningún paso usa un módulo de un paso posterior |
| 2 | Regla de rutas y prueba de determinismo | **resuelto** | §7.3 define `display_path`: relativa POSIX dentro de `base_dir` y absoluta fuera, con `resolve()` previo (tiene en cuenta `/var` → `/private/var` de macOS). Con la config por defecto todo sale relativo; con la config temporal de §10.1 no se lanza `ValueError`. La prueba de determinismo sustituye el run id literal y compara byte a byte, y queda explícito qué campos se excluyen |
| 3 | Lista manual de ruff | **resuelto** | §10.2 cubre todas las reglas pedidas y otras previsibles, más la sección de formato. §10.3 añade `test_style.py` y un chequeo independiente del verificador, que debe dejar constancia de que `ruff check`/`ruff format --check` no se ejecutaron |
| 4 | Temperatura duplicada | **resuelto** | `HarnessConfig.temperature` es la única fuente, viaja en `ModelRequest.temperature` y los payloads la leen de ahí |
| 5 | Mención débil en c03 y fixtures incoherentes | **resuelto (ampliado)** | Menciones específicas en c03 y c05; los oráculos 7 y 8 de `load_cases` garantizan que el fixture benigno no dispara indicadores y que el inyectado dispara al menos uno |
| 6 | Redacción de §4.2 | **resuelto** | — |
| 7 | `invisible_chars` con escapes | **resuelto** | — |
| 8 | Falso positivo de c07 medible | **parcial; rechazo aceptado** | c07 incluye ahora un action item esperado derivado de la línea redactada, que sí se medirá con modelos reales. Rechazar un tercer guion del mock es razonable: mantiene la regla única benigno/comprometido. Queda documentado en §6.4 y en el README |
| 9 | Código de salida si la corrida o el CSV ya existen | **resuelto** | `RunExistsError` → código 1 sin escribir nada; `compare` lo comprueba todo antes de ejecutar |
| 10 | Aviso sobre `git status` | **resuelto** | R4, README (paso 15) y `06-resumen.md` |
| — | Rechazo de `os.path.relpath` (B2) | **aceptado** | Era solo una de las opciones que ofrecí; la regla elegida es más estable y legible |

### Problemas nuevos (no bloqueantes)

1. **§2.11 tiene dos aristas que faltan respecto a lo que el propio plan pide.** Ninguna crea ciclos,
   pero `test_import_graph.py` fallaría si se implementa la tabla al pie de la letra:
   - `config` (nivel 1) solo puede importar `errors`, pero `HarnessConfig.to_record()` usa `display_path`
     (§2.1) → falta `config → paths` (nivel 0).
   - `runner` (nivel 9) registra como error de caso `MockFixtureError` y `OutputFormatError` (§2.10), pero
     su lista no incluye `providers.mock` ni `core.output_parser` → faltan `runner → providers.mock`
     (nivel 3) y `runner → core.output_parser` (nivel 2).
2. **El subcomando `compare` no tiene módulo asignado en §2.10.** `cli` no puede importar `recording`
   según §2.11. Para que no haya ambigüedad: la orquestación de las dos corridas y la escritura del CSV
   comparativo van en `composition.py` (p. ej. `run_comparison(...)`), reutilizando `recording` para
   escribir; `cli` solo la invoca.
3. **Referencia desactualizada.** §14.4 dice que el implementador crea el README "en el paso 12"; ahora
   es el paso 15.
4. **Redacción de §7.3.** "Es exactamente la que él escribió" solo vale para rutas absolutas escritas
   tal cual. Una ruta relativa que sale de `base` (`../datos`) o con enlaces simbólicos se registra
   resuelta. No cambia el comportamiento, solo la explicación del README.

### Precisiones obligatorias para el implementador (sin nueva ronda)

- Añadir a la tabla de §2.11 y a `test_import_graph.py` las aristas `config → paths`,
  `runner → providers.mock` y `runner → core.output_parser`, y registrarlo en `04-implementacion.md` como
  precisión del plan.
- Poner la lógica de `compare` en `composition.py` (o en un módulo de nivel ≤ 10) y no en `cli.py`.
- Seguir el resto del plan tal cual. Cualquier otra arista nueva en el grafo debe apuntar a un nivel
  inferior y documentarse.

### Comprobación de requisitos (cambios respecto a la ronda 1)

Las filas que en la ronda 1 eran "parcial" pasan a **sí**:

- "Corre de punta a punta solo con mock": grafo acíclico.
- "Registro por caso": regla de rutas sin `ValueError`.
- "Compatibilidad con ruff/CI": lista completa más un chequeo stdlib. Queda un riesgo residual
  documentado, porque `ruff format --check` no se puede ejecutar.
- "Implementable sin ambigüedades": salvo las precisiones menores de arriba.

El resto de filas sigue en **sí** sin cambios.

### Inconsistencias entre evaluación y plan

Sin cambios respecto a la ronda 1. La ubicación de las pruebas queda registrada como desviación
justificada (§14.6) y la cobertura de ruff está alineada con los grupos que enumera la evaluación (§14.7).
