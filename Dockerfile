FROM python:3.12-slim

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps --only-shell chromium \
    && apt-get install -y --no-install-recommends git \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

COPY server.py .
COPY skills/ ./skills/

RUN useradd -m -u 1000 mcp && mkdir -p /workspace && chown -R mcp:mcp /app /workspace
USER mcp

ENV PYTHONUNBUFFERED=1 \
    MCP_PORT=8088 \
    SEARXNG_URL=http://192.168.1.20:8080 \
    SANDBOX_WORKSPACE=/workspace \
    SANDBOX_CMD_TIMEOUT=60 \
    GIT_AUTHOR_NAME=mcp-ultimate \
    GIT_AUTHOR_EMAIL=mcp-ultimate@localhost \
    GIT_COMMITTER_NAME=mcp-ultimate \
    GIT_COMMITTER_EMAIL=mcp-ultimate@localhost

EXPOSE 8088

CMD ["python", "server.py"]
