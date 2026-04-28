"""LLM template definitions for Mining v1.3.

Templates must be pre-registered with llm_service before use.
"""
from __future__ import annotations

import json
from typing import Any

# ---------- Schema definitions (JSON Schema, provider-agnostic) ----------

_QUESTION_GEN_SCHEMA = json.dumps({
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
        },
        "required": ["question"],
        "additionalProperties": False,
    },
})

_SEGMENT_UNDERSTANDING_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "command", "network_element", "parameter",
                            "protocol", "interface", "alarm", "feature", "concept",
                        ],
                    },
                    "name": {"type": "string"},
                },
                "required": ["type", "name"],
                "additionalProperties": False,
            },
        },
        "semantic_role": {"type": "string"},
        "document_type": {"type": "string"},
    },
    "required": ["entities", "semantic_role", "document_type"],
    "additionalProperties": False,
})

_DISCOURSE_RELATION_SCHEMA = json.dumps({
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "source": {"type": "integer"},
            "target": {"type": "integer"},
            "relation": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["source", "target", "relation", "confidence"],
        "additionalProperties": False,
    },
})

_CONTEXTUAL_RETRIEVAL_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "context": {"type": "string"},
    },
    "required": ["context"],
    "additionalProperties": False,
})

# ---------- Template list ----------

TEMPLATES: list[dict[str, Any]] = [
    {
        "template_key": "mining-question-gen",
        "template_version": "2",
        "purpose": "从段落内容生成假设性检索问题",
        "system_prompt": "你是通信网络知识库的检索优化助手。",
        "user_prompt_template": (
            "根据以下技术文档段落，生成 1-2 个用户可能提出的问题。\n\n"
            "段落标题：$title\n段落内容：$content\n\n"
            "要求：\n"
            "- 问题必须能从该段落中找到明确答案\n"
            "- 避免生成高度相似或近义的问题\n"
            "- 如果段落内容过于简短，生成 0-1 个即可\n\n"
            "输出 JSON 数组，每个元素包含 question 字段。"
        ),
        "expected_output_type": "json_array",
        "output_schema_json": _QUESTION_GEN_SCHEMA,
    },
    {
        "template_key": "mining-segment-understanding",
        "template_version": "2",
        "purpose": "从段落提取实体并分类语义角色",
        "system_prompt": "你是通信网络知识库的内容理解助手。分析技术文档段落，提取关键实体并分类语义角色。",
        "user_prompt_template": (
            "分析以下技术文档段落：\n\n"
            "段落标题：$section_title\n"
            "内容类型：$block_type\n"
            "段落内容：$text\n\n"
            "输出 JSON 对象，包含：\n"
            "- entities: 实体列表，每个元素包含 type 和 name\n"
            "  type 可选值：command / network_element / parameter / protocol / interface / alarm / feature / concept\n\n"
            "质量指引：\n"
            "- 只提取文档中明确出现、有专有名称的技术实体\n"
            "- 接口（如N4、Sxb）和协议（如PFCP、HTTP）是不同类型：接口是3GPP定义的参考点，协议是通信规范\n"
            "- 告警ID（如ALM-XXX-XXX）归为alarm类型\n"
            "- 产品特性编码（如GWFD-XXXXXX）和子特性（如SA-HTTP Pipeline）归为feature类型\n"
            "- 如果无法确定实体类型，不要强行分类\n\n"
            "- semantic_role: 语义角色（concept/parameter/example/note/procedure_step/troubleshooting_step/constraint/alarm/checklist/unknown）\n"
            "- document_type: 文档类型提示（command/feature/procedure/troubleshooting/alarm/constraint/checklist/reference/other）"
        ),
        "expected_output_type": "json_object",
        "output_schema_json": _SEGMENT_UNDERSTANDING_SCHEMA,
    },
    {
        "template_key": "mining-discourse-relation",
        "template_version": "1",
        "purpose": "分析段落间的语篇关系（RST修辞结构理论）",
        "system_prompt": "你是通信网络技术文档的语篇关系分析专家。分析给定段落列表中相邻段落之间的修辞关系。",
        "user_prompt_template": (
            "分析以下编号段落之间的语篇关系：\n\n"
            "$segments\n\n"
            "对每对相邻或同节段落，判断其修辞关系。可选关系类型：\n"
            "- ELABORATES: 后文详细阐述前文\n"
            "- EVIDENCES: 后文提供证据支持前文\n"
            "- CAUSES: 后文是前文的原因\n"
            "- RESULTS_IN: 后文是前文的结果\n"
            "- BACKGROUNDS: 后文提供背景信息\n"
            "- CONDITIONS: 后文说明前提条件\n"
            "- SUMMARIZES: 后文总结前文\n"
            "- JUSTIFIES: 后文解释前文的理由\n"
            "- ENABLES: 后文使前文的操作成为可能\n"
            "- CONTRASTS_WITH: 后文与前文对比\n"
            "- PARALLELS: 后文与前文并列\n"
            "- SEQUENCES: 后文是前文的后续步骤\n"
            "- UNRELATED: 无明显关系\n\n"
            "输出 JSON 数组，每个元素包含：\n"
            "- source: 源段落编号（整数）\n"
            "- target: 目标段落编号（整数）\n"
            "- relation: 关系类型（大写）\n"
            "- confidence: 置信度（0.0-1.0）\n\n"
            "只输出有明确关系的段落对，跳过 UNRELATED 的。"
        ),
        "expected_output_type": "json_array",
        "output_schema_json": _DISCOURSE_RELATION_SCHEMA,
    },
    {
        "template_key": "mining-contextual-retrieval",
        "template_version": "2",
        "purpose": "为每个段落生成上下文描述，增强检索效果",
        "system_prompt": "你是通信网络技术文档的检索上下文定位助手。",
        "user_prompt_template": (
            "文档全文：\n$document\n\n"
            "段落内容：\n$segment\n\n"
            "请生成一句 20-40 字的中文上下文标签，说明该段落在文档中的位置和主题。\n"
            "不要复述段落内容，只补充从段落文本中无法直接看出的上下文信息（如所属章节、讨论主题等）。\n"
            "输出 JSON 对象，包含 context 字段。"
        ),
        "expected_output_type": "json_object",
        "output_schema_json": _CONTEXTUAL_RETRIEVAL_SCHEMA,
    },
]
