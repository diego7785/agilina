# Configuración del repositorio

## Protección de `main`

Nadie integra directo. En *Settings → Branches → Add rule* sobre `main`:

- Require a pull request before merging.
- Require approvals: **1** (siendo dos, es siempre el otro).
- Dismiss stale pull request approvals when new commits are pushed.
- Require review from Code Owners.
- Require status checks to pass before merging → **Verificación completa**.
- Require branches to be up to date before merging.
- Require conversation resolution before merging.
- Do not allow bypassing the above settings.

Con `gh` instalado y autenticado, lo mismo en un comando:

```bash
gh api -X PUT repos/:owner/:repo/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -F 'required_status_checks[strict]=true' \
  -f 'required_status_checks[contexts][]=Verificación completa' \
  -F 'enforce_admins=true' \
  -F 'required_pull_request_reviews[required_approving_review_count]=1' \
  -F 'required_pull_request_reviews[dismiss_stale_reviews]=true' \
  -F 'required_pull_request_reviews[require_code_owner_reviews]=true' \
  -F 'restrictions=null'
```

## Integración con squash

*Settings → General → Pull Requests*:

- Allow squash merging, con **Default to pull request title and description**.
- Desactivar merge commits y rebase merging.
- Automatically delete head branches.

El mensaje del pull request queda como commit final en `main`, así que debe
cumplir la convención: título `tipo(ambito): descripcion` y `Refs: AGI-nnn` en el
cuerpo.

## Etiquetas de release

Cada release se etiqueta al cerrarse:

```bash
git tag -a v1.0 -m "Release 1: primera versión local"
git push origin v1.0
```

`v1.0` al cerrar el Release 1, `v2.0` el Release 2 y `v3.0` el Release 3. Es lo
que permite volver al estado exacto de la entrega.

## Code owners

`.github/CODEOWNERS` tiene un usuario de GitHub por reemplazar. Sin eso, la
regla «Require review from Code Owners» no pide a nadie.
