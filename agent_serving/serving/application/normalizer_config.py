"""Normalizer configuration — externalized domain patterns.

Product names, NE types, version formats, operation mappings, and intent
keywords are loaded from a YAML config file if available, otherwise fall
back to defaults defined here.

To customize without code changes, create a `normalizer_config.yaml` in
the project root or set the NORMALIZER_CONFIG_PATH environment variable.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# --- Default configuration ---

DEFAULT_PRODUCTS: list[str] = ["UDG", "UNC", "CloudCore"]

DEFAULT_NETWORK_ELEMENTS: list[str] = [
    "AMF", "SMF", "UPF", "UDM", "PCF", "NRF",
    "AUSF", "BSF", "NSSF", "SCP", "UDSF", "UDR",
]

DEFAULT_VERSION_PATTERN: str = r"\b(V\d{3}R\d{3}(C\d{2})?)\b"

DEFAULT_OP_MAP: dict[str, str] = {
    "新增": "ADD", "添加": "ADD", "创建": "ADD",
    "修改": "MOD", "更改": "MOD", "编辑": "MOD",
    "删除": "DEL", "移除": "DEL",
    "查询": "SHOW", "查看": "DSP", "显示": "LST",
    "设置": "SET", "配置": "SET",
}

DEFAULT_COMMAND_RE_PATTERN: str = (
    r"\b(ADD|MOD|DEL|SET|SHOW|LST|DSP)\s+([A-Z][A-Z0-9_]*)\b"
)

DEFAULT_INTENT_COMMAND_KEYWORDS: set[str] = {
    "命令", "用法", "参数", "格式", "语法", "怎么写", "如何配置",
}
DEFAULT_INTENT_TROUBLESHOOT_KEYWORDS: set[str] = {
    "故障", "排查", "告警", "错误", "异常", "处理",
}
DEFAULT_INTENT_CONCEPT_KEYWORDS: set[str] = {
    "是什么", "什么是", "概念", "介绍", "概述", "原理",
}
DEFAULT_INTENT_PROCEDURE_KEYWORDS: set[str] = {
    "步骤", "流程", "操作", "怎么做", "如何操作",
}

DEFAULT_INTENT_ROLE_MAP: dict[str, list[str]] = {
    "command_usage": ["parameter", "example", "procedure_step"],
    "troubleshooting": ["troubleshooting_step", "alarm", "constraint"],
    "concept_lookup": ["concept", "note"],
    "procedure": ["procedure_step", "parameter", "example"],
    "comparison": ["concept", "parameter", "constraint"],
    "general": [],
}

# --- Stopwords for keyword filtering ---

DEFAULT_STOPWORDS_ZH: set[str] = {
    "的", "了", "在", "是", "和", "与", "及", "或", "也", "都",
    "这", "那", "有", "没", "不", "会", "能", "要", "可以",
    "什么", "怎么", "如何", "哪些", "为什么", "吗", "呢", "啊",
    "个", "一", "到", "把", "被", "让", "给", "从", "对", "等",
    "请问", "帮我", "告诉", "知道", "想", "应该", "需要",
    "区别", "区别于", "差异", "不同", "区别是什么", "有什么区别",
}
DEFAULT_STOPWORDS_EN: set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "do", "does", "did", "has", "have", "had",
    "and", "or", "but", "not", "no", "in", "on", "at", "to",
    "of", "for", "with", "from", "by", "as",
    "what", "which", "how", "why", "when", "where", "who",
    "this", "that", "these", "those",
    "can", "could", "will", "would", "should", "may", "might",
}

DEFAULT_MIN_KEYWORD_LENGTH: int = 2


def _load_yaml_config() -> dict | None:
    """Load normalizer config from YAML if available."""
    config_path = os.environ.get("NORMALIZER_CONFIG_PATH")
    if not config_path:
        # Try default location
        default_path = Path(__file__).resolve().parent.parent.parent.parent / "normalizer_config.yaml"
        if default_path.exists():
            config_path = str(default_path)

    if not config_path or not os.path.isfile(config_path):
        return None

    try:
        import yaml  # type: ignore[import-untyped]
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return None


def build_product_regex(products: list[str] | None = None) -> re.Pattern[str]:
    """Build product regex from configurable list."""
    names = products or DEFAULT_PRODUCTS
    pattern = r"\b(" + "|".join(re.escape(p) for p in names) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


def build_ne_regex(ne_list: list[str] | None = None) -> re.Pattern[str]:
    """Build network element regex from configurable list."""
    names = ne_list or DEFAULT_NETWORK_ELEMENTS
    pattern = r"\b(" + "|".join(re.escape(n) for n in names) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


def build_version_regex(pattern: str | None = None) -> re.Pattern[str]:
    """Build version regex from configurable pattern."""
    return re.compile(pattern or DEFAULT_VERSION_PATTERN)


def build_command_regex(pattern: str | None = None) -> re.Pattern[str]:
    """Build command regex from configurable pattern."""
    return re.compile(pattern or DEFAULT_COMMAND_RE_PATTERN, re.IGNORECASE)


def load_config() -> dict:
    """Load and merge configuration from YAML + defaults."""
    yaml_config = _load_yaml_config()
    if not yaml_config:
        return {}

    result: dict = {}
    if "products" in yaml_config:
        result["products"] = yaml_config["products"]
    if "network_elements" in yaml_config:
        result["network_elements"] = yaml_config["network_elements"]
    if "version_pattern" in yaml_config:
        result["version_pattern"] = yaml_config["version_pattern"]
    if "op_map" in yaml_config:
        result["op_map"] = yaml_config["op_map"]
    if "intent_keywords" in yaml_config:
        result["intent_keywords"] = yaml_config["intent_keywords"]
    if "intent_role_map" in yaml_config:
        result["intent_role_map"] = yaml_config["intent_role_map"]
    return result
