"""Live E2E test: real LLM calls through the full mining pipeline.

Requires llm_service running at localhost:8900 with valid provider API key.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from knowledge_mining.mining.jobs.run import run


# Real APN document content for testing
_APN_DOC = """# APN配置指南

## 概述

APN（Access Point Name）是移动通信网络中的重要参数，用于标识分组数据网络。终端设备通过APN来选择对应的网关和外部网络。

APN由两部分组成：
- 网络标识：标识外部网络
- 运营商标识：标识归属运营商

## 配置步骤

### 1. 创建APN配置

使用 `ADD APN` 命令创建新的APN配置。命令格式如下：

```
ADD APN: APNNAME="cmnet", AUTHTYPE=PAP, USERNAME="user1", PASSWORD="pass123";
```

参数说明：
- APNNAME：接入点名称，必填参数
- AUTHTYPE：认证方式，支持PAP和CHAP
- USERNAME：认证用户名
- PASSWORD：认证密码

### 2. 修改APN配置

使用 `MOD APN` 命令修改已有的APN配置：

```
MOD APN: APNNAME="cmnet", AUTHTYPE=CHAP;
```

### 3. 查询APN配置

使用 `LST APN` 命令查询APN配置信息：

```
LST APN: APNNAME="cmnet";
```

查询结果包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| APNNAME | String | 接入点名称 |
| AUTHTYPE | Enum | 认证方式 |
| USERNAME | String | 认证用户名 |
| STATUS | Enum | 当前状态 |

## APN参数详解

APN配置涉及多个关键参数，这些参数直接影响终端的数据业务接入能力。正确配置APN是保障移动数据业务正常运行的前提条件。

认证方式PAP和CHAP的区别：
- PAP：密码明文传输，安全性较低
- CHAP：密码加密传输，安全性较高

## 常见问题排查

### 问题1：APN配置后无法接入

可能原因：
1. APNNAME拼写错误
2. 认证参数不匹配
3. 网关未配置对应APN

解决步骤：
1. 使用 `LST APN` 检查配置
2. 对比运营商提供的APN参数
3. 检查网关侧配置

### 问题2：CHAP认证失败

可能原因：
1. 共享密钥不一致
2. 用户名密码错误
3. 认证服务器不可达

解决步骤：
1. 确认共享密钥配置
2. 使用测试命令验证认证
3. 检查网络连通性
"""


def _create_test_docs(tmpdir: str) -> str:
    """Create test document directory with APN doc."""
    docs_dir = Path(tmpdir) / "docs"
    docs_dir.mkdir()
    (docs_dir / "apn_config.md").write_text(_APN_DOC, encoding="utf-8")
    return str(docs_dir)


def test_e2e_live_pipeline():
    """Full E2E: ingest -> parse -> segment -> enrich -> relations -> retrieval units -> build.

    Uses real LLM service for question generation.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = _create_test_docs(tmpdir)
        asset_db_path = os.path.join(tmpdir, "asset_core.sqlite")
        runtime_db_path = os.path.join(tmpdir, "mining_runtime.sqlite")

        # Use a custom _init_llm that only creates question_generator
        # (enricher/discourse/contextualizer submit too many tasks for 4 workers)
        from knowledge_mining.mining.jobs import run as run_module
        original_init_llm = run_module._init_llm

        def _init_llm_questions_only(llm_base_url, bypass_proxy=False):
            """Only create question generator, skip enricher/discourse/contextualizer."""
            if not llm_base_url:
                return None
            from knowledge_mining.mining.llm_client import LlmClient
            from knowledge_mining.mining.llm_templates import TEMPLATES
            from knowledge_mining.mining.retrieval_units import LlmQuestionGenerator

            client = LlmClient(base_url=llm_base_url, bypass_proxy=bypass_proxy)
            if not client.health_check():
                return None
            for tpl in TEMPLATES:
                client.register_template(tpl)
            return {
                "question_generator": LlmQuestionGenerator(base_url=llm_base_url, bypass_proxy=bypass_proxy),
            }

        # Monkey-patch for this test
        run_module._init_llm = _init_llm_questions_only

        try:
            result = run(
                docs_dir,
                asset_core_db_path=asset_db_path,
                mining_runtime_db_path=runtime_db_path,
                llm_base_url="http://localhost:8900",
            )
        finally:
            run_module._init_llm = original_init_llm

        print("\n" + "=" * 60)
        print("E2E Pipeline Result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("=" * 60)

        # Basic assertions
        assert result["status"] == "completed", f"Expected completed, got {result['status']}"
        assert result["committed_count"] >= 1, "Should have committed at least 1 document"
        assert result["build_id"] is not None, "Should have created a build"

        # Check database contents
        from knowledge_mining.mining.db import AssetCoreDB
        db = AssetCoreDB(asset_db_path)
        db.open()

        # Check segments
        build = db.get_build(result["build_id"])
        assert build is not None

        snapshots = db.get_build_snapshots(result["build_id"])
        active_snaps = [s for s in snapshots if s["selection_status"] == "active"]
        assert len(active_snaps) >= 1

        snap_id = active_snaps[0]["document_snapshot_id"]
        segments = db.get_segments_by_snapshot(snap_id)
        print(f"\nSegments: {len(segments)}")

        relations = db.get_relations_by_snapshot(snap_id)
        print(f"Relations: {len(relations)}")

        units = db.get_retrieval_units_by_snapshot(snap_id)
        print(f"Retrieval units: {len(units)}")

        # Check unit types
        unit_types = {}
        for u in units:
            unit_types[u["unit_type"]] = unit_types.get(u["unit_type"], 0) + 1
        print(f"Unit type breakdown: {json.dumps(unit_types, ensure_ascii=False)}")

        # Print some sample retrieval units
        for u in units[:5]:
            print(f"\n  [{u['unit_type']}] {u['title']}")
            print(f"    text: {u['text'][:120]}...")

        # Check for generated questions (LLM-driven)
        gen_q_units = [u for u in units if u["unit_type"] == "generated_question"]
        print(f"\nGenerated questions (LLM): {len(gen_q_units)}")
        for q in gen_q_units[:3]:
            print(f"  Q: {q['title']}")

        db.close()

        # Verify all counts
        assert len(segments) > 5, "Should have multiple segments"
        assert len(relations) > 0, "Should have relations"
        assert len(units) > 5, "Should have retrieval units"
        assert len(gen_q_units) > 0, "Should have LLM-generated questions"


if __name__ == "__main__":
    test_e2e_live_pipeline()
    print("\nE2E test passed!")
