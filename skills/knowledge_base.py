import re
import sqlite3

from skills.sandbox import WORKSPACE
from skills.utils import fetch_url

KB_DIR = WORKSPACE / ".kb"
KB_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 800
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _db_path(name: str):
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid knowledge base name '{name}': use only letters, numbers, _, -")
    return KB_DIR / f"{name}.db"


def _connect(name: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(name))
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(url, chunk_index UNINDEXED, content)")
    return conn


def _chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    words = text.split()
    chunks, current, current_len = [], [], 0
    for w in words:
        current.append(w)
        current_len += len(w) + 1
        if current_len >= size:
            chunks.append(" ".join(current))
            current, current_len = [], 0
    if current:
        chunks.append(" ".join(current))
    return chunks


async def kb_index(url: str, name: str = "default") -> str:
    """Fetch a URL and index its text into a searchable local knowledge base
    (SQLite full-text search) for later kb_search calls, instead of
    re-fetching or re-pasting the same large page repeatedly. Re-indexing the
    same URL replaces its previous chunks.
    """
    try:
        text = await fetch_url(url, max_chars=100_000)
    except Exception as e:
        return f"error fetching {url}: {e}"

    chunks = _chunk_text(text)
    if not chunks:
        return f"Nothing to index from {url}."

    try:
        with _connect(name) as conn:
            conn.execute("DELETE FROM chunks WHERE url = ?", [url])
            conn.executemany(
                "INSERT INTO chunks (url, chunk_index, content) VALUES (?, ?, ?)",
                [(url, i, c) for i, c in enumerate(chunks)],
            )
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"

    return f"Indexed {len(chunks)} chunk(s) from {url} into knowledge base '{name}'."


def kb_search(query: str, name: str = "default", max_results: int = 5) -> str:
    """Full-text search (BM25-ranked) a knowledge base previously built with kb_index.

    Multiple words in `query` are ANDed (all must appear) with no stemming --
    "coroutine" won't match text that only contains "coroutines". Prefer a
    few simple terms over a long phrase; retry with fewer/different words if
    a search comes back empty rather than assuming the content isn't indexed.
    """
    try:
        with _connect(name) as conn:
            rows = conn.execute(
                "SELECT url, chunk_index, content FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
                [query, max_results],
            ).fetchall()
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"

    if not rows:
        return f"No matches for '{query}' in knowledge base '{name}'."

    lines = []
    for i, (url, chunk_index, content) in enumerate(rows, 1):
        preview = content if len(content) <= 500 else content[:500] + "..."
        lines.append(f"{i}. [{url} #chunk {chunk_index}]\n   {preview}")
    return "\n\n".join(lines)


def register(mcp):
    mcp.tool()(kb_index)
    mcp.tool()(kb_search)
