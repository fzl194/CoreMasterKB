"""Integration test: end-to-end pipeline with synthetic Markdown."""
import tempfile
from pathlib import Path

from knowledge_mining.mining.db import MiningDB
from knowledge_mining.mining.jobs.run import run_pipeline


def _write_files(tmp: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        p = tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


SYNTHETIC_DOCS = {
    "cmd_add_apn.md": """# ADD APN

ADD APN命令用于配置APN地址池

## 参数说明

| 参数 | 类型 | 说明 |
|-----|------|------|
| APN名称 | String | APN的名称 |
| 地址池ID | Integer | 地址池标识 |

## 示例

```
ADD APN:APNNAME="internet",POOLID=1;
```
""",
    "cmd_mod_apn.md": """# MOD APN

MOD APN命令用于修改APN配置

## 参数说明

| 参数 | 类型 | 说明 |
|-----|------|------|
| APN名称 | String | APN的名称 |
| 地址池ID | Integer | 地址池标识 |

## 示例

```
MOD APN:APNNAME="internet",POOLID=2;
```
""",
    "feature_overview.md": """# 网络切片特性概述

网络切片是5G核心网的关键技术之一。

## 功能介绍

网络切片允许在同一物理网络上创建多个虚拟网络。

## 注意事项

切片配置需要提前规划好SLA需求。

<table>
<tr><td>参数</td><td>值</td></tr>
<tr><td>最大切片数</td><td>8</td></tr>
</table>
""",
}


def test_pipeline_end_to_end():
    """Full pipeline: ingest → profile → structure → segment → canonicalize → publish."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, SYNTHETIC_DOCS)

        db_path = tmp / "output.sqlite"
        summary = run_pipeline(tmp, db_path)

        assert summary["documents"] == 3
        assert summary["segments"] > 0
        assert summary["canonicals"] > 0
        assert summary["mappings"] > 0

        # Verify canonical count < segment count (dedup happened)
        assert summary["canonicals"] < summary["segments"]

        # Verify SQLite content
        db = MiningDB(db_path)
        conn = db.connect()
        try:
            # Active version
            cursor = conn.execute("SELECT status FROM asset_publish_versions WHERE status = 'active'")
            assert cursor.fetchone() is not None

            # Segments have block_type
            cursor = conn.execute(
                "SELECT DISTINCT block_type FROM asset_raw_segments"
            )
            block_types = {row[0] for row in cursor}
            assert "table" in block_types or "paragraph" in block_types

            # Canonicals exist
            cursor = conn.execute("SELECT count(*) FROM asset_canonical_segments")
            assert cursor.fetchone()[0] > 0

            # Source mappings link canonical to raw
            cursor = conn.execute(
                "SELECT count(*) FROM asset_canonical_segment_sources"
            )
            assert cursor.fetchone()[0] > 0
        finally:
            conn.close()


def test_pipeline_empty_directory():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "empty.sqlite"
        summary = run_pipeline(Path(tmp), db_path)
        assert summary == {"documents": 0, "segments": 0, "canonicals": 0, "mappings": 0}


def test_pipeline_dedup_reduces_count():
    """Identical paragraphs in different docs should deduplicate."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shared_para = "这是一段完全相同的段落文字，出现在多个文档中用于测试去重功能。"
        _write_files(tmp, {
            "a.md": f"# Doc A\n\n{shared_para}",
            "b.md": f"# Doc B\n\n{shared_para}",
        })

        db_path = tmp / "dedup.sqlite"
        summary = run_pipeline(tmp, db_path)

        # 2 docs × at least 1 segment each, but dedup should reduce canonicals
        assert summary["segments"] >= 2
        assert summary["canonicals"] < summary["segments"]
