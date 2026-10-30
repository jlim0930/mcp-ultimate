import os

import httpx

from skills.config import LOCAL_LLM_TIMEOUT

GEMINI_URL = os.environ.get("GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "")

OPENROUTER_URL = os.environ.get("OPENROUTER_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "")

OPENWEBUI_URL = os.environ.get("OPENWEBUI_URL", "").rstrip("/")
OPENWEBUI_API_KEY = os.environ.get("OPENWEBUI_API_KEY", "")
OPENWEBUI_MODEL = os.environ.get("OPENWEBUI_MODEL", "")


def _config():
    return {
        # Self-hosted, typically free -- auto-detect a model is a reasonable
        # default the same way it was for LM Studio/MLX before.
        "openwebui": {
            "url": OPENWEBUI_URL,
            "api_key": OPENWEBUI_API_KEY,
            "model": OPENWEBUI_MODEL,
            "requires_key": False,
        },
        # Hosted, multi-model, real per-token cost -- no sensible "first
        # model" default, so these two require an explicit model id.
        "gemini": {
            "url": GEMINI_URL,
            "api_key": GEMINI_API_KEY,
            "model": GEMINI_MODEL,
            "requires_key": True,
        },
        "openrouter": {
            "url": OPENROUTER_URL,
            "api_key": OPENROUTER_API_KEY,
            "model": OPENROUTER_MODEL,
            "requires_key": True,
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


async def _call_backend(name: str, cfg: dict, prompt: str, system: str, max_tokens: int, temperature: float) -> str:
    if not cfg["url"]:
        raise RuntimeError(f"{name.upper()}_URL is not set")
    if cfg["requires_key"] and not cfg["api_key"]:
        raise RuntimeError(f"{name.upper()}_API_KEY is not set")

    headers = _headers(cfg["api_key"])
    async with httpx.AsyncClient(timeout=LOCAL_LLM_TIMEOUT) as client:
        if cfg["requires_key"] and not cfg["model"]:
            raise RuntimeError(
                f"{name.upper()}_MODEL is not set -- {name} hosts many models with real "
                "per-token cost and no sensible default, pick one from its model list and set it"
            )
        model = await _resolve_model(client, cfg["url"], headers, cfg["model"])
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
    """Ask an LLM via an OpenAI-compatible API: your own self-hosted Open
    WebUI instance, Google Gemini, or OpenRouter.

    backend: "auto" (tries openwebui first since it's typically self-hosted
    and free, then gemini, then openrouter), or name one directly:
    "openwebui", "gemini", "openrouter".

    Gemini and OpenRouter need an API key (GEMINI_API_KEY / OPENROUTER_API_KEY)
    and an explicit model id (GEMINI_MODEL / OPENROUTER_MODEL) -- both host
    many models with real per-token cost, so there's no sensible auto-picked
    default; pick one from the provider's own model list and set it. Open
    WebUI (OPENWEBUI_URL, pointed at your own instance) auto-detects the
    first available model if OPENWEBUI_MODEL isn't set.
    """
    cfg = _config()
    order = {
        "auto": ["openwebui", "gemini", "openrouter"],
        "openwebui": ["openwebui"],
        "gemini": ["gemini"],
        "openrouter": ["openrouter"],
    }.get(backend, ["openwebui", "gemini", "openrouter"])

    errors = []
    for name in order:
        try:
            return await _call_backend(name, cfg[name], prompt, system, max_tokens, temperature)
        except Exception as e:
            errors.append(f"{name}: {e}")

    return "error: no backend reachable/configured.\n" + "\n".join(errors)


def register(mcp):
    mcp.tool()(ask_local_llm)
