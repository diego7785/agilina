"""Team configuration that Agilina knows (members, Slack, Jira issues, OneDrive folder).

It is trusted configuration, not ceremony data: the core sends it to the model in its own
block, separated from the (untrusted) transcript, the output guard derives its allowed
destinations from it and the automatic system outputs take their fixed destinations from it,
so all of them use a single source of truth.

Version 2 (cycle 4, handoff/18): every member has a Slack user (direct messages and
``slack_message``) and an email (calendar invitations only); the team has a Slack channel, a
Jira project with some existing issues and a fixed OneDrive folder for the summary Excel.
"""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from purple_team.core.text import sha256_hex
from purple_team.errors import ConfigError

TEAM_CONTEXT_SCHEMA_VERSION: Final = 2
LEGACY_SCHEMA_VERSION: Final = 1
TOP_LEVEL_KEYS: Final = frozenset(
    {
        "schema_version",
        "team_name",
        "members",
        "slack_channel",
        "jira_project_key",
        "jira_issues",
        "onedrive_folder",
    }
)
MEMBER_KEYS: Final = frozenset({"name", "role", "slack_user", "email"})
ISSUE_KEYS: Final = frozenset({"key", "title"})
EMAIL_PATTERN: Final = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
JIRA_KEY_PATTERN: Final = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
# Slack form: lowercase, no spaces, at most 80 characters after the prefix.
SLACK_USER_PATTERN: Final = re.compile(r"^@[a-z0-9][a-z0-9._-]{0,79}$")
SLACK_CHANNEL_PATTERN: Final = re.compile(r"^#[a-z0-9][a-z0-9_-]{0,79}$")
ISSUE_NUMBER_PATTERN: Final = "[1-9][0-9]*"
FOLDER_SEPARATOR: Final = "/"
PATH_TRAVERSAL: Final = ".."


@dataclass(frozen=True, slots=True)
class TeamMember:
    """A member of the team: Slack user for messages, email only for calendar invitations."""

    name: str
    role: str
    slack_user: str
    email: str

    def to_dict(self) -> dict[str, str]:
        """JSON view."""
        return {
            "name": self.name,
            "role": self.role,
            "slack_user": self.slack_user,
            "email": self.email,
        }


@dataclass(frozen=True, slots=True)
class JiraIssue:
    """An existing issue of the team project (Agilina comments issues, never creates them)."""

    key: str
    title: str

    def to_dict(self) -> dict[str, str]:
        """JSON view."""
        return {"key": self.key, "title": self.title}


@dataclass(frozen=True, slots=True)
class TeamContext:
    """Validated team context; ``sha256`` is the hash of the file as it was read."""

    team_name: str
    members: tuple[TeamMember, ...]
    slack_channel: str
    jira_project_key: str
    jira_issues: tuple[JiraIssue, ...]
    onedrive_folder: str
    source: Path
    sha256: str

    @property
    def member_emails(self) -> tuple[str, ...]:
        """Addresses of the members, in the order of the file."""
        return tuple(member.email for member in self.members)

    @property
    def member_slack_users(self) -> tuple[str, ...]:
        """Slack users of the members, in the order of the file."""
        return tuple(member.slack_user for member in self.members)

    @property
    def jira_issue_keys(self) -> tuple[str, ...]:
        """Keys of the listed issues, in the order of the file."""
        return tuple(issue.key for issue in self.jira_issues)

    def model_view(self) -> dict[str, object]:
        """What the model receives (no file path or hash)."""
        return {
            "team_name": self.team_name,
            "members": [member.to_dict() for member in self.members],
            "slack_channel": self.slack_channel,
            "jira_project_key": self.jira_project_key,
            "jira_issues": [issue.to_dict() for issue in self.jira_issues],
            "onedrive_folder": self.onedrive_folder,
        }

    def render_for_model(self) -> str:
        """Deterministic JSON text of ``model_view`` (keys in a fixed order)."""
        return json.dumps(self.model_view(), ensure_ascii=False, indent=2)

    def to_record(self, display: Callable[[Path], str]) -> dict[str, object]:
        """View for the run records; ``display`` applies the single path rule."""
        return {"file": display(self.source), "sha256": self.sha256, **self.model_view()}


