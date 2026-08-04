from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    document: str
    chapter: str | None = None
    section: str | None = None
    entry_type: str = "text"
    entry_name: str | None = None
    content_type: str = "description"
    content: str
    paragraph_start: int
    paragraph_end: int
    ordinal: int
    content_hash: str | None = None
    options: list[str] = []
    functions: list[str] = []


class SearchResult(BaseModel):
    entry_name: str | None
    section: str | None
    score: float = Field(ge=0)
    excerpt: str
    source: str
    content_type: str
    options: list[str] = []
    functions: list[str] = []
