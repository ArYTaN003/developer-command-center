"""Configuration for rag-context-service."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "rag-context-service"

    # --- Qdrant ---
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection: str = "github_context"

    # --- Redis (session summary cache) ---
    redis_host: str = "redis"
    redis_port: int = 6379
    cache_ttl_seconds: int = 3600

    # --- RabbitMQ ---
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_events_exchange: str = "github.events"

    # --- gRPC (Lab 3B: ContextService, served alongside REST) ---
    grpc_port: int = 50051

    # --- Embeddings ---
    embedding_mode: str = "hash"   # "hash" (local, zero-download) | "st"
    embedding_dim: int = 256

    # --- Claude (placeholder-friendly) ---
    anthropic_api_key: str = "PLACEHOLDER_ANTHROPIC_API_KEY"
    anthropic_base_url: str = "https://api.anthropic.com"
    claude_model: str = "claude-haiku-4-5"

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