def load_team_context(path: Path) -> TeamContext:
    """Read and validate the team context; raise ``ConfigError`` naming the file and reason."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"No se pudo leer el contexto del equipo {path}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        message = f"El contexto del equipo {path} no es JSON válido ({exc.msg}, línea {exc.lineno})"
        raise ConfigError(message) from exc
    where = f"contexto del equipo {path}"
    if not isinstance(data, dict):
        raise ConfigError(f"El {where} debe contener un objeto JSON")
    version = data.get("schema_version")
    if not isinstance(version, bool) and version == LEGACY_SCHEMA_VERSION:
        message = (
            f"{where}: schema_version {LEGACY_SCHEMA_VERSION} ya no se admite: añade slack_user "
            "a cada miembro, slack_channel y jira_issues (README §4)"
        )
        raise ConfigError(message)
    _require_exact_keys(data, TOP_LEVEL_KEYS, where)
    if isinstance(version, bool) or version != TEAM_CONTEXT_SCHEMA_VERSION:
        raise ConfigError(f"{where}: schema_version debe ser {TEAM_CONTEXT_SCHEMA_VERSION}")
    project_key = _jira_key(data, where)
    return TeamContext(
        team_name=_text(data, "team_name", where),
        members=_members(data.get("members"), where),
        slack_channel=_slack_channel(data, where),
        jira_project_key=project_key,
        jira_issues=_issues(data.get("jira_issues"), project_key, where),
        onedrive_folder=_onedrive_folder(data, where),
        source=path,
        sha256=sha256_hex(text),
    )


def _members(value: object, where: str) -> tuple[TeamMember, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{where}: members debe ser una lista no vacía de objetos")
    members = []
    for index, entry in enumerate(value):
        entry_where = f"{where}, members[{index}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{entry_where} debe ser un objeto")
        _require_exact_keys(entry, MEMBER_KEYS, entry_where)
        email = _text(entry, "email", entry_where)
        if not EMAIL_PATTERN.match(email):
            raise ConfigError(f"{entry_where}: email inválido {email!r}")
        slack_user = _text(entry, "slack_user", entry_where)
        if not SLACK_USER_PATTERN.match(slack_user):
            pattern = SLACK_USER_PATTERN.pattern
            raise ConfigError(f"{entry_where}: slack_user {slack_user!r} no cumple {pattern}")
        member = TeamMember(
            name=_text(entry, "name", entry_where),
            role=_text(entry, "role", entry_where),
            slack_user=slack_user,
            email=email,
        )
        members.append(member)
    names = [member.name for member in members]
    emails = [member.email.casefold() for member in members]
    users = [member.slack_user.casefold() for member in members]
    if any(len(set(values)) != len(values) for values in (names, emails, users)):
        message = f"{where}: los nombres, los correos y los slack_user de members deben ser únicos"
        raise ConfigError(message)
    return tuple(members)


def _issues(value: object, project_key: str, where: str) -> tuple[JiraIssue, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{where}: jira_issues debe ser una lista no vacía de objetos")
    pattern = re.compile(f"^{re.escape(project_key)}-{ISSUE_NUMBER_PATTERN}$")
    issues = []
    for index, entry in enumerate(value):
        entry_where = f"{where}, jira_issues[{index}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{entry_where} debe ser un objeto")
        _require_exact_keys(entry, ISSUE_KEYS, entry_where)
        key = _text(entry, "key", entry_where)
        if not pattern.match(key):
            raise ConfigError(f"{entry_where}: key {key!r} no cumple {pattern.pattern}")
        issues.append(JiraIssue(key=key, title=_text(entry, "title", entry_where)))
    keys = [issue.key for issue in issues]
    if len(set(keys)) != len(keys):
        raise ConfigError(f"{where}: las claves de jira_issues deben ser únicas")
    return tuple(issues)


def _slack_channel(data: Mapping[str, object], where: str) -> str:
    channel = _text(data, "slack_channel", where)
    if not SLACK_CHANNEL_PATTERN.match(channel):
        message = f"{where}: slack_channel {channel!r} no cumple {SLACK_CHANNEL_PATTERN.pattern}"
        raise ConfigError(message)
    return channel


def _jira_key(data: Mapping[str, object], where: str) -> str:
    key = _text(data, "jira_project_key", where)
    if not JIRA_KEY_PATTERN.match(key):
        raise ConfigError(f"{where}: jira_project_key {key!r} no cumple {JIRA_KEY_PATTERN.pattern}")
    return key


def _onedrive_folder(data: Mapping[str, object], where: str) -> str:
    folder = _text(data, "onedrive_folder", where)
    valid_ends = folder.startswith(FOLDER_SEPARATOR) and folder.endswith(FOLDER_SEPARATOR)
    if not valid_ends or PATH_TRAVERSAL in folder:
        message = f"{where}: onedrive_folder debe empezar y terminar por '/' y no contener '..'"
        raise ConfigError(message)
    return folder


def _require_exact_keys(data: Mapping[str, object], keys: frozenset[str], where: str) -> None:
    unknown = sorted(set(data) - keys)
    missing = sorted(keys - set(data))
    if unknown or missing:
        detail = f"desconocidas={unknown}, faltantes={missing}"
        raise ConfigError(f"{where}: claves inválidas ({detail})")


def _text(data: Mapping[str, object], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: {key} debe ser un texto no vacío")
    return value
