import io
import re
from urllib.parse import parse_qs, urlparse

import httpx
from pypdf import PdfReader
from youtube_transcript_api import YouTubeTranscriptApi

from skills.config import HTTP_TIMEOUT, random_headers
from skills.sandbox import _safe_path


def _extract_youtube_id(video: str) -> str:
    video = video.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
        return video

    parsed = urlparse(video)
    if parsed.hostname == "youtu.be":
        return parsed.path.lstrip("/")
    if parsed.hostname and "youtube.com" in parsed.hostname:
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            if "v" in qs:
                return qs["v"][0]
        for prefix in ("/embed/", "/shorts/", "/live/"):
            if parsed.path.startswith(prefix):
                return parsed.path[len(prefix) :].split("/")[0]

    raise ValueError(f"could not extract a YouTube video ID from: {video}")


async def read_pdf(source: str, max_chars: int = 8000) -> str:
    """Extract text from a PDF. source can be a URL or a path in the sandbox workspace."""
    if source.startswith("http://") or source.startswith("https://"):
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(source, headers=random_headers())
            resp.raise_for_status()
            data = resp.content
    else:
        path = _safe_path(source)
        if not path.is_file():
            return f"error: not a file: {source}"
        data = path.read_bytes()

    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as e:
        return f"error: could not parse PDF ({e})"

    if len(text) > max_chars:
        text = text[:max_chars] + f"... [truncated, {len(text)} chars total, {len(reader.pages)} pages]"
    return text or "(no extractable text found -- this may be a scanned/image-only PDF)"


async def get_youtube_transcript(video: str, max_chars: int = 8000) -> str:
    """Get the transcript of a YouTube video. Accepts a full URL or a bare video ID."""
    try:
        video_id = _extract_youtube_id(video)
    except ValueError as e:
        return f"error: {e}"

    try:
        transcript = YouTubeTranscriptApi().fetch(video_id)
    except Exception as e:
        return f"error: could not fetch transcript for {video_id} ({e})"

    text = " ".join(snippet.text for snippet in transcript.snippets)
    text = " ".join(text.split())
    if len(text) > max_chars:
        text = text[:max_chars] + f"... [truncated, {len(text)} chars total]"
    return text or "(empty transcript)"


def register(mcp):
    mcp.tool()(read_pdf)
    mcp.tool()(get_youtube_transcript)
