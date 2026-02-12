from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


_ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE"}


@dataclass
class EndpointSpec:
    name: str
    method: str
    path: str
    body: Dict[str, Any] = field(default_factory=dict)
    expect_status: int = 200
    valid_cases: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TestSpec:
    base_url: str
    endpoints: Dict[str, EndpointSpec]
    timeout_seconds: float = 5.0
    response_sla_ms: int = 200
    invariants: List[str] = field(
        default_factory=lambda: ["balance_non_negative", "money_conserved", "idempotent"]
    )
    retry_count: int = 3
    retry_endpoint: str = "transfer"
    retry_body: Dict[str, Any] = field(default_factory=dict)
    retry_idempotency_key: str = "retry-simulation-key"
    fuzz_enabled: bool = True
    fuzz_endpoint: str = "transfer"
    stateful_sequence: List[Dict[str, Any]] = field(default_factory=list)


class SpecValidationError(ValueError):
    pass


def load_test_spec(path: str | Path) -> TestSpec:
    spec_path = Path(path)
    if not spec_path.exists():
        raise SpecValidationError(f"Spec file not found: {spec_path}")

    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SpecValidationError("Spec root must be a YAML mapping")

    base_url = raw.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        raise SpecValidationError("`base_url` is required and must be a non-empty string")

    endpoints_raw = raw.get("endpoints")
    if not isinstance(endpoints_raw, dict) or not endpoints_raw:
        raise SpecValidationError("`endpoints` is required and must be a non-empty mapping")

    endpoints: Dict[str, EndpointSpec] = {}
    for name, conf in endpoints_raw.items():
        endpoints[name] = _parse_endpoint(name, conf)

    invariants = raw.get("invariants", ["balance_non_negative", "money_conserved", "idempotent"])
    if not isinstance(invariants, list) or not all(isinstance(i, str) for i in invariants):
        raise SpecValidationError("`invariants` must be a list of strings")

    stateful_sequence = raw.get("stateful_sequence", [])
    if not isinstance(stateful_sequence, list):
        raise SpecValidationError("`stateful_sequence` must be a list")
    for idx, step in enumerate(stateful_sequence):
        if not isinstance(step, dict):
            raise SpecValidationError(f"stateful_sequence[{idx}] must be a mapping")
        endpoint_name = step.get("endpoint")
        if not isinstance(endpoint_name, str) or endpoint_name not in endpoints:
            raise SpecValidationError(
                f"stateful_sequence[{idx}].endpoint must reference a known endpoint"
            )

    return TestSpec(
        base_url=base_url.rstrip("/"),
        endpoints=endpoints,
        timeout_seconds=float(raw.get("timeout_seconds", 5.0)),
        response_sla_ms=int(raw.get("response_sla_ms", 200)),
        invariants=invariants,
        retry_count=int(raw.get("retry_count", 3)),
        retry_endpoint=str(raw.get("retry_endpoint", "transfer")),
        retry_body=dict(raw.get("retry_body", {})),
        retry_idempotency_key=str(raw.get("retry_idempotency_key", "retry-simulation-key")),
        fuzz_enabled=bool(raw.get("fuzz_enabled", True)),
        fuzz_endpoint=str(raw.get("fuzz_endpoint", "transfer")),
        stateful_sequence=stateful_sequence,
    )


def _parse_endpoint(name: str, conf: Any) -> EndpointSpec:
    if not isinstance(conf, dict):
        raise SpecValidationError(f"Endpoint `{name}` must be a mapping")

    method = conf.get("method")
    path = conf.get("path")

    if not isinstance(method, str):
        raise SpecValidationError(f"Endpoint `{name}` is missing string `method`")
    if not isinstance(path, str):
        raise SpecValidationError(f"Endpoint `{name}` is missing string `path`")

    method = method.upper()
    if method not in _ALLOWED_METHODS:
        raise SpecValidationError(
            f"Endpoint `{name}` has unsupported method `{method}`. "
            f"Allowed: {', '.join(sorted(_ALLOWED_METHODS))}"
        )
    if not path.startswith("/"):
        raise SpecValidationError(f"Endpoint `{name}` path must start with '/'")

    body = conf.get("body", {})
    if not isinstance(body, dict):
        raise SpecValidationError(f"Endpoint `{name}` body must be a mapping when provided")

    valid_cases = conf.get("valid_cases", [])
    if not isinstance(valid_cases, list) or not all(isinstance(case, dict) for case in valid_cases):
        raise SpecValidationError(f"Endpoint `{name}` valid_cases must be a list of mappings")

    expect_status = conf.get("expect_status", 200)
    if not isinstance(expect_status, int):
        raise SpecValidationError(f"Endpoint `{name}` expect_status must be an integer")

    return EndpointSpec(
        name=name,
        method=method,
        path=path,
        body=body,
        expect_status=expect_status,
        valid_cases=valid_cases,
    )
