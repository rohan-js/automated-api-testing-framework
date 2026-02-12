from __future__ import annotations

import argparse
import sys

from api_test_framework.config_loader import SpecValidationError, load_test_spec
from api_test_framework.fuzz_tester import FuzzTester
from api_test_framework.invariant_checker import InvariantChecker
from api_test_framework.reporter import Reporter
from api_test_framework.request_engine import RequestEngine
from api_test_framework.retry_simulator import RetrySimulator
from api_test_framework.state_tracker import StateTracker
from api_test_framework.test_generator import TestGenerator


def run(spec_path: str, report_file: str | None = None) -> int:
    try:
        spec = load_test_spec(spec_path)
    except SpecValidationError as exc:
        print(f"Spec validation failed: {exc}")
        return 2

    request_engine = RequestEngine(spec.base_url, timeout_seconds=spec.timeout_seconds)
    state_tracker = StateTracker(request_engine)
    invariant_checker = InvariantChecker()
    test_generator = TestGenerator()
    retry_simulator = RetrySimulator(request_engine, state_tracker, invariant_checker)
    fuzz_tester = FuzzTester(request_engine, state_tracker, invariant_checker)
    reporter = Reporter(use_color=True)

    # Setup/reset target state first.
    reset_endpoint = spec.endpoints.get("reset")
    if reset_endpoint is not None:
        reset_result = request_engine.send_endpoint(reset_endpoint, reset_endpoint.body)
        reporter.add_request("setup", reset_result, sla_ms=spec.response_sla_ms)
        if reset_result.error is not None or reset_result.status_code >= 500:
            reporter.add_custom("setup", "reset_ready", False, "Target reset failed")
            reporter.print()
            return 1

    _run_normal_tests(spec, request_engine, state_tracker, invariant_checker, test_generator, reporter)
    _run_retry_tests(spec, retry_simulator, reporter)
    _run_fuzz_tests(spec, request_engine, fuzz_tester, reporter)
    _run_stateful_tests(spec, request_engine, state_tracker, invariant_checker, test_generator, reporter)

    reporter.print()
    if report_file:
        reporter.write(report_file)

    return 1 if reporter.has_failures else 0


def _run_normal_tests(
    spec,
    request_engine: RequestEngine,
    state_tracker: StateTracker,
    invariant_checker: InvariantChecker,
    test_generator: TestGenerator,
    reporter: Reporter,
) -> None:
    for endpoint in spec.endpoints.values():
        if endpoint.name in {"reset", "balance"}:
            continue

        for payload in test_generator.generate_valid_cases(endpoint):
            state_before = state_tracker.capture_state()
            result = request_engine.send_endpoint(endpoint, payload)
            reporter.add_request("normal", result, sla_ms=spec.response_sla_ms)

            if result.error is not None:
                reporter.add_custom(
                    "normal",
                    f"{endpoint.name}_executed",
                    False,
                    f"Request failed before invariants: {result.error}",
                )
                continue

            state_after = state_tracker.capture_state()
            if "balance_non_negative" in spec.invariants:
                reporter.add_invariant(
                    "normal", invariant_checker.check_balance_non_negative(state_after)
                )

            if endpoint.name == "transfer" and "money_conserved" in spec.invariants:
                reporter.add_invariant(
                    "normal", invariant_checker.check_money_conserved(state_before, state_after)
                )


def _run_retry_tests(spec, retry_simulator: RetrySimulator, reporter: Reporter) -> None:
    endpoint = spec.endpoints.get(spec.retry_endpoint)
    if endpoint is None:
        reporter.add_custom(
            "retry",
            "retry_endpoint_present",
            False,
            f"Configured retry endpoint `{spec.retry_endpoint}` not found",
        )
        return

    payload = spec.retry_body or endpoint.body
    simulation = retry_simulator.simulate(
        endpoint,
        payload,
        retry_count=spec.retry_count,
        idempotency_key=spec.retry_idempotency_key,
    )

    for request_result in simulation.request_results:
        reporter.add_request("retry", request_result, sla_ms=spec.response_sla_ms)
    for invariant in simulation.invariants:
        reporter.add_invariant("retry", invariant)


def _run_fuzz_tests(
    spec,
    request_engine: RequestEngine,
    fuzz_tester: FuzzTester,
    reporter: Reporter,
) -> None:
    if not spec.fuzz_enabled:
        return

    endpoint = spec.endpoints.get(spec.fuzz_endpoint)
    if endpoint is None:
        reporter.add_custom(
            "fuzz",
            "fuzz_endpoint_present",
            False,
            f"Configured fuzz endpoint `{spec.fuzz_endpoint}` not found",
        )
        return

    seed_payload = endpoint.body
    reset_endpoint = spec.endpoints.get("reset")

    def _reset_before_case() -> None:
        if reset_endpoint is None:
            return
        reset_result = request_engine.send_endpoint(reset_endpoint, reset_endpoint.body)
        if reset_result.error is not None or reset_result.status_code >= 500:
            reporter.add_custom(
                "fuzz",
                "fuzz_case_reset",
                False,
                f"Failed to reset before fuzz case: {reset_result.error or reset_result.status_code}",
            )

    for fuzz_result in fuzz_tester.run(
        endpoint,
        seed_payload,
        before_case_hook=_reset_before_case,
    ):
        reporter.add_fuzz_case("fuzz", fuzz_result)


def _run_stateful_tests(
    spec,
    request_engine: RequestEngine,
    state_tracker: StateTracker,
    invariant_checker: InvariantChecker,
    test_generator: TestGenerator,
    reporter: Reporter,
) -> None:
    sequence = test_generator.generate_stateful_sequence(spec)
    if not sequence:
        return

    for step_index, step in enumerate(sequence, start=1):
        endpoint_name = step.get("endpoint")
        endpoint = spec.endpoints.get(endpoint_name)
        if endpoint is None:
            reporter.add_custom(
                "stateful",
                f"step_{step_index}",
                False,
                f"Unknown endpoint `{endpoint_name}`",
            )
            continue

        payload = step.get("body")
        headers = step.get("headers")

        state_before = state_tracker.capture_state()
        result = request_engine.send_endpoint(endpoint, payload, headers=headers)
        reporter.add_request("stateful", result, sla_ms=spec.response_sla_ms)

        if result.error is not None:
            reporter.add_custom(
                "stateful",
                f"step_{step_index}_{endpoint_name}",
                False,
                result.error,
            )
            continue

        state_after = state_tracker.capture_state()
        reporter.add_invariant("stateful", invariant_checker.check_balance_non_negative(state_after))

        if endpoint.name == "transfer":
            reporter.add_invariant(
                "stateful", invariant_checker.check_money_conserved(state_before, state_after)
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated invariant-based API test framework")
    parser.add_argument("spec", help="Path to YAML test spec")
    parser.add_argument("--report-file", help="Optional output path for plain-text report")
    args = parser.parse_args()

    exit_code = run(args.spec, report_file=args.report_file)
    sys.exit(exit_code)
