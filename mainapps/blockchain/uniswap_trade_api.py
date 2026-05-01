from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


DEFAULT_UNISWAP_TRADE_API_BASE_URL = "https://trade-api.gateway.uniswap.org/v1"


@dataclass
class UniswapTradeAPIError(Exception):
    message: str
    status_code: int = 500
    payload: dict[str, Any] | list[Any] | None = None

    def __str__(self) -> str:
        return self.message


def _get_api_key() -> str:
    api_key = getattr(settings, "UNISWAP_API_KEY", None)
    if not api_key:
        raise UniswapTradeAPIError(
            message="Uniswap API key is not configured on the server.",
            status_code=500,
        )
    return api_key


def _get_base_url() -> str:
    return (
        getattr(settings, "UNISWAP_TRADE_API_BASE_URL", None)
        or DEFAULT_UNISWAP_TRADE_API_BASE_URL
    ).rstrip("/")


def _get_timeout_seconds() -> int:
    timeout_value = getattr(settings, "UNISWAP_API_TIMEOUT_SECONDS", 30)
    try:
        return int(timeout_value)
    except (TypeError, ValueError):
        return 30


def _extract_error_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return fallback


def call_uniswap_trade_api(
    *,
    method: str,
    path: str,
    params: Any = None,
    json_body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    url = f"{_get_base_url()}/{path.lstrip('/')}"
    headers = {
        "x-api-key": _get_api_key(),
        "Accept": "application/json",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)

    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            headers=headers,
            timeout=_get_timeout_seconds(),
        )
    except requests.RequestException as exc:
        logger.exception("Uniswap Trade API request failed for %s %s", method.upper(), url)
        raise UniswapTradeAPIError(
            message="Unable to reach Uniswap right now.",
            status_code=502,
        ) from exc

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if not response.ok:
        fallback = f"Uniswap request failed with status {response.status_code}."
        raise UniswapTradeAPIError(
            message=_extract_error_message(payload, fallback),
            status_code=response.status_code,
            payload=payload if isinstance(payload, (dict, list)) else None,
        )

    return payload
