import os

import httpx

from skills.config import LOCAL_LLM_TIMEOUT

SHARED_MODEL_OVERRIDE = os.environ.get("LOCAL_LLM_MODEL", "")


def _config():
    return {
        "lmstudio": {
            "url": os.environ.get("LMSTUDIO_URL", "http://host.docker.internal:1234/v1").rstrip("/"),
            "api_key": os.environ.get("LMSTUDIO_API_KEY", ""),
            "model_override": os.environ.get("LMSTUDIO_MODEL", "") or SHARED_MODEL_OVERRIDE,
        },
        "mlx": {
            "url": os.environ.get("MLX_URL", "http://host.docker.internal:8080/v1").rstrip("/"),
            "api_key": os.environ.get("MLX_API_KEY", ""),
            "model_override": os.environ.get("MLX_MODEL", "") or SHARED_MODEL_OVERRIDE,
        },
    }


def _headers(api_key: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def _resolve_model(client: httpx.AsyncClient, base_url: str, headers: dict, model_override: str) -> str:
    if model_override:
        return model_override
    try:
        resp = await client.get(f"{base_url}/models", headers=headers)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        if models:
            return models[0]["id"]
    except Exception:
        pass
    return "local-model"


async def _call_backend(name, cfg, prompt, system, max_tokens, temperature) -> str:
    headers = _headers(cfg["api_key"])
    async with httpx.AsyncClient(timeout=LOCAL_LLM_TIMEOUT) as client:
        model = await _resolve_model(client, cfg["url"], headers, cfg["model_override"])
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = await client.post(
            f"{cfg['url']}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    return f"[{name} / {model}]\n{content}"


async def ask_local_llm(
    prompt: str,
    system: str = "",
    backend: str = "auto",
    max_tokens: int = 512,
    temperature: float = 0.7,
) -> str:
    """Ask your own local LLM (LM Studio and/or MLX server) via its OpenAI-compatible API.

    backend: "auto" (try lmstudio, then mlx), "lmstudio", or "mlx".

    Endpoints and optional API keys are configured via env vars (see .env.example),
    not hardcoded: LMSTUDIO_URL/LMSTUDIO_API_KEY and MLX_URL/MLX_API_KEY. Both
    default to host.docker.internal, which reaches servers running on the
    Docker host's Mac (e.g. via lmstudio_server.sh / mlx_server.sh) from inside
    this container. LMSTUDIO_MODEL/MLX_MODEL pin a model id per backend (they
    use different id formats -- e.g. MLX's mlx-community/Qwen3-30B-A3B-4bit vs
    LM Studio's own catalog names); LOCAL_LLM_MODEL is a shared fallback for
    both if you only ever run one model at a time. Leave all three unset to
    auto-detect from whichever model the backend's /models endpoint reports.
    """
    cfg = _config()
    order = {"auto": ["lmstudio", "mlx"], "lmstudio": ["lmstudio"], "mlx": ["mlx"]}.get(
        backend, ["lmstudio", "mlx"]
    )

    errors = []
    for name in order:
        try:
            return await _call_backend(name, cfg[name], prompt, system, max_tokens, temperature)
        except Exception as e:
            errors.append(f"{name} ({cfg[name]['url']}): {e}")

    return (
        "error: no local LLM backend reachable.\n"
        + "\n".join(errors)
        + "\n\nStart one on the host with lmstudio_server.sh or mlx_server.sh."
    )


def register(mcp):
    mcp.tool()(ask_local_llm)
