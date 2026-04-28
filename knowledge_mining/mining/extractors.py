"""Pluggable content understanding interfaces for v1.1 Mining.

Provides lightweight rule-based implementations for semantic_role
and entity_refs extraction. Future: replace with LLM-based classifiers.
"""
from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EntityExtractor(Protocol):
    def extract(self, text: str, context: dict[str, Any]) -> list[dict[str, str]]: ...


@runtime_checkable
class RoleClassifier(Protocol):
    def classify(
        self,
        text: str,
        section_title: str | None,
        block_type: str,
        context: dict[str, Any],
    ) -> str: ...


# --- Lightweight rule-based implementations ---

_NF_PATTERN = re.compile(
    r"\b(SMF|UPF|AMF|PCF|UDM|UDR|AUSF|NRF|NSSF|BSF|CHF|SMSF|LMF|GMLC|NEF|SCF)"
    r"\b",
)

_CMD_PATTERN = re.compile(
    r"\b(ADD|SHOW|MOD|DEL|DSP|LST|REG|DEREG|SET|GET|CFG|ACT|DEACT|CLR|PRT)"
    r"\s+([A-Z][A-Z0-9_]{1,20})",
)

# 3GPP service-based interface reference points: N1-N28, Sx[a|b|c], S1-MME/U, S6a, S11, Gx
# Use lookaround instead of \b — Chinese/Japanese chars are not \w boundaries
_INTERFACE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(N[1-9]\d?|N1[0-9]\d?|N2[0-8]|"
    r"Sx[abc]|S1[ -](?:MME|U)|S6a|S11|Gx)"
    r"(?![A-Za-z0-9_])"
)

# Alarm IDs: ALM-XXXX-XXXX format (Huawei UDG convention)
_ALARM_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(ALM-[A-Z][A-Z0-9_-]{2,40})(?![A-Za-z0-9_-])"
)

_ROLE_RULES: list[tuple[list[str], str]] = [
    (["参数", "参数说明", "参数标识"], "parameter"),
    (["使用实例", "命令格式", "示例", "配置示例"], "example"),
    (["操作步骤", "流程", "检查项", "前置检查", "checklist"], "procedure_step"),
    (["排障", "故障", "troubleshoot"], "troubleshooting_step"),
    (["注意事项", "限制", "约束", "constraint"], "constraint"),
    (["概述", "简介"], "concept"),
]


class RuleBasedEntityExtractor:
    """Lightweight entity extractor: commands and network elements."""

    def extract(self, text: str, context: dict[str, Any]) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        seen: set[str] = set()

        for match in _CMD_PATTERN.finditer(text):
            cmd_name = f"{match.group(1)} {match.group(2)}"
            key = f"command:{cmd_name}"
            if key not in seen:
                seen.add(key)
                refs.append({"type": "command", "name": cmd_name})

        for match in _NF_PATTERN.finditer(text):
            nf_name = match.group(1)
            key = f"network_element:{nf_name}"
            if key not in seen:
                seen.add(key)
                refs.append({"type": "network_element", "name": nf_name})

        structure = context.get("structure") if context else None
        if structure and isinstance(structure, dict):
            columns = structure.get("columns", [])
            if any("参数" in c for c in columns):
                rows = structure.get("rows", [])
                for row in rows:
                    param_name = row.get("参数标识") or row.get("参数名称") or row.get("参数名")
                    if param_name:
                        key = f"parameter:{param_name}"
                        if key not in seen:
                            seen.add(key)
                            refs.append({"type": "parameter", "name": param_name})

        for match in _INTERFACE_PATTERN.finditer(text):
            iface_name = match.group(1)
            key = f"interface:{iface_name}"
            if key not in seen:
                seen.add(key)
                refs.append({"type": "interface", "name": iface_name})

        for match in _ALARM_PATTERN.finditer(text):
            alarm_name = match.group(1)
            key = f"alarm:{alarm_name}"
            if key not in seen:
                seen.add(key)
                refs.append({"type": "alarm", "name": alarm_name})

        return refs


class NoOpEntityExtractor:
    def extract(self, text: str, context: dict[str, Any]) -> list[dict[str, str]]:
        return []


class DefaultRoleClassifier:
    """Lightweight role classifier based on section title keywords."""

    def classify(
        self,
        text: str,
        section_title: str | None,
        block_type: str,
        context: dict[str, Any],
    ) -> str:
        title = (section_title or "").lower()

        for keywords, role in _ROLE_RULES:
            if any(kw.lower() in title for kw in keywords):
                return role

        if block_type == "table":
            structure = context.get("structure") if context else None
            if structure and isinstance(structure, dict):
                columns = structure.get("columns", [])
                if columns and any("参数" in c for c in columns):
                    return "parameter"
            return "note"

        if block_type == "code":
            return "example"

        return "unknown"
