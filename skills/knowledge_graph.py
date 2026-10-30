import pathlib
import re
import sqlite3

from skills.sandbox import WORKSPACE

KG_DIR = WORKSPACE / ".kg"
KG_DIR.mkdir(parents=True, exist_ok=True)

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _db_path(graph: str) -> pathlib.Path:
    if not _NAME_RE.match(graph):
        raise ValueError(f"invalid graph name '{graph}': use only letters, numbers, _, -")
    return KG_DIR / f"{graph}.db"


def _connect(graph: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(graph))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("CREATE TABLE IF NOT EXISTS entities (name TEXT PRIMARY KEY, entity_type TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS observations ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "entity_name TEXT NOT NULL REFERENCES entities(name) ON DELETE CASCADE, "
        "content TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS relations ("
        "from_entity TEXT NOT NULL, to_entity TEXT NOT NULL, relation_type TEXT NOT NULL, "
        "PRIMARY KEY (from_entity, to_entity, relation_type))"
    )
    return conn


def _format_entity(conn: sqlite3.Connection, name: str, entity_type: str) -> str:
    obs = [r[0] for r in conn.execute("SELECT content FROM observations WHERE entity_name = ?", [name]).fetchall()]
    return "\n".join([f"- {name} ({entity_type})"] + [f"    * {o}" for o in obs])


def kg_create_entities(entities: list[dict], graph: str = "default") -> str:
    """Create one or more entities in the knowledge graph -- people, projects,
    concepts, anything worth remembering as a named thing with facts attached.

    Each entity: {"name": str, "entity_type": str, "observations": list[str] (optional)}.
    Entities that already exist are left alone -- use kg_add_observations to
    append new facts to an existing entity instead of recreating it.
    """
    try:
        with _connect(graph) as conn:
            created = 0
            for e in entities:
                name = e["name"]
                cur = conn.execute(
                    "INSERT OR IGNORE INTO entities (name, entity_type) VALUES (?, ?)",
                    [name, e.get("entity_type", "")],
                )
                created += cur.rowcount
                for obs in e.get("observations", []):
                    dup = conn.execute(
                        "SELECT 1 FROM observations WHERE entity_name = ? AND content = ?", [name, obs]
                    ).fetchone()
                    if not dup:
                        conn.execute("INSERT INTO observations (entity_name, content) VALUES (?, ?)", [name, obs])
    except (sqlite3.Error, ValueError, KeyError) as e:
        return f"error: {e}"
    return f"Created {created} new entit{'y' if created == 1 else 'ies'} (of {len(entities)} requested; existing ones were left as-is)."


def kg_create_relations(relations: list[dict], graph: str = "default") -> str:
    """Create directed relations between existing entities, e.g.
    [{"from_entity": "Justin", "to_entity": "Elastic", "relation_type": "works_at"}].
    """
    try:
        with _connect(graph) as conn:
            count = 0
            for r in relations:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO relations (from_entity, to_entity, relation_type) VALUES (?, ?, ?)",
                    [r["from_entity"], r["to_entity"], r["relation_type"]],
                )
                count += cur.rowcount
    except (sqlite3.Error, ValueError, KeyError) as e:
        return f"error: {e}"
    return f"Created {count} new relation(s)."


def kg_add_observations(entity_name: str, observations: list[str], graph: str = "default") -> str:
    """Add new facts (observations) to an existing entity."""
    try:
        with _connect(graph) as conn:
            if not conn.execute("SELECT 1 FROM entities WHERE name = ?", [entity_name]).fetchone():
                return f"error: no entity named '{entity_name}' -- create it first with kg_create_entities"
            added = 0
            for obs in observations:
                dup = conn.execute(
                    "SELECT 1 FROM observations WHERE entity_name = ? AND content = ?", [entity_name, obs]
                ).fetchone()
                if not dup:
                    conn.execute("INSERT INTO observations (entity_name, content) VALUES (?, ?)", [entity_name, obs])
                    added += 1
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"
    return f"Added {added} new observation(s) to '{entity_name}'."


def kg_delete_entities(entity_names: list[str], graph: str = "default") -> str:
    """Delete entities (and their observations/relations) from the knowledge graph."""
    try:
        with _connect(graph) as conn:
            count = 0
            for name in entity_names:
                cur = conn.execute("DELETE FROM entities WHERE name = ?", [name])
                conn.execute("DELETE FROM relations WHERE from_entity = ? OR to_entity = ?", [name, name])
                count += cur.rowcount
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"
    return f"Deleted {count} entit{'y' if count == 1 else 'ies'}."


