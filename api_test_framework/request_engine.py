from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from api_test_framework.config_loader import EndpointSpec


@dataclass
class RequestResult:
    endpoint_name: str
    method: str
    url: str
    path: str
    status_code: int
    body: Any
    latency_ms: float
    error: Optional[str] = None


class RequestEngine:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        path: str,
        *,
        endpoint_name: str = "",
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> RequestResult:
        url = f"{self.base_url}{path}"
        started = time.perf_counter()

        try:
            response = requests.request(
                method=method,
                url=url,
                json=json_body,
                params=params,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            body = _decode_response_body(response)
            return RequestResult(
                endpoint_name=endpoint_name,
                method=method.upper(),
                url=url,
                path=path,
                status_code=response.status_code,
                body=body,
                latency_ms=latency_ms,
            )
        except requests.RequestException as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            return RequestResult(
                endpoint_name=endpoint_name,
                method=method.upper(),
                url=url,
                path=path,
                status_code=0,
                body=None,
                latency_ms=latency_ms,
                error=str(exc),
            )

    def send_endpoint(
        self,
        endpoint: EndpointSpec,
        payload: Optional[Dict[str, Any]] = None,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> RequestResult:
        request_body = payload if payload is not None else endpoint.body
        if endpoint.method == "GET":
            request_body = None

        return self.request(
            endpoint.method,
            endpoint.path,
            endpoint_name=endpoint.name,
            json_body=request_body,
            headers=headers,
            params=params,
        )



def _decode_response_body(response: requests.Response) -> Any:
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type.lower():
        try:
            return response.json()
        except ValueError:
            return response.text
    return response.text
