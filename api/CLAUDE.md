## Para agentes que trabajan en api/

Esta carpeta es la API (FastAPI): el código vive en `src/agilina_api/`, las migraciones en
`migrations/` y las pruebas en [`tests/api/`](../tests/CLAUDE.md), fuera de aquí.

- Las guías mandan, en este orden: [code-conventions.md](../docs/code-conventions.md),
  [estructura-del-proyecto.md](../docs/estructura-del-proyecto.md) y los ADR
  ([AD-21](../docs/adr/0021-organizar-el-codigo-en-contextos-y-capas.md) a
  [AD-25](../docs/adr/0025-organizar-las-pruebas-con-arbol-espejo-builders-y-cobertura-total.md)).
  Si algo no está decidido ahí, **pregunta antes de decidir**: no se inventan librerías,
  capas ni convenciones. Una decisión que cambia la forma del sistema se registra como ADR.
- **Una clase por archivo**, con el nombre de la clase en `snake_case` (`invalid_email_error.py`);
  un tema con varias clases es un paquete (`errors/`) que las reexporta en su `__init__.py`. Un
  comando y su manejador son dos archivos. Una prueba lo verifica; la regla completa está en
  [code-conventions.md](../docs/code-conventions.md).
- Código, comentarios, nombres de archivo y mensajes de error en inglés. Commits, pull
  requests, documentación y ADR en español.
- Todo corre en contenedores; no se instala Python, uv ni nada en la máquina. Usa `make`:
  `lint`, `format`, `typecheck`, `arch`, `test-python`, `test-integration`, `coverage` y
  `verify`. Antes de dar algo por terminado: `make verify` en verde.
- Commits: un solo autor, sin `Co-Authored-By` ni líneas de atribución. Nada de commits ni
  push sin autorización explícita de quien lo pide, cada vez. Una rama por historia
  (`tipo/AGI-nnn-descripcion`).

## Dónde va cada cosa

```
src/agilina_api/
├── bootstrap/        Raíz de composición: aquí, y solo aquí, se elige qué adaptador atiende cada puerto
├── shared_kernel/    Entity, AggregateRoot, DomainEvent, DomainError
├── shared/           Lo común a los contextos, por capas (puertos Clock, Mailer, UnitOfWork…)
└── <contexto>/       identity, teams, ceremonies
    ├── domain/         Agregados, objetos de valor, eventos, errores, repositorios (interfaces)
    ├── application/    Comandos y consultas, puertos de salida, DTO
    ├── presentation/   Routers HTTP, esquemas, presentadores, dependencias
    └── infrastructure/ Persistencia, Keycloak, correo, mapeadores
```

Las capas apuntan hacia adentro: `presentation` e `infrastructure` → `application` →
`domain`. `make arch` (import-linter) lo verifica y falla si se rompe.

## Reglas de arquitectura

- **El dominio es Python puro:** sin FastAPI, SQLAlchemy, Pydantic ni httpx. Los invariantes
  viven en los agregados y se prueban sin servidores.
- **Un contexto no importa a otro.** Se hablan por puertos que el contexto que los necesita
  declara en su `application` y que `bootstrap/` implementa (`TeamsBackedMembership`,
  `TeamsBackedContacts`). Los contextos nunca se conocen entre sí.
- **El ORM no es el dominio.** Los modelos SQLAlchemy viven en `infrastructure` y se
  convierten con mapeadores; el dominio no sabe que existe una base de datos.
- **CQRS pragmático:** una sola base de datos, sin *event sourcing* ni bus. Los comandos pasan
  por el agregado y el repositorio; las consultas de lectura usan SQL directo y devuelven
  DTO.
- **Una unidad de trabajo por caso de uso.** El caso de uso abre la transacción y hace el
  `commit`; un manejador que se usa dentro de la transacción de otro (`AddTeamMember`) no
  hace `commit`.
- **Los casos de uso no conocen HTTP ni SQL.** Reciben comandos y devuelven DTO; los errores
  de negocio son `DomainError` y es `presentation` quien los convierte en estado HTTP y
  código estable.
- **Tiempo y azar se inyectan:** el instante sale del puerto `Clock` (siempre en UTC) y los
  identificadores se generan en el caso de uso, nunca dentro del dominio.
- **Multi-tenant en dos niveles ([AD-29](../docs/adr/0029-un-tenant-es-una-organizacion-con-su-base-y-su-realm.md)):**
  el **tenant** es la organización, con su propia base de datos y su propio realm, y se elige en el
  borde (`X-Agilina-Tenant`, `current_tenant`); dentro, el **equipo** aísla los datos y toda consulta
  de un equipo filtra por él. Un caso de uso, un repositorio o una consulta no conoce el tenant: recibe
  la sesión de su base. Todo lo que toca datos de un tenant llega por `current_container`; una ruta
  nueva no necesita más, y la prueba de inventario falla si olvida el tenant. Nada de un tenant se
  guarda en el catálogo salvo lo que `tenancy` define, y nadie usa la base de un tenant para otro.
