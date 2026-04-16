"""Structure parser: parse Markdown into SectionNode tree with ContentBlocks."""
from __future__ import annotations

from markdown_it import MarkdownIt

from knowledge_mining.mining.models import ContentBlock, SectionNode

_RE_TABLE_TAG = "<table"


def parse_structure(content: str) -> SectionNode:
    """Parse Markdown content into a SectionNode tree."""
    md = MarkdownIt().enable("table")
    tokens = md.parse(content)

    # Step 1: convert tokens to flat block list
    blocks = _tokens_to_blocks(tokens)

    # Step 2: organize into section tree
    return _build_section_tree(blocks)


def _tokens_to_blocks(tokens: list) -> list[ContentBlock]:
    """Convert markdown-it tokens into ContentBlock list."""
    blocks: list[ContentBlock] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "heading_open":
            level = int(tok.tag[1])
            i += 1
            if i < len(tokens) and tokens[i].type == "inline":
                blocks.append(ContentBlock(block_type="heading", text=tokens[i].content, level=level))
            i += 1  # heading_close
        elif tok.type == "table_open":
            parts: list[str] = []
            j = i
            while j < len(tokens):
                if tokens[j].type == "table_close":
                    break
                if tokens[j].type == "inline":
                    parts.append(tokens[j].content)
                j += 1
            blocks.append(ContentBlock(block_type="table", text=" | ".join(parts)))
            i = j + 1
            continue
        elif tok.type in ("fence", "code_block"):
            lang = tok.info.strip() if tok.info else None
            blocks.append(ContentBlock(block_type="code", text=tok.content, language=lang))
        elif tok.type in ("bullet_list_open", "ordered_list_open"):
            list_parts: list[str] = []
            close_type = tok.type.replace("open", "close")
            j = i + 1
            while j < len(tokens):
                if tokens[j].type == close_type:
                    break
                if tokens[j].type == "inline":
                    list_parts.append(tokens[j].content)
                j += 1
            blocks.append(ContentBlock(block_type="list", text="; ".join(list_parts)))
            i = j + 1
            continue
        elif tok.type == "blockquote_open":
            bq_parts: list[str] = []
            j = i + 1
            while j < len(tokens):
                if tokens[j].type == "blockquote_close":
                    break
                if tokens[j].type == "inline":
                    bq_parts.append(tokens[j].content)
                j += 1
            blocks.append(ContentBlock(block_type="blockquote", text=" ".join(bq_parts)))
            i = j + 1
            continue
        elif tok.type == "html_block":
            html_text = tok.content.strip()
            if _RE_TABLE_TAG in html_text.lower():
                blocks.append(ContentBlock(block_type="html_table", text=html_text))
            else:
                blocks.append(ContentBlock(block_type="raw_html", text=html_text))
        elif tok.type == "inline":
            text = tok.content.strip()
            if text:
                blocks.append(ContentBlock(block_type="paragraph", text=text))
        i += 1

    return blocks


def _build_section_tree(blocks: list[ContentBlock]) -> SectionNode:
    """Build section tree from flat block list using heading boundaries."""
    if not blocks:
        return SectionNode(title=None, level=0)

    # Find heading indices
    heading_indices = [i for i, b in enumerate(blocks) if b.block_type == "heading"]

    if not heading_indices:
        # No headings — everything goes into a root section
        return SectionNode(title=None, level=0, blocks=tuple(blocks))

    # First heading is the root
    first_heading = blocks[heading_indices[0]]

    # Pre-heading blocks (before any heading)
    pre_blocks = tuple(blocks[:heading_indices[0]])

    # Split into top-level sections at h1/h2 boundaries
    # For simplicity: collect all sections and make them children of the root
    sections: list[SectionNode] = []
    for si, start_idx in enumerate(heading_indices):
        heading = blocks[start_idx]
        # End at next same-or-higher-level heading, or end of blocks
        end_idx = len(blocks)
        for next_idx in heading_indices[si + 1:]:
            if blocks[next_idx].level is not None and heading.level is not None:
                if blocks[next_idx].level <= heading.level:
                    end_idx = next_idx
                    break
        section_blocks = blocks[start_idx + 1:end_idx]
        sections.append(_make_section(heading, section_blocks))

    return SectionNode(
        title=first_heading.text,
        level=first_heading.level or 1,
        blocks=pre_blocks,
        children=tuple(sections),
    )


def _make_section(heading: ContentBlock, content_blocks: list[ContentBlock]) -> SectionNode:
    """Create a section from a heading and its content blocks."""
    # Check for sub-headings
    sub_heading_indices = [
        i for i, b in enumerate(content_blocks)
        if b.block_type == "heading" and (b.level or 1) > (heading.level or 1)
    ]

    if not sub_heading_indices:
        return SectionNode(
            title=heading.text,
            level=heading.level or 1,
            blocks=tuple(content_blocks),
        )

    # Has sub-sections: split them
    non_heading_blocks: list[ContentBlock] = []
    children: list[SectionNode] = []

    for sub_idx in sub_heading_indices:
        sub_heading = content_blocks[sub_idx]
        # Find end of sub-section
        end = len(content_blocks)
        for later_idx in sub_heading_indices[sub_heading_indices.index(sub_idx) + 1:]:
            if (content_blocks[later_idx].level or 1) <= (sub_heading.level or 1):
                end = later_idx
                break
        sub_content = content_blocks[sub_idx + 1:end]
        children.append(_make_section(sub_heading, sub_content))

    # Collect non-heading, non-sub-heading blocks
    direct_blocks = [
        b for b in content_blocks
        if b.block_type != "heading" or (b.level or 1) <= (heading.level or 1)
    ]
    non_heading_blocks = [b for b in direct_blocks if b.block_type != "heading"]

    return SectionNode(
        title=heading.text,
        level=heading.level or 1,
        blocks=tuple(non_heading_blocks),
        children=tuple(children),
    )
