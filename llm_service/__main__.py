import uvicorn

from llm_service.config import LLMServiceConfig


def main():
    cfg = LLMServiceConfig()
    uvicorn.run(
        "llm_service.main:create_app",
        host=cfg.host,
        port=cfg.port,
        factory=True,
    )


if __name__ == "__main__":
    main()