- **La API hace la autorización.** La interfaz solo oculta lo que la API ya protege.
- **El rol interno autoriza; la etiqueta solo se muestra** ([permisos](../docs/permisos.md)). Hay dos
  roles guardados por equipo (`admin`, `member`); la etiqueta (`member`, `scrum_master`, `admin`) se
  deriva del rol y del modo con `agilina_shared.role_label`, no se guarda, y solo la leen la
  presentación y las consultas. Las rutas de personas viven en `/v1/users` y nombran el equipo en `?team_id=` (`current_team_*_by_query`). Una ruta de equipo o de usuarios nueva declara su rol mínimo en el inventario de
  `tests/api/unit/bootstrap/test_permissions.py` y en `docs/permisos.md`.

## Seguridad

- Ninguna credencial, token ni secreto en el código ni en la configuración versionada: todo
  sale de variables de entorno (`AGILINA_*`, declaradas en `.env.example`).
- Un token de invitación se guarda **solo como hash SHA-256**; viaja en el cuerpo de la
  petición, nunca en la URL de la API, y ninguna respuesta lo repite.
- Nunca se registran tokens, contraseñas ni correos completos (un adaptador usa
  `mask_email`). Un adaptador registra cada llamada a un sistema externo con su resultado, y
  un mensaje de error de un sistema externo no se devuelve al cliente.
- Las respuestas de autenticación llevan `Cache-Control: no-store`.
- **Toda ruta nueva exige un tenant y una sesión.** Declara `Depends(current_user_id)` (o
  `current_team_member` si es de un equipo): la API valida el token de Keycloak (firma, emisor,
  audiencia, vigencia) antes de confiar en él ([AD-28](../docs/adr/0028-iniciar-sesion-con-keycloak.md)).
  Una ruta pública es una excepción: se agrega a `PUBLIC` en
  `tests/api/unit/bootstrap/test_authentication.py` (`TENANT_ONLY` si necesita tenant pero no
  sesión, `NO_TENANT` si no necesita ninguno), con su razón; si no, esa prueba falla.
  Nunca se lee un rol ni un equipo del token: se consulta lo guardado.
- Todo error de la API tiene el mismo cuerpo, `{"error": {status, code, message, details?,
  request_id}}`, con `code` estable: el cliente decide por el código, no por el texto
  ([AD-30](../docs/adr/0030-un-solo-formato-de-error-http-y-un-catalogo-de-la-api.md)). Un error
  nuevo es una entrada del catálogo de su contexto (`ApiError`), emparejada con su excepción en la
  tabla del contexto o lanzada como `ApiException`; nunca un `JSONResponse` armado a mano. El
  `message` es en inglés y genérico, y `details` nunca repite un valor enviado.
- **Documenta el endpoint.** Una ruta nueva, o una respuesta nueva de una existente, entra en
  [`docs/api.md`](../docs/api.md) y declara `responses=errors_of(...)` en el mismo cambio; una
  prueba falla si no coinciden.

## Migraciones

- Hay dos entornos de Alembic: `tenant` (el esquema de cada base de tenant: identidad y equipos) y
  `platform` (el catálogo de tenants). Se escriben **a mano, en SQL**, en
  `migrations/tenant/versions/` o `migrations/platform/versions/`. El *autogenerate* de Alembic
  propone borrar columnas reales y no se usa. `make migration m="…"` crea una revisión vacía del
  esquema de los tenants y `make migration-platform m="…"` una del catálogo; `make migrate` aplica
  las del catálogo y después las de **todos** los tenants.
- **Mientras el desarrollo sea local, no se parchean: se reescribe la migración inicial** (una por
  entorno) y se reconstruye con `make clean` y `make up`. Desde el primer despliegue compartido, cada
  cambio es una migración nueva y las anteriores no se tocan.
- La prueba de migraciones comprueba que el esquema que producen y los modelos ORM
  coinciden: un cambio de esquema sin su modelo (o al revés) la rompe.

## Cómo agregar algo

**Un caso de uso nuevo en un contexto existente**

1. Si hay una regla, va en el agregado (`domain`), con su prueba pura.
2. Escribe el comando o la consulta y su manejador en `application`. Lo que necesite del
   exterior es un puerto de salida (un `Protocol`), no una clase concreta.
3. Implementa el puerto en `infrastructure` (persistencia, Keycloak, correo) y prueba el
   adaptador.
4. Expón el endpoint en `presentation/http`, con su esquema y la traducción de errores.
5. Cabléalo en `bootstrap/container.py` y en `app.py`.
6. Pruebas de cada capa y `make verify` en verde (100 % de cobertura).

**Un contexto nuevo:** crea `src/agilina_api/<contexto>/` con solo las capas que necesite,
agrégalo a los contratos de `import-linter` en el `pyproject.toml` y, si necesita algo de
otro contexto, declara el puerto y su adaptador en `bootstrap/`.

**Un texto para el usuario** (por ejemplo un correo) va en una plantilla en ES y en EN
(`shared/infrastructure/mail/`), nunca escrito en el caso de uso.

## Calidad (Definition of Done)

- `ruff`, `mypy --strict` y los contratos de arquitectura en verde.
- La lógica nueva lleva pruebas de cada capa que toca, y la cobertura de `api/src` y
  `shared/src` se mantiene en **100 %**.
- Todo texto dirigido al usuario existe en español y en inglés.
- Los errores se manejan y se registran; no se tragan en silencio.
- No se revisa formato ni estilo en el Code Review: de eso se encargan `ruff` y `mypy`.
