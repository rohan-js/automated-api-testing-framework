from __future__ import annotations

from typing import Any, Dict, List

from api_test_framework.config_loader import EndpointSpec, TestSpec


class TestGenerator:
    def generate_valid_cases(self, endpoint: EndpointSpec) -> List[Dict[str, Any]]:
        if endpoint.valid_cases:
            return endpoint.valid_cases

        if endpoint.method == "GET":
            return [{}]

        body = dict(endpoint.body)
        if not body:
            return [{}]

        generated: List[Dict[str, Any]] = [body]

        # Generate a few deterministic edge values for amount-driven payloads.
        if "amount" in body:
            amount = float(body["amount"])
            for candidate in [max(0.01, round(amount / 10, 3)), round(amount * 10, 3), 1.0]:
                clone = dict(body)
                clone["amount"] = candidate
                generated.append(clone)

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for payload in generated:
            marker = tuple(sorted(payload.items()))
            if marker not in seen:
                deduped.append(payload)
                seen.add(marker)

        return deduped

    def generate_stateful_sequence(self, spec: TestSpec) -> List[Dict[str, Any]]:
        if spec.stateful_sequence:
            return spec.stateful_sequence

        sequence: List[Dict[str, Any]] = []
        if "reset" in spec.endpoints:
            sequence.append({"endpoint": "reset", "body": {}})

        if "deposit" in spec.endpoints:
            sequence.append({"endpoint": "deposit", "body": {"account": "A", "amount": 500}})

        if "transfer" in spec.endpoints:
            sequence.extend(
                [
                    {"endpoint": "transfer", "body": {"from": "A", "to": "B", "amount": 100}},
                    {
                        "endpoint": "transfer",
                        "body": {"from": "A", "to": "B", "amount": 100},
                        "headers": {"Idempotency-Key": "stateful-retry-1"},
                    },
                    {
                        "endpoint": "transfer",
                        "body": {"from": "A", "to": "B", "amount": 100},
                        "headers": {"Idempotency-Key": "stateful-retry-1"},
                    },
                    {"endpoint": "transfer", "body": {"from": "B", "to": "A", "amount": 50}},
                ]
            )

        return sequence
