"""Creating the realm of a tenant in Keycloak (AD-29).

Used by the operator's tools (``make tenant-add``), not by the API while it serves requests.
It signs in as Keycloak's own administrator, with the credentials of the ``.env``, and creates
the realm from a representation: the template ``infra/keycloak/realm-template.json`` with the
tenant's values put in.
"""

import json
import string
from pathlib import Path

import httpx

TEMPLATE = Path(__file__).resolve().parents[6] / "infra" / "keycloak" / "realm-template.json"


def render_realm(
    realm: str, name: str, locale: str, api_secret: str, worker_secret: str
) -> dict[str, object]:
    """The realm of a tenant: the template with ``${TENANT_…}`` replaced by its values.

    ``substitute`` fails on a placeholder it was not given, so a template that grows a new
    one cannot be used half filled in."""
    values = {
        "TENANT_REALM": realm,
        "TENANT_NAME": name,
        "TENANT_LOCALE": locale,
        "TENANT_API_SECRET": api_secret,
        "TENANT_WORKER_SECRET": worker_secret,
    }
    # JSON-escaped, so that a name with quotes cannot break out of its string.
    escaped = {key: json.dumps(value)[1:-1] for key, value in values.items()}
    rendered = string.Template(TEMPLATE.read_text(encoding="utf-8")).substitute(escaped)
    realm_representation: dict[str, object] = json.loads(rendered)
    return realm_representation


class KeycloakRealmProvisioner:
    def __init__(
        self,
        *,
        base_url: str,
        admin_user: str,
        admin_password: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._admin_user = admin_user
        self._admin_password = admin_password
        self._client = client or httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def ensure_realm(self, realm: dict[str, object]) -> bool:
        """Creates the realm unless it exists. ``True`` when it was created."""
        name = str(realm["realm"])
        headers = {"Authorization": f"Bearer {self._admin_token()}"}
        found = self._client.get(f"{self._base_url}/admin/realms/{name}", headers=headers)
        if found.status_code == httpx.codes.OK:
            return False
        if found.status_code != httpx.codes.NOT_FOUND:
            raise RuntimeError(f"Keycloak answered {found.status_code} looking for realm {name}")
        created = self._client.post(f"{self._base_url}/admin/realms", headers=headers, json=realm)
        if created.status_code != httpx.codes.CREATED:
            raise RuntimeError(f"Keycloak answered {created.status_code} creating realm {name}")
        return True

    def _admin_token(self) -> str:
        response = self._client.post(
            f"{self._base_url}/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": self._admin_user,
                "password": self._admin_password,
            },
        )
        if response.status_code != httpx.codes.OK:
            raise RuntimeError(
                f"Keycloak refused the administrator's credentials ({response.status_code})"
            )
        return str(response.json()["access_token"])
