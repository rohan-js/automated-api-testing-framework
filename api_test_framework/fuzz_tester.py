from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from api_test_framework.config_loader import EndpointSpec
from api_test_framework.invariant_checker import InvariantChecker
from api_test_framework.request_engine import RequestEngine, RequestResult
from api_test_framework.state_tracker import StateTracker


@dataclass
class FuzzCaseResult:
    case_name: str
    payload: Dict[str, Any]
    request_result: RequestResult
    state_changed: bool
    passed: bool
    message: str


class FuzzTester:
    def __init__(
        self,
        request_engine: RequestEngine,
        state_tracker: StateTracker,
        invariant_checker: InvariantChecker,
    ) -> None:
        self.request_engine = request_engine
        self.state_tracker = state_tracker
        self.invariant_checker = invariant_checker

    def generate_cases(self, seed_payload: Dict[str, Any]) -> List[tuple[str, Dict[str, Any]]]:
        base = dict(seed_payload)
        amount = float(base.get("amount", 100))

        cases: List[tuple[str, Dict[str, Any]]] = []

        neg = dict(base)
        neg["amount"] = -abs(amount)
        cases.append(("negative_amount", neg))

        huge = dict(base)
        huge["amount"] = 99999999999
        cases.append(("huge_amount", huge))

        missing_from = dict(base)
        missing_from.pop("from", None)
        cases.append(("missing_from", missing_from))

        missing_amount = dict(base)
        missing_amount.pop("amount", None)
        cases.append(("missing_amount", missing_amount))

        wrong_type_amount = dict(base)
        wrong_type_amount["amount"] = "abc"
        cases.append(("wrong_type_amount", wrong_type_amount))

        wrong_type_from = dict(base)
        wrong_type_from["from"] = 12345
        cases.append(("wrong_type_from", wrong_type_from))

        boundary_zero = dict(base)
        boundary_zero["amount"] = 0
        cases.append(("boundary_zero", boundary_zero))

        boundary_fraction = dict(base)
        boundary_fraction["amount"] = 0.001
        cases.append(("boundary_fraction", boundary_fraction))

        return cases

    def run(
        self,
        endpoint: EndpointSpec,
        seed_payload: Dict[str, Any],
        before_case_hook: Optional[Callable[[], None]] = None,
    ) -> List[FuzzCaseResult]:
        results: List[FuzzCaseResult] = []

        for case_name, payload in self.generate_cases(seed_payload):
            if before_case_hook is not None:
                before_case_hook()

            state_before = self.state_tracker.capture_state()
            req_result = self.request_engine.send_endpoint(endpoint, payload)
            state_after = self.state_tracker.capture_state()

            state_changed = state_before != state_after
            non_negative = self.invariant_checker.check_balance_non_negative(state_after).passed

            server_error = req_result.error is not None or req_result.status_code >= 500
            rejected = 400 <= req_result.status_code < 500

            if server_error:
                passed = False
                message = (
                    f"Server error for case `{case_name}` "
                    f"(status={req_result.status_code}, error={req_result.error})"
                )
            elif rejected:
                passed = (not state_changed) and non_negative
                message = (
                    f"Rejected invalid input with status {req_result.status_code}; "
                    f"state_changed={state_changed}"
                )
            else:
                # Graceful handling is accepted if invariants still hold.
                passed = non_negative
                message = (
                    f"Handled input without server error (status={req_result.status_code}); "
                    f"state_changed={state_changed}"
                )

            results.append(
                FuzzCaseResult(
                    case_name=case_name,
                    payload=payload,
                    request_result=req_result,
                    state_changed=state_changed,
                    passed=passed,
                    message=message,
                )
            )

        return results
