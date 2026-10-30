import asyncio

from skills.config import GIT_TIMEOUT
from skills.sandbox import WORKSPACE, _safe_path, _truncate


async def _git(args: list[str], cwd) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=GIT_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return f"[timed out after {GIT_TIMEOUT}s]"
    except FileNotFoundError:
        return "error: git is not installed in this image"

    out = stdout.decode(errors="replace")
    err = stderr.decode(errors="replace")
    if proc.returncode != 0:
        return f"error (exit {proc.returncode}): {_truncate(err or out)}"
    return _truncate(out) or "(no output)"


async def git_clone(url: str, path: str = "") -> str:
    """Clone a git repository into the sandbox workspace.

    If path is omitted, git derives the directory name from the URL.
    """
    if path:
        return await _git(["clone", url, str(_safe_path(path))], WORKSPACE)
    return await _git(["clone", url], WORKSPACE)


async def git_status(path: str = ".") -> str:
    """Show git status for a repo in the sandbox workspace."""
    return await _git(["status"], _safe_path(path))


async def git_log(path: str = ".", max_count: int = 10) -> str:
    """Show recent commit history for a repo in the sandbox workspace."""
    return await _git(["log", f"-{max_count}", "--oneline", "--decorate"], _safe_path(path))


async def git_diff(path: str = ".", staged: bool = False) -> str:
    """Show the diff for a repo in the sandbox workspace (working tree by default, or staged changes)."""
    args = ["diff", "--staged"] if staged else ["diff"]
    return await _git(args, _safe_path(path))


async def git_pull(path: str = ".") -> str:
    """Pull the latest changes for a repo in the sandbox workspace."""
    return await _git(["pull"], _safe_path(path))


async def git_add(path: str = ".", files: str = ".") -> str:
    """Stage files (default: all changes) for commit in a repo in the sandbox workspace."""
    return await _git(["add", files], _safe_path(path))


async def git_commit(message: str, path: str = ".") -> str:
    """Commit staged changes in a repo in the sandbox workspace.

    Author/committer identity comes from the GIT_AUTHOR_NAME/EMAIL and
    GIT_COMMITTER_NAME/EMAIL env vars (see .env.example), not hardcoded.
    """
    return await _git(["commit", "-m", message], _safe_path(path))


async def git_branch(path: str = ".") -> str:
    """List local and remote branches for a repo in the sandbox workspace."""
    return await _git(["branch", "-a"], _safe_path(path))


def register(mcp):
    mcp.tool()(git_clone)
    mcp.tool()(git_status)
    mcp.tool()(git_log)
    mcp.tool()(git_diff)
    mcp.tool()(git_pull)
    mcp.tool()(git_add)
    mcp.tool()(git_commit)
    mcp.tool()(git_branch)
