import json
import os
import pathlib

WORKSPACE = pathlib.Path(os.environ.get("SANDBOX_WORKSPACE", "/workspace")).resolve()
MEMORY_FILE = WORKSPACE / ".memory" / "notes.json"


def _load() -> dict:
    if not MEMORY_FILE.exists():
        return {}
    try:
        return json.loads(MEMORY_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def _save(data: dict) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(data, indent=2, sort_keys=True))


def remember(key: str, value: str) -> str:
    """Store a note under a key, persisted across container restarts."""
    data = _load()
    data[key] = value
    _save(data)
    return f"remembered '{key}'"


def recall(key: str) -> str:
    """Retrieve a previously stored note by key."""
    data = _load()
    return data.get(key, f"no memory found for '{key}'")


def list_memories() -> str:
    """List all stored memory keys with a short preview of each value."""
    data = _load()
    if not data:
        return "(no memories stored)"
    lines = []
    for k, v in sorted(data.items()):
        preview = v if len(v) <= 80 else v[:80] + "..."
        lines.append(f"{k}: {preview}")
    return "\n".join(lines)


def forget(key: str) -> str:
    """Delete a stored note by key."""
    data = _load()
    if key not in data:
        return f"no memory found for '{key}'"
    del data[key]
    _save(data)
    return f"forgot '{key}'"


def register(mcp):
    mcp.tool()(remember)
    mcp.tool()(recall)
    mcp.tool()(list_memories)
    mcp.tool()(forget)
