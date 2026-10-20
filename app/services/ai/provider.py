"""Step 4 - AI request: optional call to an external model.

Configured only through environment variables (see ``.env.example``). When no
API key is set the assistant never reaches this module.
"""
import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com"
OPENAI_URL = "https://api.openai.com/v1"


class ProviderError(Exception):
    """The AI provider could not be reached or returned something unusable."""


def is_configured(config) -> bool:
    return bool(config.get("AI_API_KEY"))


def _post(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Log the status only. Never log headers (they contain the API key).
        log.warning("AI provider returned HTTP %s", exc.code)
        raise ProviderError(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        log.warning("AI provider request failed: %s", type(exc).__name__)
        raise ProviderError(type(exc).__name__) from None


def ask_model(system_prompt: str, user_prompt: str, config) -> str:
    """Send one grounded question to the configured provider; return its text."""
    provider = config.get("AI_PROVIDER", "anthropic")
    key = config["AI_API_KEY"]
    model = config.get("AI_MODEL")
    timeout = config.get("AI_TIMEOUT_SECONDS", 20)
    base = (config.get("AI_BASE_URL") or "").rstrip("/")

    if provider == "anthropic":
        data = _post(
            f"{base or ANTHROPIC_URL}/v1/messages",
            {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            {
                "model": model,
                "max_tokens": 400,
                "temperature": 0,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout,
        )
        blocks = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        text = "".join(blocks).strip()
    elif provider == "openai":
        data = _post(
            f"{base or OPENAI_URL}/chat/completions",
            {"Authorization": f"Bearer {key}", "content-type": "application/json"},
            {
                "model": model,
                "temperature": 0,
                "max_tokens": 400,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout,
        )
        try:
            text = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError):
            raise ProviderError("unexpected response shape") from None
    else:
        raise ProviderError(f"unknown AI_PROVIDER '{provider}'")

    if not text:
        raise ProviderError("empty response")
    return text
