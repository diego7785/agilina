# Cómo se trabaja en este repositorio

Las reglas de esta página están tomadas para un equipo de dos personas que
trabaja fuera de su horario laboral, en iteraciones de tres semanas. Cada una
existe por una razón concreta de ese contexto, no por convención heredada. Son
las mismas que registra la sección 7 del documento de Avance 1.

## Estrategia de ramas: GitHub Flow

Una sola rama de larga vida, `main`, siempre desplegable. Todo el trabajo sale
de `main` en ramas cortas y vuelve a `main` por pull request.

No se usa GitFlow porque resuelve el problema de mantener varias versiones en
producción a la vez; Agilina tiene una sola versión viva y dos desarrolladores.
Tampoco trunk based puro, porque integrar directo sobre `main` dejaría sin
lugar el code review cruzado que exige el Definition of Done.

- **`main` protegida.** Nadie integra directo. Toda entrada pasa por pull
  request con la verificación automática en verde y la aprobación del otro.
- **Ramas cortas.** Una rama por historia o por grupo coherente de tareas, con
  vida máxima de una iteración. Si una rama sobrevive a un sprint, la historia
  estaba mal dimensionada y se divide.
- **Nombre.** `tipo/AGI-nnn-descripcion-corta`, en minúsculas y con guiones. El
  identificador de la historia es obligatorio: es lo que permite rastrear el
  código hasta el backlog.
- **Tipos.** `feat` funcionalidad nueva · `fix` corrección · `chore`
  infraestructura o mantenimiento · `docs` documentación · `spike` prueba
  técnica desechable.
- **Ramas de spike.** No se integran a `main`. Producen un informe, no código, y
  se conservan para consulta.
- **Borrado y actualización.** La rama se borra al integrarse. Antes de pedir
  revisión se pone al día con `main`: resolver conflictos es trabajo de quien
  abre el pull request, no de quien revisa.

```bash
git switch main && git pull
git switch -c feat/AGI-13-token-de-sala
```

## Commits: Conventional Commits

```
tipo(ambito): descripcion en imperativo

Cuerpo opcional que explica el porqué, no el qué.

Refs: AGI-nnn
```

- **Tipo.** `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `build`
  o `ci`. Obligatorio.
- **Ámbito.** `api`, `agent`, `stt`, `web`, `infra`, `docs` o `shared`.
  Identifica el desplegable o la capa tocada. Obligatorio salvo en cambios
  transversales.
- **Descripción.** En imperativo y en minúscula.
- **Cuerpo.** Opcional. Explica el porqué, no el qué, que ya está en el diff. Es
  obligatorio cuando el cambio no es evidente o descarta una alternativa.
- **Referencia.** Todo commit lleva al final `Refs: AGI-nnn`. Los commits de
  gestión de configuración del Sprint 0 usan `Refs: Sprint-0`.
- **Cambio de ruptura.** `BREAKING CHANGE` en el pie cuando rompe un contrato
  entre desplegables, en particular el contrato entre el worker y la API.
- **Idioma.** Español, igual que el resto de la documentación del proyecto.

El pipeline valida asunto y pie en cada pull request. El gancho de `pre-commit`
(`make hooks`) valida el asunto al hacer el commit; el pie lo revisas antes de
empujar con:

```bash
./.github/scripts/validar-commits.sh origin/main HEAD
```

## Pull requests

Un pull request por historia, o por un grupo de tareas que tenga sentido
revisar junto: uno que mezcla dos historias no se puede aceptar a medias.

El título usa el mismo formato que el commit más el identificador de la
historia. La descripción dice qué hace, qué historia cierra, cómo probarlo paso
a paso y qué quedó fuera a propósito. El apartado de cómo probarlo no es
opcional: sin él, revisar obliga a adivinar.

Un pull request con la compilación o las pruebas en rojo no se revisa. El
trabajo en curso se sube como borrador. Se integra con squash, usando el
mensaje del pull request como commit final.

Antes de pedir revisión, `make verify` en verde y el checklist de la
plantilla completo.

## Code review

La revisión es cruzada, nunca autorrevisión: siendo dos, la hace siempre el
otro desarrollador.

Se revisa que los criterios de aceptación estén cubiertos, que la lógica nueva
tenga pruebas, que no haya credenciales, que los errores estén manejados y
registrados, que los textos existan en ambos idiomas y que la documentación
acompañe al cambio.

No se revisa formato ni estilo: de eso se encarga el análisis estático.

Cada comentario se marca como **bloqueante**, **sugerencia** o **detalle
menor**; sin esa distinción el autor no sabe qué debe atender, que es la causa
más común de fricción en revisiones entre dos. Se aprueba cuando no quedan
comentarios bloqueantes. Si no hay acuerdo, decide quien ejerce el rol dueño de
esa parte y la decisión queda registrada.

## Definition of Done

Una historia está terminada cuando:

- el código está integrado a `main` mediante un pull request revisado y
  aprobado por el otro desarrollador;
- todos sus criterios de aceptación están verificados y son demostrables;
- la lógica nueva tiene pruebas automatizadas y el pipeline está en verde;
- no hay errores de análisis estático ni advertencias nuevas;
- ninguna credencial quedó en el repositorio;
- la documentación técnica y el documento de flujos quedaron actualizados si la
  historia cambió la arquitectura, un contrato o el comportamiento de Agilina;
- cada endpoint nuevo, o cada respuesta nueva de uno existente, está en
  [docs/api.md](docs/api.md) con todas sus respuestas;
- está desplegada y verificada en el entorno vigente;
- funciona en español y en inglés si produce texto o voz dirigida al usuario;
- se puede demostrar de principio a fin sin pasos manuales ocultos.

## Convenciones de código

La guía completa está en [docs/code-conventions.md](docs/code-conventions.md), la
estructura de carpetas y capas en
[docs/estructura-del-proyecto.md](docs/estructura-del-proyecto.md) y el
vocabulario del dominio en [docs/glossary.md](docs/glossary.md). Lo esencial:

- **Idioma.** El código va en inglés: identificadores, comentarios, variables de
  entorno y objetivos de `make`. Commits, pull requests y documentación van en
  español. Los textos de usuario van en español e inglés mediante i18n.
- **Python.** `ruff` decide formato y reglas, `mypy` en modo estricto el tipado
  e `import-linter` las reglas de arquitectura (capas y fronteras entre
  contextos); la configuración está en el `pyproject.toml` de la raíz.
- **TypeScript y Angular.** Prettier para el formato y `eslint` con
  `angular-eslint` para el resto. Angular 22 zoneless, señales y prefijo de
  selectores `agl`. La guía completa está en [web/README.md](web/README.md).
- **Textos de usuario.** Nunca en el código: en `shared/src/agilina_shared/i18n.py`
  para lo que Agilina dice, y en `web/public/i18n/*.json` para la interfaz.
  Hay una prueba que falla si una clave existe en un idioma y no en el otro.
- **Dependencias.** Cuando cambias `pyproject.toml` o `web/package.json`, ejecuta
  `make lock` y commitea `uv.lock` y `web/package-lock.json`. Los locks fijan la
  versión exacta de cada librería: las imágenes y la CI los exigen y fallan si
  no coinciden con el manifiesto.
- **Configuración.** Siempre por variables de entorno, con su clave declarada en
  `.env.example`. Ningún valor real entra al repositorio.
