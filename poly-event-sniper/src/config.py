"""Configuration architecture using pydantic-settings for typed environment loading."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class PolygonConfig(BaseSettings):
    """Polygon network configuration."""

    model_config = SettingsConfigDict(
        env_prefix="POLYGON_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    private_key: SecretStr
    rpc_url: str


class ClobConfig(BaseSettings):
    """Polymarket CLOB API configuration.

    API credentials are optional - if not provided, they will be
    auto-derived from the POLYGON_PRIVATE_KEY at runtime.
    """

    model_config = SettingsConfigDict(
        env_prefix="CLOB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Optional - will be derived from private key if not set
    api_key: SecretStr = SecretStr("")
    api_secret: SecretStr = SecretStr("")
    api_passphrase: SecretStr = SecretStr("")


class BotConfig(BaseSettings):
    """Bot runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="BOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    dry_run: bool = True
    poll_interval: float = 1.0
    max_position_size: float = 1000.0


class IngesterConfig(BaseSettings):
    """Ingester runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="INGESTER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    reconnect_attempts: int = 5
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    heartbeat_interval: float = 30.0


class ParserConfig(BaseSettings):
    """Parser runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="PARSER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    default_cooldown_seconds: float = 60.0


class Settings:
    """Root settings aggregating all configuration sections."""

    def __init__(self) -> None:
        self.polygon = PolygonConfig()
        self.clob = ClobConfig()
        self.bot = BotConfig()
        self.ingester = IngesterConfig()
        self.parser = ParserConfig()


# Global settings instance - lazily loaded
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
