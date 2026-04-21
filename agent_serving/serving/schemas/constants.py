"""v1.1 Serving constants."""
from __future__ import annotations

# --- Intent types ---
INTENT_COMMAND_USAGE = "command_usage"
INTENT_TROUBLESHOOT = "troubleshooting"
INTENT_CONCEPT_LOOKUP = "concept_lookup"
INTENT_PROCEDURE = "procedure"
INTENT_GENERAL = "general"

# --- Item roles (how an item relates to the query) ---
ROLE_SEED = "seed"
ROLE_CONTEXT = "context"
ROLE_SUPPORT = "support"

# --- Item kinds (what table the item came from) ---
KIND_RETRIEVAL_UNIT = "retrieval_unit"
KIND_RAW_SEGMENT = "raw_segment"

# --- Issue types ---
ISSUE_NO_RESULT = "no_result"
ISSUE_LOW_CONFIDENCE = "low_confidence"
ISSUE_AMBIGUOUS_SCOPE = "ambiguous_scope"
ISSUE_PARTIAL_CONTEXT = "partial_context"
