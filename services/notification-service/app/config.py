"""Configuration for notification-service."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "notification-service"

    # --- Claude (placeholder-friendly) ---
    anthropic_api_key: str = "PLACEHOLDER_ANTHROPIC_API_KEY"
    anthropic_base_url: str = "https://api.anthropic.com"
    claude_model: str = "claude-haiku-4-5"

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379

    # --- RabbitMQ ---
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_events_exchange: str = "github.events"
    rabbitmq_notifications_exchange: str = "notifications"

    # --- Peer services ---
    ai_review_url: str = "http://ai-review-service:8000"

    # --- Digest schedule (UTC) ---
    digest_cron_hour: int = 8
    digest_cron_minute: int = 0

    @property
    def amqp_url(self) -> str:
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/"
        )

    @property
    def anthropic_is_placeholder(self) -> bool:
        return (not self.anthropic_api_key) or self.anthropic_api_key.startswith("PLACEHOLDER")


settings = Settings()
