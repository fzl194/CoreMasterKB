from pydantic_settings import BaseSettings
from pydantic import Field


class LLMServiceConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8900

    db_path: str = "data/llm_service.sqlite"

    provider_base_url: str = "https://api.openai.com/v1"
    provider_api_key: str = ""
    provider_model: str = "gpt-4o"
    provider_headers: dict = Field(default_factory=dict)
    provider_timeout: int = 30

    worker_concurrency: int = 4
    default_max_attempts: int = 3
    retry_backoff_base: float = 2.0
    retry_backoff_max: float = 60.0

    execute_timeout: int = 60
    lease_duration: int = 300

    model_config = {"env_prefix": "LLM_SERVICE_"}
