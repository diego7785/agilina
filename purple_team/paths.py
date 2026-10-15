"""Single rule for every path written to a record (plan section 7.3)."""

from pathlib import Path


def display_path(path: Path, base: Path) -> str:
    """Return ``path`` relative to ``base`` when it is inside it, otherwise absolute.

    Both paths are resolved first so that symbolic links (``/var`` -> ``/private/var`` on
    macOS) do not break the comparison. The result always uses POSIX separators.
    """
    resolved = path.resolve()
    resolved_base = base.resolve()
    if resolved.is_relative_to(resolved_base):
        return resolved.relative_to(resolved_base).as_posix()
    return resolved.as_posix()
