import asyncio
import sys

from skills.config import PYTHON_TIMEOUT
from skills.sandbox import WORKSPACE, _safe_path, _truncate


async def _run(args: list[str], cwd, timeout: int) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "", f"[timed out after {timeout}s]"
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def run_python(code: str, timeout: int = PYTHON_TIMEOUT) -> str:
    """Run a Python snippet in the sandbox workspace and return stdout/stderr/exit code.

    Runs as its own subprocess (python3 -c), isolated from the MCP server's own
    process -- not a shared REPL, no state persists between calls. For anything
    that needs installed packages or files, use the sandbox workspace via
    write_file first, or run_command for pip install (note: packages installed
    this way don't survive a container rebuild -- only /workspace persists).
    """
    code_exit, out, err = await _run([sys.executable, "-c", code], WORKSPACE, timeout)
    parts = [f"exit code: {code_exit}"]
    if out:
        parts.append("stdout:\n" + _truncate(out))
    if err:
        parts.append("stderr:\n" + _truncate(err))
    return "\n\n".join(parts)


async def lint_python(path: str = ".") -> str:
    """Lint Python files under a path in the sandbox workspace with ruff."""
    _, out, err = await _run(["ruff", "check", str(_safe_path(path))], WORKSPACE, PYTHON_TIMEOUT)
    return _truncate(out or err or "(no issues found)")


async def format_python(path: str = ".", check: bool = True) -> str:
    """Format Python files under a path in the sandbox workspace with ruff.

    check=True (default) only reports what would change, without modifying
    files. check=False applies the formatting in place.
    """
    args = ["ruff", "format"]
    args += ["--diff"] if check else []
    args.append(str(_safe_path(path)))
    _, out, err = await _run(args, WORKSPACE, PYTHON_TIMEOUT)
    return _truncate(out or err or "(no changes)")


def register(mcp):
    mcp.tool()(run_python)
    mcp.tool()(lint_python)
    mcp.tool()(format_python)
