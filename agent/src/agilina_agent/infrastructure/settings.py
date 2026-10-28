"""Worker settings.

The worker has no database setting at all (AGI-64): the API is its only source of truth.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agilina_shared.enums import Language

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PENDING_DIR = REPO_ROOT / "infra" / "datos" / "agent-pending"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        env_prefix="AGILINA_",
        extra="ignore",
    )

    environment: str = "local"
    log_level: str = "INFO"
    default_language: Language = Language.ES

    # LiveKit: only what the worker needs to register. The agent's room token is issued by
    # LiveKit when it dispatches the job, with the permissions the worker declares.
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # The API is the only source of context and the only destination of the result.
    api_public_url: str = "http://localhost:8000"

    # Keycloak service account the worker authenticates with, in the realm of each tenant
    # (AD-29): the realm is this prefix and the slug, the same key the API and the web read.
    keycloak_url: str = "http://localhost:8080"
    tenant_realm_prefix: str = "agilina-"
    keycloak_worker_client: str = "agilina-worker"

    # Results not yet accepted by the API, one file per ceremony (CA6).
    agent_pending_dir: Path = DEFAULT_PENDING_DIR

    # Transcription service, never exposed to the internet.
    stt_url: str = "http://localhost:8001"

    # Speech synthesis. The key only lives in .env and never shows up in a log or a repr.
    elevenlabs_api_key: SecretStr = SecretStr("")
    # A free plan model (HU-01 spike); eleven_flash_v2_5 is the fallback if it gets slow.
    elevenlabs_model: str = "eleven_v4_turbo"
    elevenlabs_voice_es: str = ""
    elevenlabs_voice_en: str = ""

    @field_validator("agent_pending_dir", mode="before")
    @classmethod
    def _default_pending_dir_when_empty(cls, value: object) -> object:
        # .env.example leaves it empty, and an empty path would be the working directory.
        return value or DEFAULT_PENDING_DIR

    def worker_secret(self, slug: str) -> SecretStr:
        """The secret of the ``agilina-worker`` client of the tenant's realm, in
        ``AGILINA_TENANT_<SLUG>_KEYCLOAK_WORKER_SECRET``. Never in the repository."""
        return SecretStr(
            os.environ.get(f"AGILINA_TENANT_{slug.upper()}_KEYCLOAK_WORKER_SECRET", "")
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
