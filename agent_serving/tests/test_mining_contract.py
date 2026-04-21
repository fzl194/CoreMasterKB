"""Contract tests placeholder — v1.1.

v1.1 contract tests will be enabled once Mining produces v1.1 schema DBs
with the three-layer model (documents → snapshots → builds → releases).
"""
import os
import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_CONTRACT_DB = os.path.join(_REPO_ROOT, "data", "m1_contract_corpus", "m1_contract_asset.sqlite")


@pytest.mark.skip(reason="v1.1 contract tests require Mining v1.1 output DB")
def test_v11_contract_placeholder():
    """Placeholder for v1.1 contract tests."""
    pass
