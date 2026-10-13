<!--
Título del PR: mismo formato que el commit.
    tipo(ambito): descripcion en imperativo (AGI-nnn)
Un pull request por historia. Uno que mezcla dos historias no se puede aceptar
a medias. El trabajo en curso se sube como borrador.
-->

## Qué hace

<!-- Una o dos frases. El detalle está en el diff. -->

## Qué historia cierra

Refs: AGI-

## Cómo probarlo paso a paso

<!--
Este apartado no es opcional: sin él, revisar obliga a adivinar.
1.
2.
3.
-->

## Qué quedó fuera a propósito

<!-- Lo que alguien podría esperar aquí y no está, con su razón. -->

---

### Checklist del autor

- [ ] Los criterios de aceptación de la historia están cubiertos.
- [ ] La lógica nueva tiene pruebas automatizadas.
- [ ] `make verify` pasa en local.
- [ ] Ninguna credencial quedó en el código ni en la configuración versionada.
- [ ] Los textos dirigidos al usuario existen en español y en inglés.
- [ ] La documentación técnica quedó actualizada si cambió la arquitectura o un contrato.
- [ ] `docs/api.md` lista cada endpoint nuevo o cambiado con todas sus respuestas.
- [ ] La rama está al día con `main` y sin conflictos.

### Para quien revisa

Marca cada comentario como **bloqueante**, **sugerencia** o **detalle menor**.
No revises formato ni estilo: de eso se encarga el análisis estático.
