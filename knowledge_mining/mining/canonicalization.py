"""Canonicalization module: three-layer dedup to produce L1 canonical + L2 source mapping."""
from __future__ import annotations

from knowledge_mining.mining.models import (
    CanonicalSegmentData,
    DocumentProfile,
    RawSegmentData,
    SourceMappingData,
)
from knowledge_mining.mining.text_utils import (
    content_hash,
    hamming_distance,
    jaccard_similarity,
    normalized_hash,
    simhash_fingerprint,
)

# Dedup thresholds
_SIMHASH_THRESHOLD = 3
_JACCARD_THRESHOLD = 0.85


def canonicalize(
    segments: list[RawSegmentData],
    profiles: dict[str, DocumentProfile],
) -> tuple[list[CanonicalSegmentData], list[SourceMappingData]]:
    """Three-layer dedup: exact → normalized → simhash+Jaccard.

    Returns (canonical_segments, source_mappings).
    """
    if not segments:
        return [], []

    canonicals: list[CanonicalSegmentData] = []
    mappings: list[SourceMappingData] = []

    # Track which segments have been assigned to a canonical
    assigned: set[str] = set()
    canonical_idx = 0

    # Layer 1: exact duplicates (content_hash)
    hash_groups: dict[str, list[RawSegmentData]] = {}
    for seg in segments:
        key = seg.content_hash
        hash_groups.setdefault(key, []).append(seg)

    for hash_key, group in hash_groups.items():
        canonical, group_mappings = _create_canonical_group(
            group, profiles, f"c{canonical_idx:06d}"
        )
        canonical_idx += 1
        canonicals.append(canonical)
        mappings.extend(group_mappings)
        for seg in group:
            assigned.add(f"{seg.document_file_path}#{seg.segment_index}")

    # Layer 2: normalized duplicates
    norm_groups: dict[str, list[RawSegmentData]] = {}
    for seg in segments:
        seg_key = f"{seg.document_file_path}#{seg.segment_index}"
        if seg_key in assigned:
            continue
        norm_groups.setdefault(seg.normalized_hash, []).append(seg)

    for norm_key, group in norm_groups.items():
        if len(group) < 2:
            continue
        canonical, group_mappings = _create_canonical_group(
            group, profiles, f"c{canonical_idx:06d}"
        )
        canonical_idx += 1
        canonicals.append(canonical)
        mappings.extend(group_mappings)
        for seg in group:
            assigned.add(f"{seg.document_file_path}#{seg.segment_index}")

    # Layer 3: near duplicates (simhash + Jaccard)
    remaining = [
        seg for seg in segments
        if f"{seg.document_file_path}#{seg.segment_index}" not in assigned
    ]

    i = 0
    while i < len(remaining):
        seg = remaining[i]
        group = [seg]
        j = i + 1
        while j < len(remaining):
            other = remaining[j]
            fp1 = simhash_fingerprint(seg.raw_text)
            fp2 = simhash_fingerprint(other.raw_text)
            if (hamming_distance(fp1, fp2) <= _SIMHASH_THRESHOLD
                    and jaccard_similarity(seg.raw_text, other.raw_text) >= _JACCARD_THRESHOLD):
                group.append(other)
                remaining.pop(j)
            else:
                j += 1
        canonical, group_mappings = _create_canonical_group(
            group, profiles, f"c{canonical_idx:06d}"
        )
        canonical_idx += 1
        canonicals.append(canonical)
        mappings.extend(group_mappings)
        i += 1

    return canonicals, mappings


def _create_canonical_group(
    group: list[RawSegmentData],
    profiles: dict[str, DocumentProfile],
    canonical_key: str,
) -> tuple[CanonicalSegmentData, list[SourceMappingData]]:
    """Create a canonical segment from a group of raw segments."""
    primary = group[0]
    has_variants = False
    variant_policy = "none"
    relations: list[SourceMappingData] = []

    # Check for scope variants
    for i, seg in enumerate(group):
        if i == 0:
            relations.append(SourceMappingData(
                canonical_key=canonical_key,
                raw_segment_ref=f"{seg.document_file_path}#{seg.segment_index}",
                relation_type="primary",
            ))
            continue

        profile = profiles.get(seg.document_file_path)
        primary_profile = profiles.get(primary.document_file_path)

        rel_type = "near_duplicate"
        if profile and primary_profile:
            if profile.product and primary_profile.product and profile.product != primary_profile.product:
                rel_type = "product_variant"
                has_variants = True
                variant_policy = "require_product_version"
            elif profile.product_version and primary_profile.product_version and profile.product_version != primary_profile.product_version:
                rel_type = "version_variant"
                has_variants = True
                variant_policy = "prefer_latest"
            elif profile.network_element and primary_profile.network_element and profile.network_element != primary_profile.network_element:
                rel_type = "ne_variant"
                has_variants = True

        # Check if exact or near
        if seg.content_hash == primary.content_hash and rel_type == "near_duplicate":
            rel_type = "exact_duplicate"

        relations.append(SourceMappingData(
            canonical_key=canonical_key,
            raw_segment_ref=f"{seg.document_file_path}#{seg.segment_index}",
            relation_type=rel_type,
        ))

    return CanonicalSegmentData(
        canonical_key=canonical_key,
        segment_type=primary.segment_type,
        section_role=primary.section_role,
        title=primary.section_title,
        canonical_text=primary.raw_text,
        search_text=primary.raw_text.lower(),
        has_variants=has_variants,
        variant_policy=variant_policy,
        command_name=primary.command_name,
        raw_segment_refs=[r.raw_segment_ref for r in relations],
    ), relations
