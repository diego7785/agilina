# AD-28: iniciar sesión con Keycloak desde su página, validar el token en la API

- **Estado:** propuesta (pasa a aceptada al integrarse este PR); en lo del realm único, supersedida por [AD-29](0029-un-tenant-es-una-organizacion-con-su-base-y-su-realm.md)
- **Fecha:** 2026-10-06
- **Deciden:** Diego, Angélica
- **Historia:** HU-03

## Contexto

HU-02 deja cuentas creadas en Keycloak y HU-05 dejó rutas de la API que ya piden un usuario
(`current_user_id`, `current_team_member`) detrás de un puerto, `AuthenticatedUsers`, con un
adaptador cerrado que rechazaba todo. Faltaba iniciar sesión, validar el token y que la web
lo use. Los hechos que pesaron:

- El token que Keycloak firma lleva como emisor la **URL pública** del realm. El navegador lo
  alcanza en `localhost:8080` y la API, dentro de Compose, en `keycloak:8080`: sin fijar el
  emisor, todo token sería rechazado.
- El cliente `agilina-web` es público y el realm ya exige PKCE (S256).
- Las contraseñas no deben pasar por la web ni por la API, y el mensaje de un login fallido no
  debe revelar si el correo existe (HU-03, criterio 2).
- La guía de la web dejaba abiertas la librería de Keycloak y la herramienta de pruebas de
  punta a punta «para cuando exista el inicio de sesión».

## Decisión

- **El formulario de login es la página de Keycloak**, con un tema propio (`agilina`) que
  reproduce el mockup. Flujo *authorization code* con PKCE. La contraseña solo la ve Keycloak,
  que ya trae el mensaje genérico, la protección contra fuerza bruta y los idiomas.
- **El tema se escribe con Tailwind y los mismos tokens que la web** (`web/src/tokens.css`,
  AD-27) y se compila al construir una **imagen propia de Keycloak**
  (`infra/docker/keycloak.Dockerfile`): no se versiona CSS generado y la misma imagen sirve
  para la nube. Los textos van en `messages_es/en.properties` del tema.
- **Realm versionado:** un *mapper* de audiencia hace que el token de acceso diga
  `aud: agilina-api`; protección contra fuerza bruta; idiomas es/en; la recuperación de
  contraseña **apagada** hasta que una historia la pida. `KC_HOSTNAME` fija el emisor a la URL
  pública, con `KC_HOSTNAME_BACKCHANNEL_DYNAMIC` para que la API siga leyendo las llaves por la
  red interna.
- **La API valida el token con `PyJWT`** (`KeycloakAccessTokenVerifier`): solo RS256, llaves del
  realm (JWKS) leídas una vez y re-leídas como mucho cada 30 s ante un `kid` desconocido,
  emisor, audiencia, `typ: Bearer`, y vigencia con un margen de 30 s **usando el puerto
  `Clock`**. Un token malo es una respuesta (`None` → 401), nunca una excepción, y el token
  nunca se escribe en los registros. El `sub` se resuelve al `app_user` activo
  (`KeycloakAuthenticatedUsers`); los roles no se leen del token.
- **La web usa `keycloak-js` directo**, detrás de un puerto (`AuthSession`) en `core/auth`. La
  sesión se comprueba **cuando algo la pide** (un *guard* o el interceptor), no al arrancar: las
  pantallas públicas (`/activate`, `/status`) nunca llevan a nadie a iniciar sesión. El token
  vive solo en memoria. El interceptor envía el token **solo a la API** y, ante un 401, lleva a
  iniciar sesión y de vuelta a la página. Las rutas de equipos tienen *guard*; `/` es la
  entrada del producto.
- **Pruebas de punta a punta con Playwright** en su propio contenedor (`make test-e2e`), con un
  solo recorrido: invitar → activar → iniciar sesión → equipo → volver a la página pedida.

## Alternativas descartadas

- **Formulario de login dentro de Angular**, enviando la contraseña a Keycloak (*Resource Owner
  Password Grant*): se ve igual al mockup, pero OAuth 2.1 lo elimina por inseguro, obliga a
  habilitar *direct access grants* y pierde la sesión única.
- **`keycloak-angular`:** una dependencia más, atada a la versión de Angular, y su interceptor no
  encaja con el `Logger` ni con la regla de adaptadores en `core`/`infrastructure`.
- **`joserfc`/`authlib` o `python-keycloak`** en la API: más de lo que hace falta para validar
  un JWT.
- **`check-sso` silencioso con un iframe al arrancar:** necesita una página extra, un
  encabezado distinto en nginx y cookies de terceros, que algunos navegadores bloquean. Pedir la
  sesión cuando hace falta evita las tres cosas.
- **Solo CSS sobre el tema por defecto de Keycloak** o **Keycloakify:** el primero no permite la
  marca ni el pie del mockup; el segundo suma una cadena de compilación de React por una pantalla.

## Consecuencias

- Cambiar el realm exige `make keycloak-reset`, que **borra los usuarios de Keycloak de
  desarrollo** (las cuentas activadas antes quedan sin Keycloak: se vuelve a invitar). Cambiar
  el tema es `make keycloak-theme`.
- Keycloak se construye en lugar de descargarse tal cual: `make up` tarda más la primera vez.
- Cada recarga de una página protegida pasa por Keycloak (dos redirecciones rápidas). Es el
  precio de no usar el iframe.
- Los tokens de la cuenta de servicio del worker (HU-55) no son tokens de usuario y hoy se
  rechazan por su audiencia; el mismo validador, con otra audiencia, los aceptará.
- Cerrar sesión, la expiración por inactividad y la renovación continua son HU-09.
- Las pruebas de punta a punta corren en local (red del anfitrión, Linux); la CI aún no levanta
  el entorno completo.

## Cómo se verifica

`make verify` (con la API al 100 % de cobertura), `make test-keycloak` (un token real de Keycloak
pasa la validación; el de otro tipo, el de una cuenta de servicio o uno alterado no; el mensaje
de un login fallido es el mismo exista o no el correo) y `make test-e2e` (el recorrido completo
en un navegador).

## Nota posterior (AGI-64, 2026-10-15)

Se agrega sin cambiar la decisión. La consecuencia sobre los tokens del worker se cumplió de otra
forma: en lugar de un validador con otra audiencia, el cliente `agilina-worker` de cada realm recibe
el mismo *mapper* de audiencia que `agilina-web`, así que su token dice `aud: agilina-api` y lo valida
el mismo `KeycloakAccessTokenVerifier` del tenant. Lo distingue de una persona el `azp`
(`agilina-worker`), que lee `KeycloakAuthenticatedWorkers`; las rutas del worker responden
`403 not_a_worker` a una persona, y las de persona, `403 account_not_active` al worker.
