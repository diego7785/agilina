"""Exceptions shared by several modules (no internal dependencies)."""


class ConfigError(ValueError):
    """The harness configuration is invalid (CLI exit code 1)."""


class CaseFormatError(ValueError):
    """A test case definition is malformed (CLI exit code 1)."""


class RunExistsError(FileExistsError):
    """A run folder or a comparison CSV already exists (CLI exit code 1)."""


class DefenseUnavailableError(RuntimeError):
    """An optional defense (LLM Guard) is not installed or cannot load (CLI exit code 4)."""
