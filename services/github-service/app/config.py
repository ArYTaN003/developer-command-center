"""Configuration for github-service, loaded from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "github-service"

    # --- GitHub API (placeholder-friendly) ---
    github_token: str = "PLACEHOLDER_GITHUB_TOKEN"
    github_api_url: str = "https://api.github.com"
    github_repos: str = "octocat/hello-world"
    github_poll_enabled: bool = False
    github_poll_interval_minutes: int = 10

    # --- Circuit breaker for outbound GitHub calls ---
    github_breaker_fail_max: int = 5
    github_breaker_reset_timeout: int = 30

    # --- PostgreSQL (github-db) ---
    db_host: str = "github-db"
    db_port: int = 5432
    db_name: str = "github"
    db_user: str = "github"
    db_password: str = "github"

    # --- RabbitMQ ---
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_events_exchange: str = "github.events"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def amqp_url(self) -> str:
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/"
        )

    @property
    def github_token_is_placeholder(self) -> bool:
        return (not self.github_token) or self.github_token.startswith("PLACEHOLDER")


settings = Settings()
