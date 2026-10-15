"""Text helpers shared by the mock, the cases and the evaluator (no internal dependencies)."""

import hashlib
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_DECOMPOSED_FORM = "NFKD"
_COMBINING_MARK = "Mn"


def normalize_for_match(text: str) -> str:
    """Casefold the text and collapse every run of whitespace into a single space."""
    return _WHITESPACE.sub(" ", text.casefold())


def fold_for_match(text: str) -> str:
    """Tolerant form for criteria: NFKD, drop combining marks (Mn), casefold, collapse spaces.

    "Migración  de DATOS" and "migracion de datos" fold to the same text. The mock and
    ``injection_reached_model`` keep using ``normalize_for_match`` so their decision does not
    change.
    """
    decomposed = unicodedata.normalize(_DECOMPOSED_FORM, text)
    kept = (char for char in decomposed if unicodedata.category(char) != _COMBINING_MARK)
    stripped = "".join(kept)
    return _WHITESPACE.sub(" ", stripped.casefold())


def sha256_hex(text: str) -> str:
    """Return the SHA-256 hex digest of the UTF-8 encoding of ``text``."""
    return hashlib.sha256(text.encode()).hexdigest()
