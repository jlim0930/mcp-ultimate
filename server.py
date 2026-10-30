import importlib
import logging
import os
import pkgutil

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("mcp-ultimate")

mcp = FastMCP(
    "mcp-ultimate",
    host="0.0.0.0",
    port=int(os.environ.get("MCP_PORT", "8088")),
)

import skills  # noqa: E402


def _skill_enabled(module_name: str) -> bool:
    env_name = f"SKILL_{module_name.upper()}_ENABLED"
    return os.environ.get(env_name, "true").strip().lower() not in ("false", "0", "no", "off")


for _, module_name, _ in pkgutil.iter_modules(skills.__path__):
    if module_name in ("config", "search_engines"):
        continue  # shared helper modules, not toggleable skills

    if not _skill_enabled(module_name):
        log.info("skipped skill (disabled via SKILL_%s_ENABLED): %s", module_name.upper(), module_name)
        continue

    module = importlib.import_module(f"skills.{module_name}")
    if hasattr(module, "register"):
        module.register(mcp)
        log.info("loaded skill: %s", module_name)

if __name__ == "__main__":
    import uvicorn
    from starlette.applications import Starlette

    # FastMCP.run() only serves one transport per call. To expose both SSE
    # (/sse) and Streamable HTTP (/mcp) from the same process/port, combine
    # their routes into one Starlette app instead -- this is the pattern the
    # FastMCP.session_manager property's own docstring documents as supported
    # ("exposed to enable advanced use cases like mounting multiple FastMCP
    # servers in a single ... application"). streamable_http_app() must be
    # called at least once to lazily create the session manager before its
    # lifespan can be referenced.
    sse_app = mcp.sse_app()
    streamable_app = mcp.streamable_http_app()

    app = Starlette(
        routes=sse_app.routes + streamable_app.routes,
        lifespan=lambda app: mcp.session_manager.run(),
    )

    log.info("serving SSE at /sse and Streamable HTTP at /mcp")
    uvicorn.run(app, host=mcp.settings.host, port=mcp.settings.port, log_level=mcp.settings.log_level.lower())
