from fastapi import FastAPI

from llm_service.config import LLMServiceConfig


def create_app(config: LLMServiceConfig | None = None) -> FastAPI:
    cfg = config or LLMServiceConfig()
    app = FastAPI(title="LLM Service", version="0.1.0")
    app.state.config = cfg
    return app
