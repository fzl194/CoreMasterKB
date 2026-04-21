# LLM Service

Unified LLM call and audit service for CoreMasterKB Mining/Serving modules.

## Architecture

- **FastAPI** independent service on port 8900
- **SQLite** (WAL mode) with 6 tables: `agent_llm_prompt_templates`, `agent_llm_tasks`, `agent_llm_requests`, `agent_llm_attempts`, `agent_llm_results`, `agent_llm_events`
- Single execution engine shared by `/tasks` (async) and `/execute` (sync)
- OpenAI-compatible provider with configurable base_url/api_key/headers
- Jinja2+HTMX dashboard at `/dashboard`

## Quick Start

```bash
# Install dependencies
pip install -e ".[llm]"

# Start the service
python -m llm_service.main

# Or with custom config
LLM_SERVICE_PORT=8900 LLM_SERVICE_DB_PATH=data/llm.sqlite python -m llm_service.main
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /api/v1/tasks | Submit async task |
| POST | /api/v1/execute | Execute synchronously |
| GET | /api/v1/tasks/{id} | Get task detail |
| POST | /api/v1/tasks/{id}/cancel | Cancel task |
| GET | /api/v1/tasks/{id}/result | Get parsed result |
| GET | /api/v1/tasks/{id}/attempts | Get all attempts |
| GET | /api/v1/tasks/{id}/events | Get event log |
| GET | /dashboard | Web dashboard |
| GET | /dashboard/api/stats | Stats JSON |

## Configuration

All via environment variables with `LLM_SERVICE_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_SERVICE_HOST` | 0.0.0.0 | Bind host |
| `LLM_SERVICE_PORT` | 8900 | Bind port |
| `LLM_SERVICE_DB_PATH` | data/llm_service.sqlite | Database path |
| `LLM_SERVICE_PROVIDER_BASE_URL` | https://api.openai.com/v1 | LLM API base URL |
| `LLM_SERVICE_PROVIDER_API_KEY` | | API key |
| `LLM_SERVICE_PROVIDER_MODEL` | gpt-4o | Default model |
| `LLM_SERVICE_DEFAULT_MAX_ATTEMPTS` | 3 | Max retry attempts |
| `LLM_SERVICE_LEASE_DURATION` | 300 | Worker lease (seconds) |

## Client Usage

```python
from llm_service.client import LLMClient

client = LLMClient(base_url="http://localhost:8900")

# Sync execute
result = await client.execute(
    caller_domain="mining",
    pipeline_stage="extract",
    messages=[{"role": "user", "content": "Extract entities from: ..."}],
    expected_output_type="json_object",
)

# Async submit
task_id = await client.submit(
    caller_domain="serving",
    pipeline_stage="search",
    messages=[{"role": "user", "content": "Search for: ..."}],
    idempotency_key="unique-key-123",
)
task = await client.get_task(task_id)
```

## Tests

```bash
pytest llm_service/tests/ -v
```
