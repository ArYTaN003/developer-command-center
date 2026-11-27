"""Configuration for ai-review-service."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "ai-review-service"

    # --- Claude (placeholder-friendly) ---
    anthropic_api_key: str = "PLACEHOLDER_ANTHROPIC_API_KEY"
    anthropic_base_url: str = "https://api.anthropic.com"
    claude_model: str = "claude-haiku-4-5"

    # --- Circuit breakers ---
    claude_breaker_fail_max: int = 2
    claude_breaker_reset_timeout: int = 10
    rag_breaker_fail_max: int = 3
    rag_breaker_reset_timeout: int = 15

    # --- RAG context service (sync dependency) ---
    rag_context_url: str = "http://rag-context-service:8000"
    # gRPC target for the ContextService (Lab 3B); same DNS in Compose and K8s.
    rag_grpc_target: str = "rag-context-service:50051"

    # --- PostgreSQL (reviews-db) ---
    db_host: str = "reviews-db"
    db_port: int = 5432
    db_name: str = "reviews"
    db_user: str = "reviews"
    db_password: str = "reviews"

    # --- RabbitMQ ---
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_events_exchange: str = "github.events"
    rabbitmq_notifications_exchange: str = "notifications"

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
    def anthropic_is_placeholder(self) -> bool:
        return (not self.anthropic_api_key) or self.anthropic_api_key.startswith("PLACEHOLDER")


settings = Settings()
