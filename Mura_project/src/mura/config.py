from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from mura.identity.auth import DEFAULT_ALLOWED_ALGORITHMS, AuthMode, validate_jwks_url
from mura.storage.audio import AudioStorageBackend

_POSTGRES_SCHEME_PREFIXES = ("postgresql", "postgres")
_SQLITE_SCHEME_PREFIX = "sqlite"
_ALLOWED_ORIGIN_SCHEMES = frozenset({"http", "https"})


class Environment(StrEnum):
    """Deployment environment. Production-like environments fail closed on unsafe settings."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_production_like(self) -> bool:
        return self in {Environment.STAGING, Environment.PRODUCTION}


def _is_postgres_url(database_url: str) -> bool:
    return database_url.startswith(_POSTGRES_SCHEME_PREFIXES)


def _is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith(_SQLITE_SCHEME_PREFIX)


def _split_delimited(value: object) -> object:
    """Accept comma-separated environment values without requiring JSON encoding."""

    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


def _is_rooted_path(path: Path) -> bool:
    """Absolute on the deployment platform, not merely on this one.

    Path('/srv/mura/audio').is_absolute() is False on Windows because it has no
    drive letter, yet it is exactly the path a Linux deployment uses. Accept a
    leading separator as rooted so development on Windows can still validate a
    production configuration.
    """

    return path.is_absolute() or str(path).startswith(("/", "\\"))


def _validate_origin(origin: str) -> None:
    parsed = urlparse(origin)
    if parsed.scheme not in _ALLOWED_ORIGIN_SCHEMES or not parsed.netloc:
        raise ValueError(f"CORS origin must be scheme://host[:port]: {origin!r}")
    if parsed.path or parsed.params or parsed.query or parsed.fragment:
        raise ValueError(f"CORS origin must not contain a path or query: {origin!r}")


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Environment = Field(default=Environment.LOCAL, alias="MURA_ENVIRONMENT")

    deepseek_api_key: str = Field(alias="DEEPSEEK_API_KEY", min_length=8)
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-v4-flash", alias="DEEPSEEK_MODEL")
    deepseek_fallback_model: str = Field(
        default="deepseek-v4-pro",
        alias="DEEPSEEK_FALLBACK_MODEL",
    )
    core_api_key: str = Field(alias="CORE_API_KEY", min_length=32)
    worker_registration_token: str = Field(
        alias="WORKER_REGISTRATION_TOKEN",
        min_length=32,
    )
    #: Destructive operator routes use their own credential: a leaked frontend
    #: token must not be able to activate a release or apply retention.
    operations_api_key: str = Field(alias="OPERATIONS_API_KEY", min_length=32)
    kaggle_asr_api_key: str = Field(alias="KAGGLE_ASR_API_KEY", min_length=32)
    database_url: str = Field(alias="DATABASE_URL", min_length=1)
    database_auto_create: bool = Field(default=False, alias="DATABASE_AUTO_CREATE")
    audio_storage_backend: AudioStorageBackend = Field(
        default=AudioStorageBackend.LOCAL,
        alias="AUDIO_STORAGE_BACKEND",
    )
    audio_storage_dir: Path = Field(default=Path(".mura/audio"), alias="AUDIO_STORAGE_DIR")
    core_max_upload_mb: int = Field(default=25, alias="CORE_MAX_UPLOAD_MB", ge=1, le=200)
    job_poll_interval_seconds: float = Field(
        default=1.0,
        alias="JOB_POLL_INTERVAL_SECONDS",
        ge=0.1,
        le=60,
    )
    asr_retry_seconds: float = Field(default=15.0, alias="ASR_RETRY_SECONDS", ge=1, le=600)
    # Lease duration is sized against real provider bounds, not a round number.
    # A single job may spend up to ASR_REQUEST_TIMEOUT_SECONDS (900s default) in
    # one transcription call, and long-form extraction adds up to 6 windows of
    # DeepSeek work, so processing legitimately outlives any short lease. The
    # heartbeat is what keeps ownership alive; the lease only has to survive
    # several missed heartbeats, so 300s with 60s ticks tolerates four
    # consecutive failures before another worker may recover the job.
    job_lease_seconds: float = Field(
        default=300.0,
        alias="JOB_LEASE_SECONDS",
        ge=10,
        le=3600,
    )
    job_heartbeat_seconds: float = Field(
        default=60.0,
        alias="JOB_HEARTBEAT_SECONDS",
        ge=1,
        le=600,
    )
    asr_request_timeout_seconds: float = Field(
        default=900.0,
        alias="ASR_REQUEST_TIMEOUT_SECONDS",
        ge=30,
        le=3600,
    )

    auth_mode: AuthMode = Field(default=AuthMode.DISABLED, alias="AUTH_MODE")
    auth_issuer: str | None = Field(default=None, alias="AUTH_ISSUER")
    auth_audience: str | None = Field(default=None, alias="AUTH_AUDIENCE")
    auth_jwks_url: str | None = Field(default=None, alias="AUTH_JWKS_URL")
    auth_allowed_algorithms: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_ALGORITHMS),
        alias="AUTH_ALLOWED_ALGORITHMS",
    )
    auth_clock_skew_seconds: int = Field(default=30, alias="AUTH_CLOCK_SKEW_SECONDS", ge=0, le=300)
    auth_jwks_cache_seconds: int = Field(
        default=300, alias="AUTH_JWKS_CACHE_SECONDS", ge=30, le=86_400
    )

    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        alias="CORS_ALLOWED_ORIGINS",
    )
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        alias="ALLOWED_HOSTS",
    )
    expose_api_docs: bool | None = Field(default=None, alias="EXPOSE_API_DOCS")

    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE", ge=1, le=50)
    db_max_overflow: int = Field(default=5, alias="DB_MAX_OVERFLOW", ge=0, le=50)
    db_pool_recycle_seconds: int = Field(
        default=1800,
        alias="DB_POOL_RECYCLE_SECONDS",
        ge=60,
        le=86_400,
    )
    db_connect_timeout_seconds: int = Field(
        default=10,
        alias="DB_CONNECT_TIMEOUT_SECONDS",
        ge=1,
        le=60,
    )
    db_statement_timeout_seconds: int = Field(
        default=30,
        alias="DB_STATEMENT_TIMEOUT_SECONDS",
        ge=1,
        le=600,
    )

    @field_validator(
        "cors_allowed_origins", "allowed_hosts", "auth_allowed_algorithms", mode="before"
    )
    @classmethod
    def accept_delimited_values(cls, value: object) -> object:
        return _split_delimited(value)

    @property
    def api_docs_enabled(self) -> bool:
        """Docs default to on for local/test and off everywhere else unless set explicitly."""

        if self.expose_api_docs is not None:
            return self.expose_api_docs
        return self.environment in {Environment.LOCAL, Environment.TEST}

    @model_validator(mode="after")
    def validate_auth_invariants(self) -> CoreSettings:
        production_like = self.environment.is_production_like
        if production_like and self.auth_mode is not AuthMode.OIDC:
            raise ValueError(
                "AUTH_MODE must be 'oidc' in staging and production; the disabled "
                "mode exists only for local development and tests"
            )
        if self.auth_mode is AuthMode.OIDC:
            missing = [
                name
                for name, value in (
                    ("AUTH_ISSUER", self.auth_issuer),
                    ("AUTH_AUDIENCE", self.auth_audience),
                    ("AUTH_JWKS_URL", self.auth_jwks_url),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"{', '.join(missing)} required when AUTH_MODE is oidc")
            assert self.auth_jwks_url is not None
            # The JWKS endpoint is trusted configuration; a token never picks it.
            validate_jwks_url(self.auth_jwks_url, require_https=production_like)
            symmetric = [a for a in self.auth_allowed_algorithms if a.upper().startswith("HS")]
            if symmetric:
                raise ValueError(
                    "AUTH_ALLOWED_ALGORITHMS must not mix symmetric HS* with "
                    "public-key verification"
                )
            if "none" in {a.lower() for a in self.auth_allowed_algorithms}:
                raise ValueError("AUTH_ALLOWED_ALGORITHMS must never include 'none'")
        return self

    @model_validator(mode="after")
    def validate_lease_invariants(self) -> CoreSettings:
        # A heartbeat at or beyond the lease could never renew in time, so the
        # job would be recovered from under a perfectly healthy worker.
        if self.job_heartbeat_seconds >= self.job_lease_seconds:
            raise ValueError("JOB_HEARTBEAT_SECONDS must be shorter than JOB_LEASE_SECONDS")
        if self.job_lease_seconds < 3 * self.job_heartbeat_seconds:
            raise ValueError(
                "JOB_LEASE_SECONDS must allow at least three heartbeats "
                "so a transient database blip does not lose the lease"
            )
        return self

    @model_validator(mode="after")
    def validate_environment_invariants(self) -> CoreSettings:
        production_like = self.environment.is_production_like

        if production_like and self.database_auto_create:
            raise ValueError(
                "DATABASE_AUTO_CREATE must be false in staging and production; "
                "apply Alembic migrations instead"
            )
        if production_like and not _is_postgres_url(self.database_url):
            raise ValueError("DATABASE_URL must target PostgreSQL in staging and production")
        if production_like and _is_sqlite_url(self.database_url):
            raise ValueError("SQLite is not a supported database in staging and production")
        if production_like and self.operations_api_key == self.core_api_key:
            raise ValueError(
                "OPERATIONS_API_KEY must differ from CORE_API_KEY so a leaked "
                "application token cannot reach destructive operator routes"
            )
        if production_like and not _is_rooted_path(self.audio_storage_dir):
            raise ValueError(
                "AUDIO_STORAGE_DIR must be an absolute path outside staging and "
                "production working directories"
            )
        if production_like and not self.cors_allowed_origins:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must list at least one origin in staging and production"
            )

        for origin in self.cors_allowed_origins:
            if origin == "*":
                if production_like:
                    raise ValueError(
                        'CORS_ALLOWED_ORIGINS must not contain "*" in staging and production'
                    )
                continue
            _validate_origin(origin)

        return self


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    #: Destructive operator routes use their own credential: a leaked frontend
    #: token must not be able to activate a release or apply retention.
    operations_api_key: str = Field(alias="OPERATIONS_API_KEY", min_length=32)
    kaggle_asr_api_key: str = Field(alias="KAGGLE_ASR_API_KEY", min_length=32)
    hf_token: str | None = Field(default=None, alias="HF_TOKEN")
    asr_device: str = Field(default="cuda:0", alias="ASR_DEVICE")
    max_upload_mb: int = Field(default=25, alias="MAX_UPLOAD_MB", ge=1, le=200)
    max_audio_seconds: int = Field(default=900, alias="MAX_AUDIO_SECONDS", ge=10, le=3600)
    core_backend_url: str | None = Field(default=None, alias="CORE_BACKEND_URL")
    worker_registration_token: str | None = Field(
        default=None,
        alias="WORKER_REGISTRATION_TOKEN",
        min_length=32,
    )

    @model_validator(mode="after")
    def require_registration_token_for_callback(self) -> WorkerSettings:
        if self.core_backend_url and not self.worker_registration_token:
            raise ValueError(
                "WORKER_REGISTRATION_TOKEN is required when CORE_BACKEND_URL is configured"
            )
        return self
