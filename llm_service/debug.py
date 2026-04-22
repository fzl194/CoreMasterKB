"""Debug entry point — breakpoints will hit in your IDE.

Usage:
    python llm_service/debug.py

Or run this file directly in VS Code / PyCharm debugger.
"""
import uvicorn
from llm_service.config import LLMServiceConfig
from llm_service.main import create_app

cfg = LLMServiceConfig()

# create_app() is called here, breakpoints in lifespan/service will work
app = create_app(cfg)

if __name__ == "__main__":
    uvicorn.run(app, host=cfg.host, port=cfg.port)
