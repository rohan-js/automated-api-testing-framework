from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from api_test_framework.config_loader import EndpointSpec
from api_test_framework.invariant_checker import InvariantChecker, InvariantResult
from api_test_framework.request_engine import RequestEngine, RequestResult
from api_test_framework.state_tracker import StateTracker


@dataclass
class RetrySimulationResult:
    endpoint_name: str
    state_before: Dict[str, float]
    state_after_first: Dict[str, float]
    state_after_retries: Dict[str, float]
    request_results: List[RequestResult] = field(default_factory=list)
    invariants: List[InvariantResult] = field(default_factory=list)
    idempotency_key: str = ""


class RetrySimulator:
    def __init__(
        self,
        request_engine: RequestEngine,
        state_tracker: StateTracker,
        invariant_checker: InvariantChecker,
    ) -> None:
        self.request_engine = request_engine
        self.state_tracker = state_tracker
        self.invariant_checker = invariant_checker

    def simulate(
        self,
        endpoint: EndpointSpec,
        payload: Dict[str, Any],
        *,
        retry_count: int = 3,
        idempotency_key: str = "retry-simulation-key",
        headers: Optional[Dict[str, str]] = None,
    ) -> RetrySimulationResult:
        if retry_count < 2:
            retry_count = 2

        merged_headers: Dict[str, str] = {}
        if headers:
            merged_headers.update(headers)
        merged_headers["Idempotency-Key"] = idempotency_key

        state_before = self.state_tracker.capture_state()

        request_results: List[RequestResult] = []

        first_result = self.request_engine.send_endpoint(endpoint, payload, headers=merged_headers)
        request_results.append(first_result)

        state_after_first = self.state_tracker.capture_state()

        for _ in range(retry_count - 1):
            request_results.append(
                self.request_engine.send_endpoint(endpoint, payload, headers=merged_headers)
            )

        state_after_retries = self.state_tracker.capture_state()

        invariants = [
            self.invariant_checker.check_idempotent(state_after_first, state_after_retries),
            self.invariant_checker.check_money_conserved(state_before, state_after_retries),
            self.invariant_checker.check_balance_non_negative(state_after_retries),
        ]

        return RetrySimulationResult(
            endpoint_name=endpoint.name,
            state_before=state_before,
            state_after_first=state_after_first,
            state_after_retries=state_after_retries,
            request_results=request_results,
            invariants=invariants,
            idempotency_key=idempotency_key,
        )
