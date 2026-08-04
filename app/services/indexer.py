from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from app.models.document import DocumentChunk, SearchResult
from app.services.chunker import merge_small_chunks
from app.services.docx_parser import DocxParser


TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9_.$()]+")
INDEX_FORMAT_VERSION = "3"


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


class DocumentIndex:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with closing(self.connect()) as conn:
            conn.executescript(
                """
                create table if not exists metadata (
                    key text primary key,
                    value text not null
                );
                create table if not exists chunks (
                    id integer primary key,
                    document text not null,
                    chapter text,
                    section text,
                    entry_type text not null,
                    entry_name text,
                    content_type text not null,
                    content text not null,
                    paragraph_start integer not null,
                    paragraph_end integer not null,
                    ordinal integer not null,
                    content_hash text,
                    options_json text not null default '[]',
                    functions_json text not null default '[]'
                );
                """
            )
            columns = {row["name"] for row in conn.execute("pragma table_info(chunks)").fetchall()}
            if "options_json" not in columns:
                conn.execute("alter table chunks add column options_json text not null default '[]'")
            if "functions_json" not in columns:
                conn.execute("alter table chunks add column functions_json text not null default '[]'")
            conn.commit()

    def rebuild(self, doc_path: str | Path) -> dict[str, object]:
        doc_path = Path(doc_path)
        self.init()
        chunks = merge_small_chunks(DocxParser().parse(doc_path))
        stat = doc_path.stat()
        with closing(self.connect()) as conn:
            conn.execute("delete from chunks")
            conn.execute("delete from metadata")
            conn.executemany(
                """
                insert into chunks (
                    document, chapter, section, entry_type, entry_name, content_type,
                    content, paragraph_start, paragraph_end, ordinal, content_hash,
                    options_json, functions_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.document, c.chapter, c.section, c.entry_type, c.entry_name, c.content_type,
                        c.content, c.paragraph_start, c.paragraph_end, c.ordinal, c.content_hash,
                        json.dumps(c.options, ensure_ascii=False),
                        json.dumps(c.functions, ensure_ascii=False),
                    )
                    for c in chunks
                ],
            )
            conn.executemany(
                "insert into metadata(key, value) values (?, ?)",
                [
                    ("doc_path", str(doc_path)),
                    ("doc_mtime", str(stat.st_mtime)),
                    ("doc_size", str(stat.st_size)),
                    ("index_format_version", INDEX_FORMAT_VERSION),
                    ("chunk_count", str(len(chunks))),
                ],
            )
            conn.commit()
        return {"chunk_count": len(chunks), "document": doc_path.name}

    def ensure_current(self, doc_path: str | Path) -> None:
        status = self.status(doc_path)
        if not status["indexed"] or status["stale"]:
            self.rebuild(doc_path)

    def status(self, doc_path: str | Path) -> dict[str, object]:
        doc_path = Path(doc_path)
        self.init()
        with closing(self.connect()) as conn:
            rows = conn.execute("select key, value from metadata").fetchall()
            meta = {row["key"]: row["value"] for row in rows}
        indexed = bool(meta)
        stale = True
        if indexed and doc_path.exists():
            stat = doc_path.stat()
            stale = (
                meta.get("doc_mtime") != str(stat.st_mtime)
                or meta.get("doc_size") != str(stat.st_size)
                or meta.get("index_format_version") != INDEX_FORMAT_VERSION
            )
        return {
            "indexed": indexed,
            "stale": stale,
            "chunk_count": int(meta.get("chunk_count", "0")),
            "document": doc_path.name,
            "last_indexed_mtime": meta.get("doc_mtime"),
        }

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        self.init()
        query_tokens = tokenize(query)
        with closing(self.connect()) as conn:
            rows = conn.execute("select * from chunks").fetchall()
        if not rows:
            return []
        documents = [tokenize(row["content"] + " " + (row["entry_name"] or "")) for row in rows]
        df = Counter(token for doc in documents for token in set(doc))
        avg_len = sum(len(doc) for doc in documents) / max(len(documents), 1)
        scored: list[tuple[float, sqlite3.Row]] = []
        for row, doc_tokens in zip(rows, documents):
            counts = Counter(doc_tokens)
            score = 0.0
            for token in query_tokens:
                if counts[token] == 0:
                    continue
                idf = math.log(1 + (len(rows) - df[token] + 0.5) / (df[token] + 0.5))
                denom = counts[token] + 1.2 * (1 - 0.75 + 0.75 * len(doc_tokens) / max(avg_len, 1))
                score += idf * counts[token] * 2.2 / denom
            if row["entry_name"] and row["entry_name"].lower() in query.lower():
                score += 3.0
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            SearchResult(
                entry_name=row["entry_name"],
                section=row["section"],
                score=round(score, 4),
                excerpt=row["content"][:500],
                source=row["document"],
                content_type=row["content_type"],
                options=json.loads(row["options_json"] or "[]"),
                functions=json.loads(row["functions_json"] or "[]"),
            )
            for score, row in scored[:limit]
        ]

    def command_names(self) -> set[str]:
        self.init()
        with closing(self.connect()) as conn:
            rows = conn.execute("select distinct entry_name from chunks where entry_name is not null").fetchall()
        return {row["entry_name"] for row in rows}

    def options_for_entry(self, entry_name: str) -> set[str]:
        self.init()
        with closing(self.connect()) as conn:
            rows = conn.execute(
                "select options_json from chunks where entry_name = ? and content_type = 'syntax'",
                (entry_name,),
            ).fetchall()
            if not rows:
                rows = conn.execute(
                    "select options_json from chunks where entry_name = ?",
                    (entry_name,),
                ).fetchall()
        options: set[str] = set()
        for row in rows:
            options.update(json.loads(row["options_json"] or "[]"))
        return options

    def functions_for_entry(self, entry_name: str | None = None) -> set[str]:
        self.init()
        if entry_name:
            sql = "select functions_json from chunks where entry_name = ?"
            params = (entry_name,)
        else:
            sql = "select functions_json from chunks"
            params = ()
        with closing(self.connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        functions: set[str] = set()
        for row in rows:
            functions.update(json.loads(row["functions_json"] or "[]"))
        return functions

    def dump_json(self) -> str:
        self.init()
        with closing(self.connect()) as conn:
            rows = conn.execute("select * from chunks order by ordinal").fetchall()
        return json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2)
