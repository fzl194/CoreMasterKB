"""Tests for v1.1 QueryNormalizer."""
import pytest

from agent_serving.serving.application.normalizer import QueryNormalizer
from agent_serving.serving.schemas.constants import (
    INTENT_COMMAND_USAGE,
    INTENT_CONCEPT_LOOKUP,
    INTENT_GENERAL,
    INTENT_PROCEDURE,
    INTENT_TROUBLESHOOT,
)


@pytest.fixture
def normalizer():
    return QueryNormalizer()


class TestCommandDetection:
    def test_add_command(self, normalizer):
        result = normalizer.normalize("ADD APN怎么用")
        assert result.intent == INTENT_COMMAND_USAGE
        assert any(e.type == "command" and "ADD APN" in e.name for e in result.entities)

    def test_show_command(self, normalizer):
        result = normalizer.normalize("SHOW CPU命令参数")
        assert result.intent == INTENT_COMMAND_USAGE
        assert any("SHOW CPU" in e.name for e in result.entities)

    def test_chinese_op_map(self, normalizer):
        result = normalizer.normalize("新增APN")
        assert result.intent == INTENT_COMMAND_USAGE
        assert any("ADD" in e.name for e in result.entities)

    def test_mod_command(self, normalizer):
        result = normalizer.normalize("修改APN的参数")
        assert any(e.type == "command" and "MOD" in e.name for e in result.entities)

    def test_del_command(self, normalizer):
        result = normalizer.normalize("删除APN配置")
        assert any(e.type == "command" and "DEL" in e.name for e in result.entities)

    def test_command_with_product_and_version(self, normalizer):
        result = normalizer.normalize("UDG V100R023C10 ADD APN 怎么写")
        assert result.intent == INTENT_COMMAND_USAGE
        assert any(e.type == "command" and e.name == "ADD APN" for e in result.entities)
        assert "products" in result.scope
        assert "UDG" in result.scope["products"]


class TestIntentDetection:
    def test_troubleshoot(self, normalizer):
        result = normalizer.normalize("CPU过载故障怎么排查")
        assert result.intent == INTENT_TROUBLESHOOT

    def test_concept(self, normalizer):
        result = normalizer.normalize("5G是什么")
        assert result.intent == INTENT_CONCEPT_LOOKUP

    def test_procedure(self, normalizer):
        result = normalizer.normalize("操作步骤流程")
        assert result.intent == INTENT_PROCEDURE

    def test_general(self, normalizer):
        result = normalizer.normalize("网络架构")
        assert result.intent == INTENT_GENERAL


class TestScopeExtraction:
    def test_product_extraction(self, normalizer):
        result = normalizer.normalize("UDG上的ADD APN命令")
        assert "products" in result.scope
        assert "UDG" in result.scope["products"]

    def test_ne_extraction(self, normalizer):
        result = normalizer.normalize("AMF上的配置")
        assert "network_elements" in result.scope
        assert "AMF" in result.scope["network_elements"]

    def test_version_extraction(self, normalizer):
        result = normalizer.normalize("V100R023版本")
        assert "product_versions" in result.scope
        assert "V100R023" in result.scope["product_versions"]

    def test_cloudcore_product(self, normalizer):
        result = normalizer.normalize("CloudCore 5G 概念")
        assert "products" in result.scope
        assert "CLOUDCORE" in result.scope["products"]

    def test_smf_is_ne(self, normalizer):
        result = normalizer.normalize("SMF 配置 S-NSSAI")
        assert "network_elements" in result.scope
        assert "SMF" in result.scope["network_elements"]
        assert "products" not in result.scope or "SMF" not in result.scope.get("products", [])


class TestKeywordExtraction:
    def test_stopwords_filtered(self, normalizer):
        result = normalizer.normalize("什么是5G的原理")
        assert "什么" not in result.keywords
        assert "是" not in result.keywords
        assert len(result.keywords) > 0

    def test_original_query_preserved(self, normalizer):
        result = normalizer.normalize("ADD APN怎么用")
        assert result.original_query == "ADD APN怎么用"


class TestDesiredRoles:
    def test_command_roles(self, normalizer):
        result = normalizer.normalize("ADD APN命令参数")
        assert "parameter" in result.desired_roles

    def test_troubleshoot_roles(self, normalizer):
        result = normalizer.normalize("CPU过载告警怎么排查")
        assert "troubleshooting_step" in result.desired_roles

    def test_general_no_roles(self, normalizer):
        result = normalizer.normalize("网络架构")
        assert result.desired_roles == []
