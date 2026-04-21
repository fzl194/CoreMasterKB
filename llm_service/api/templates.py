from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/templates")


class TemplateCreateRequest(BaseModel):
    template_key: str
    template_version: str = "1"
    purpose: str
    system_prompt: str | None = None
    user_prompt_template: str
    expected_output_type: str = Field(default="json_object", pattern=r"^(json_object|json_array|text)$")
    output_schema_json: str = "{}"
    status: str = Field(default="active", pattern=r"^(draft|active|archived)$")


class TemplateUpdateRequest(BaseModel):
    template_version: str | None = None
    purpose: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    expected_output_type: str | None = Field(default=None, pattern=r"^(json_object|json_array|text)$")
    output_schema_json: str | None = None
    status: str | None = Field(default=None, pattern=r"^(draft|active|archived)$")


@router.post("")
async def create_template(body: TemplateCreateRequest, request: Request):
    svc = request.app.state.llm_service
    tpl_id = await svc._templates.create(
        template_key=body.template_key,
        template_version=body.template_version,
        purpose=body.purpose,
        system_prompt=body.system_prompt,
        user_prompt_template=body.user_prompt_template,
        expected_output_type=body.expected_output_type,
        output_schema_json=body.output_schema_json,
        status=body.status,
    )
    return await svc._templates.get(tpl_id)


@router.get("")
async def list_templates(request: Request):
    svc = request.app.state.llm_service
    return await svc._templates.list_all()


@router.get("/{template_key}")
async def get_template(template_key: str, request: Request):
    svc = request.app.state.llm_service
    tpl = await svc._templates.get_by_key(template_key)
    if not tpl:
        raise HTTPException(status_code=404, detail="template not found")
    return tpl


@router.put("/{tpl_id}")
async def update_template(tpl_id: str, body: TemplateUpdateRequest, request: Request):
    svc = request.app.state.llm_service
    existing = await svc._templates.get(tpl_id)
    if not existing:
        raise HTTPException(status_code=404, detail="template not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await svc._templates.update(tpl_id, **updates)
    return await svc._templates.get(tpl_id)


@router.delete("/{tpl_id}")
async def archive_template(tpl_id: str, request: Request):
    svc = request.app.state.llm_service
    existing = await svc._templates.get(tpl_id)
    if not existing:
        raise HTTPException(status_code=404, detail="template not found")
    await svc._templates.archive(tpl_id)
    return {"id": tpl_id, "status": "archived"}
