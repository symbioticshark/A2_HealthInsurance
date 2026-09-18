"""No-inference OpenRouter API-key connectivity check."""
from dataclasses import dataclass
from typing import Optional

from config import config
from backend import live_backend


@dataclass(frozen=True)
class ApiCheckResult:
    ok: bool
    status: str
    message: str
    key_source: str
    details: Optional[dict] = None


def check_api_connection(api_key=None, timeout=None):
    """Validate a key through GET /key; this never starts a model completion."""
    import requests

    configured_key, source = live_backend.get_api_key_with_source()
    key = (api_key if api_key is not None else configured_key).strip()
    if not key:
        return ApiCheckResult(False, "missing_key", "No API key is configured.", source)
    timeout = timeout or (
        config.HTTP_CONNECT_TIMEOUT_SECONDS,
        config.HTTP_READ_TIMEOUT_SECONDS,
    )
    try:
        response = requests.get(
            f"{config.BASE_URL}/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
        )
    except requests.Timeout:
        return ApiCheckResult(False, "timeout", "The API check timed out.", source)
    except requests.ConnectionError as exc:
        safe = live_backend.sanitize_error_text(exc)
        return ApiCheckResult(False, "connection_error", f"Could not reach OpenRouter: {safe}", source)
    except requests.RequestException as exc:
        safe = live_backend.sanitize_error_text(exc)
        return ApiCheckResult(False, "request_error", f"API check failed: {safe}", source)

    if response.ok:
        try:
            payload = response.json() if response.content else {}
        except (TypeError, ValueError):
            return ApiCheckResult(
                False, "invalid_response", "OpenRouter returned an unreadable response.", source
            )
        details = payload.get("data", {}) if isinstance(payload, dict) else {}
        return ApiCheckResult(True, "ok", "API key and connection are ready.", source, details)

    messages = {
        401: "The API key is invalid or expired.",
        403: "The API key is not permitted to use this endpoint.",
        429: "OpenRouter rate-limited the connectivity check. Try again shortly.",
    }
    message = messages.get(response.status_code)
    if not message:
        message = f"OpenRouter returned HTTP {response.status_code}."
    return ApiCheckResult(False, f"http_{response.status_code}", message, source)
