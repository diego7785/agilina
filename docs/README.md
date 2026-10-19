# Documentación técnica

Lo que vive en el repositorio es lo que cambia con el código. Los entregables
del Sprint 0 —propuesta, arquitectura, flujos, BPMN y control de cambios— viven
en el espacio del proyecto y se enlazan desde aquí.

| Documento | Para qué |
| --- | --- |
| [estructura-del-proyecto.md](estructura-del-proyecto.md) | Qué hay en cada carpeta, cómo se organiza el código por capas y contextos, y qué reglas de arquitectura se verifican solas |
| [code-conventions.md](code-conventions.md) | Cómo se escribe el código: idioma, dominio, capas, CQRS, SOLID, errores, pruebas y Angular, y qué regla verifica cada herramienta |
| [glossary.md](glossary.md) | Lenguaje ubicuo: el nombre en inglés (código) y en español (producto) de cada concepto del dominio |
| [entorno-local.md](entorno-local.md) | Levantar el entorno completo, resolver lo que falla y saber qué corre dónde |
| [contrato-worker-api.md](contrato-worker-api.md) | Las dos operaciones que cruzan la frontera entre el worker y la API |
| [sala-y-emision-del-token.md](sala-y-emision-del-token.md) | Lo que la sala de la daily (AGI-60) espera del endpoint del token (AGI-59) y qué falta verificar con LiveKit |
| [github.md](github.md) | Configuración del repositorio: protección de `main`, revisión y etiquetas |
| [adr/](adr/) | Decisiones arquitectónicas que se toman de aquí en adelante |

La convención de ramas, commits, pull requests y code review está en
[CONTRIBUTING.md](../CONTRIBUTING.md), en la raíz, porque GitHub la muestra
automáticamente al abrir un pull request.
