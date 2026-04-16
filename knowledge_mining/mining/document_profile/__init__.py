"""Document profile module: classify documents by source_type, document_type, scope, tags."""
from __future__ import annotations

import re

from knowledge_mining.mining.models import DocumentProfile, RawDocumentData

_MML_PATTERN = re.compile(r"^(ADD|MOD|DEL|SET|DSP|LST|SHOW)\s+[A-Z0-9_]+", re.MULTILINE)

_DOC_TYPE_KEYWORDS: dict[str, list[str]] = {
    "command": ["命令", "command", "MML"],
    "feature": ["特性概述", "feature", "功能介绍"],
    "procedure": ["操作步骤", "配置步骤", "procedure", "操作流程"],
    "troubleshooting": ["故障处理", "排障", "troubleshooting"],
    "alarm": ["告警", "alarm"],
    "constraint": ["约束", "限制", "constraint"],
}


def build_profile(doc: RawDocumentData) -> DocumentProfile:
    """Build a DocumentProfile from a RawDocumentData."""
    manifest = doc.manifest_meta
    frontmatter = doc.frontmatter

    source_type = _resolve_source_type(manifest, frontmatter)
    document_type = _resolve_document_type(manifest, frontmatter, doc.content)
    scope_json, product, version, ne = _resolve_scope(manifest, frontmatter)
    tags_json = _resolve_tags(manifest, frontmatter)

    return DocumentProfile(
        file_path=doc.file_path,
        source_type=source_type,
        document_type=document_type,
        scope_json=scope_json,
        tags_json=tags_json,
        product=product,
        product_version=version,
        network_element=ne,
        structure_quality=_infer_structure_quality(doc.content),
    )


def _resolve_source_type(manifest: dict, frontmatter: dict) -> str:
    if manifest.get("source_type"):
        return manifest["source_type"]
    if frontmatter.get("source_type"):
        return frontmatter["source_type"]
    return "other"


def _resolve_document_type(manifest: dict, frontmatter: dict, content: str) -> str | None:
    if manifest.get("doc_type"):
        return manifest["doc_type"]
    if frontmatter.get("doc_type"):
        return frontmatter["doc_type"]
    if _MML_PATTERN.search(content):
        return "command"
    for doc_type, keywords in _DOC_TYPE_KEYWORDS.items():
        if doc_type == "command":
            continue
        for kw in keywords:
            if kw in content[:500]:
                return doc_type
    return None


def _resolve_scope(
    manifest: dict, frontmatter: dict,
) -> tuple[dict, str | None, str | None, str | None]:
    scope: dict = {}
    product = frontmatter.get("product") or None
    version = frontmatter.get("product_version") or None
    ne = frontmatter.get("network_element") or None

    nf_list = manifest.get("nf", [])
    if nf_list:
        scope["network_elements"] = nf_list
        if not ne and len(nf_list) == 1:
            ne = nf_list[0]

    if manifest.get("note"):
        scope["note"] = manifest["note"]
    if product:
        scope["product"] = product
    if version:
        scope["version"] = version

    return scope, product, version, ne


def _resolve_tags(manifest: dict, frontmatter: dict) -> list[str]:
    if manifest.get("scenario_tags"):
        return list(manifest["scenario_tags"])
    if frontmatter.get("tags"):
        tags_str = frontmatter["tags"]
        if isinstance(tags_str, str):
            return [t.strip() for t in tags_str.split(",") if t.strip()]
    return []


def _infer_structure_quality(content: str) -> str:
    if "<table" in content:
        return "mixed"
    return "markdown_native"
