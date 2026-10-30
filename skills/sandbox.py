import asyncio
import os
import pathlib

from skills.config import SANDBOX_MAX_OUTPUT

WORKSPACE = pathlib.Path(os.environ.get("SANDBOX_WORKSPACE", "/workspace")).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)

DEFAULT_TIMEOUT = int(os.environ.get("SANDBOX_CMD_TIMEOUT", "60"))
MAX_OUTPUT = SANDBOX_MAX_OUTPUT  # chars, keeps runaway output from blowing up the response


def _safe_path(path: str) -> pathlib.Path:
    p = pathlib.Path(path)
    p = p.resolve() if p.is_absolute() else (WORKSPACE / p).resolve()
    if p != WORKSPACE and WORKSPACE not in p.parents:
        raise ValueError(f"path escapes sandbox workspace ({WORKSPACE}): {path}")
    return p


def _truncate(text: str) -> str:
    if len(text) > MAX_OUTPUT:
        return text[:MAX_OUTPUT] + f"\n... [truncated, {len(text)} chars total]"
    return text


def register(mcp):
    @mcp.tool()
    async def run_command(command: str, timeout: int = DEFAULT_TIMEOUT) -> str:
        """Run a shell command inside the sandbox container (cwd defaults to the workspace dir).

        This has full shell access within the container's own filesystem/process
        space -- the container itself is the sandbox boundary. There is no
        additional in-container jail, so treat it as trusted-but-contained: no
        access to the host, but full access to whatever is inside this container.
        """
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(WORKSPACE),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return f"[timed out after {timeout}s]"

        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        parts = [f"exit code: {proc.returncode}"]
        if out:
            parts.append("stdout:\n" + _truncate(out))
        if err:
            parts.append("stderr:\n" + _truncate(err))
        return "\n\n".join(parts)

    @mcp.tool()
    def read_file(path: str) -> str:
        """Read a text file from the sandbox workspace."""
        p = _safe_path(path)
        if not p.is_file():
            return f"error: not a file: {path}"
        return _truncate(p.read_text(errors="replace"))

    @mcp.tool()
    def write_file(path: str, content: str, append: bool = False) -> str:
        """Write (or append to) a text file in the sandbox workspace, creating parent dirs as needed."""
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a" if append else "w") as f:
            f.write(content)
        return f"wrote {len(content)} chars to {p.relative_to(WORKSPACE)}"

    @mcp.tool()
    def list_dir(path: str = ".") -> str:
        """List files and directories under a path in the sandbox workspace."""
        p = _safe_path(path)
        if not p.is_dir():
            return f"error: not a directory: {path}"
        entries = [f"{'d' if c.is_dir() else 'f'} {c.name}" for c in sorted(p.iterdir())]
        return "\n".join(entries) or "(empty)"

    @mcp.tool()
    def delete_path(path: str) -> str:
        """Delete a file or empty directory inside the sandbox workspace."""
        p = _safe_path(path)
        if p == WORKSPACE:
            return "error: cannot delete the workspace root"
        if not p.exists():
            return f"error: does not exist: {path}"
        if p.is_dir():
            p.rmdir()
        else:
            p.unlink()
        return f"deleted {path}"
