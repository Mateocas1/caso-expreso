"""Minimal HTTP client for the Expreso Andino API (standard library only)."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from http.client import HTTPException
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})


class ApiError(Exception):
    pass


class AuthenticationError(ApiError):
    pass


class ApiUnavailable(ApiError):
    pass


@dataclass(frozen=True)
class ApiResponse:
    status: int
    body: dict
    attempts: int


class ExpresoClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        max_attempts: int = 4,
        backoff_seconds: float = 0.5,
        timeout_seconds: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep

    def list_provinces(self) -> list[str]:
        return self._get_ok("/v1/provinces")["provinces"]

    def create_shipment(self, shipment: dict) -> ApiResponse:
        return self._request("POST", "/v1/shipments", shipment)

    def find_shipments(self, external_ref: str) -> list[dict]:
        return self._get_ok("/v1/shipments?" + urlencode({"external_ref": external_ref}))["items"]

    def get_shipment(self, tracking_id: str) -> dict:
        return self._get_ok("/v1/shipments/" + quote(tracking_id))

    def _get_ok(self, path: str) -> dict:
        response = self._request("GET", path)
        if response.status != 200:
            raise ApiError(f"GET {path} respondió {response.status}: {response.body}")
        return response.body

    def _request(self, method: str, path: str, payload: dict | None = None) -> ApiResponse:
        """Retries transient failures with exponential backoff.

        Retrying a POST is safe because the API rejects a repeated external_ref
        with 409 instead of creating a second shipment.
        """
        for attempt in range(1, self._max_attempts + 1):
            is_last_attempt = attempt == self._max_attempts
            try:
                status, body = self._send(method, path, payload)
            except (OSError, HTTPException) as error:
                if is_last_attempt:
                    message = f"sin conexión con la API tras {attempt} intentos: {error}"
                    raise ApiUnavailable(message) from error
            else:
                if status == 401:
                    raise AuthenticationError("la API rechazó la API key (401)")
                if status not in TRANSIENT_STATUSES or is_last_attempt:
                    return ApiResponse(status, body, attempt)
            self._sleep(self._backoff_seconds * 2 ** (attempt - 1))
        raise AssertionError("unreachable: the last attempt always returns or raises")

    def _send(self, method: str, path: str, payload: dict | None) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self._base_url + path, data=data, method=method, headers=self._headers)
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                return response.status, _read_json(response.read())
        except HTTPError as error:
            return error.code, _read_json(error.read())


def _read_json(raw: bytes) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {"error": raw.decode("utf-8", errors="replace")[:200]}
