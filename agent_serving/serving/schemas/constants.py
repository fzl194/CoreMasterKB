"""Domain constants — single source of truth for string literals.

All magic strings for intent, relation_type, policy, etc. live here.
Product names, NE types, and version patterns are loaded from config
(normalizer_config module), not hardcoded in business logic.
"""
from __future__ import annotations

# --- Intent types ---
INTENT_COMMAND_USAGE = "command_usage"
INTENT_TROUBLESHOOT = "troubleshooting"
INTENT_CONCEPT_LOOKUP = "concept_lookup"
INTENT_PROCEDURE = "procedure"
INTENT_SOLUTION_EXPLAIN = "solution_explain"
INTENT_PARAMETER_EXPLAIN = "parameter_explain"
INTENT_DEPLOYMENT_GUIDANCE = "deployment_guidance"
INTENT_SOURCE_AUDIT = "source_audit"
INTENT_STRUCTURED_EVIDENCE = "structured_evidence_lookup"
INTENT_SOURCE_DRILLDOWN = "source_drilldown"
INTENT_GENERAL = "general"

# --- Relation types ---
RELATION_PRIMARY = "primary"
RELATION_EXACT_DUPLICATE = "exact_duplicate"
RELATION_NEAR_DUPLICATE = "near_duplicate"
RELATION_NORMALIZED_DUPLICATE = "normalized_duplicate"
RELATION_SCOPE_VARIANT = "scope_variant"
RELATION_CONFLICT_CANDIDATE = "conflict_candidate"

# --- Variant / conflict policies ---
POLICY_FLAG = "flag"
POLICY_REQUIRE_DISAMBIGUATION = "require_disambiguation"
POLICY_FLAG_NOT_ANSWER = "flag_not_answer"
POLICY_NONE = "none"
POLICY_REQUIRE_SCOPE = "require_scope"

# --- Entity types ---
ENTITY_TYPE_COMMAND = "command"
ENTITY_TYPE_FEATURE = "feature"
ENTITY_TYPE_TERM = "term"
ENTITY_TYPE_ALARM = "alarm"
ENTITY_TYPE_NETWORK_ELEMENT = "network_element"