def kg_delete_observations(entity_name: str, observations: list[str], graph: str = "default") -> str:
    """Delete specific observations from an entity (the entity itself stays)."""
    try:
        with _connect(graph) as conn:
            count = 0
            for obs in observations:
                cur = conn.execute(
                    "DELETE FROM observations WHERE entity_name = ? AND content = ?", [entity_name, obs]
                )
                count += cur.rowcount
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"
    return f"Deleted {count} observation(s) from '{entity_name}'."


def kg_delete_relations(relations: list[dict], graph: str = "default") -> str:
    """Delete specific relations, e.g. [{"from_entity": "A", "to_entity": "B", "relation_type": "knows"}]."""
    try:
        with _connect(graph) as conn:
            count = 0
            for r in relations:
                cur = conn.execute(
                    "DELETE FROM relations WHERE from_entity = ? AND to_entity = ? AND relation_type = ?",
                    [r["from_entity"], r["to_entity"], r["relation_type"]],
                )
                count += cur.rowcount
    except (sqlite3.Error, ValueError, KeyError) as e:
        return f"error: {e}"
    return f"Deleted {count} relation(s)."


def kg_read_graph(graph: str = "default") -> str:
    """Return the entire knowledge graph: all entities with their observations, and all relations."""
    try:
        with _connect(graph) as conn:
            entities = conn.execute("SELECT name, entity_type FROM entities ORDER BY name").fetchall()
            if not entities:
                return f"Knowledge graph '{graph}' is empty."

            lines = ["Entities:"] + [_format_entity(conn, n, t) for n, t in entities]

            relations = conn.execute(
                "SELECT from_entity, relation_type, to_entity FROM relations ORDER BY from_entity"
            ).fetchall()
            if relations:
                lines.append("\nRelations:")
                lines += [f"- {f} --{rt}--> {t}" for f, rt, t in relations]
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"
    return "\n".join(lines)


def kg_search_nodes(query: str, graph: str = "default") -> str:
    """Search entities by name, type, or observation content (substring match)."""
    like = f"%{query}%"
    try:
        with _connect(graph) as conn:
            names = conn.execute(
                "SELECT DISTINCT e.name, e.entity_type FROM entities e "
                "LEFT JOIN observations o ON o.entity_name = e.name "
                "WHERE e.name LIKE ? OR e.entity_type LIKE ? OR o.content LIKE ? "
                "ORDER BY e.name",
                [like, like, like],
            ).fetchall()
            if not names:
                return f"No entities matching '{query}' in knowledge graph '{graph}'."
            lines = [_format_entity(conn, name, entity_type) for name, entity_type in names]
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"
    return "\n".join(lines)


def kg_open_nodes(entity_names: list[str], graph: str = "default") -> str:
    """Retrieve specific entities (with observations) and the relations between them."""
    try:
        with _connect(graph) as conn:
            lines, found = [], []
            for name in entity_names:
                row = conn.execute("SELECT entity_type FROM entities WHERE name = ?", [name]).fetchone()
                if row:
                    lines.append(_format_entity(conn, name, row[0]))
                    found.append(name)
            if not found:
                return f"None of {entity_names} exist in knowledge graph '{graph}'."

            placeholders = ",".join("?" * len(found))
            relations = conn.execute(
                f"SELECT from_entity, relation_type, to_entity FROM relations "
                f"WHERE from_entity IN ({placeholders}) OR to_entity IN ({placeholders})",
                found * 2,
            ).fetchall()
            if relations:
                lines.append("\nRelations:")
                lines += [f"- {f} --{rt}--> {t}" for f, rt, t in relations]
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"
    return "\n".join(lines)


def register(mcp):
    mcp.tool()(kg_create_entities)
    mcp.tool()(kg_create_relations)
    mcp.tool()(kg_add_observations)
    mcp.tool()(kg_delete_entities)
    mcp.tool()(kg_delete_observations)
    mcp.tool()(kg_delete_relations)
    mcp.tool()(kg_read_graph)
    mcp.tool()(kg_search_nodes)
    mcp.tool()(kg_open_nodes)
