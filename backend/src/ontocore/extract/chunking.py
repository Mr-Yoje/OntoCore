from ontocore.models import ParsedDocument

SHORT_TEXT_LIMIT = 8000


def section_texts(doc: ParsedDocument) -> list[tuple[str, str]]:
    if not any(block.kind == "heading" for block in doc.blocks):
        if doc.blocks:
            return [("", "\n".join(block.text for block in doc.blocks))]
        return [("", doc.full_text)]

    preamble: list[str] = []
    sections: list[tuple[str, str]] = []
    current_id: str | None = None
    current_parts: list[str] = []

    for block in doc.blocks:
        if block.kind == "heading":
            if current_id is None:
                current_parts.extend(preamble)
                preamble = []
                current_id = block.block_id
                current_parts.append(block.text)
            else:
                sections.append((current_id, "\n".join(current_parts)))
                current_id = block.block_id
                current_parts = [block.text]
        elif current_id is None:
            preamble.append(block.text)
        else:
            current_parts.append(block.text)

    if current_id is not None:
        sections.append((current_id, "\n".join(current_parts)))
    return sections


def extract_texts(doc: ParsedDocument) -> list[tuple[str, str]]:
    if len(doc.full_text) <= SHORT_TEXT_LIMIT:
        first_id = doc.blocks[0].block_id if doc.blocks else ""
        return [(first_id, doc.full_text)]
    return section_texts(doc)
