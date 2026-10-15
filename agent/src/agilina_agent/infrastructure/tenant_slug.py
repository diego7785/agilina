"""The form of a tenant slug, the same rule the API applies when it creates a tenant.

The tenant reaches the worker inside a room name, which anyone with LiveKit access can
choose: nothing builds a URL, a header or a path from it before it passes this check.
"""

import re

TENANT_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9]{1,30}$")


def is_tenant_slug(value: str) -> bool:
    return TENANT_SLUG_PATTERN.fullmatch(value) is not None
