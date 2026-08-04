from app.models.document import DocumentChunk


def merge_small_chunks(chunks: list[DocumentChunk], min_chars: int = 500) -> list[DocumentChunk]:
    merged: list[DocumentChunk] = []
    pending: DocumentChunk | None = None
    for chunk in chunks:
        if chunk.entry_name or len(chunk.content) >= min_chars:
            if pending:
                merged.append(pending)
                pending = None
            merged.append(chunk)
            continue
        if pending is None:
            pending = chunk
        else:
            pending.content = f"{pending.content}\n{chunk.content}"
            pending.paragraph_end = chunk.paragraph_end
    if pending:
        merged.append(pending)
    for index, chunk in enumerate(merged):
        chunk.ordinal = index
    return merged

