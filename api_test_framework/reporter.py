from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:
    from colorama import Fore, Style, init
except ImportError:  # pragma: no cover - fallback for minimal environments
    class _ColorStub:
        RED = ""
        GREEN = ""
        RESET_ALL = ""

    Fore = _ColorStub()
    Style = _ColorStub()

    def init(*_args, **_kwargs) -> None:
        return None

from api_test_framework.fuzz_tester import FuzzCaseResult
from api_test_framework.invariant_checker import InvariantResult
from api_test_framework.request_engine import RequestResult


@dataclass
class ReportEntry:
    phase: str
    name: str
    passed: bool
    message: str


class Reporter:
    def __init__(self, use_color: bool = True) -> None:
        init(autoreset=True)
        self.use_color = use_color
        self.entries: List[ReportEntry] = []

    def add_request(self, phase: str, result: RequestResult, sla_ms: Optional[int] = None) -> None:
        no_error = result.error is None
        not_server_error = result.status_code < 500 if result.status_code else False
        within_sla = True if sla_ms is None else result.latency_ms <= sla_ms
        passed = no_error and not_server_error and within_sla

        status_display = result.status_code if result.status_code else "ERR"
        message = f"HTTP {status_display}, latency={result.latency_ms:.1f}ms"
        if result.error:
            message += f", error={result.error}"
        if sla_ms is not None:
            message += f", SLA<{sla_ms}ms"

        self.entries.append(
            ReportEntry(
                phase=phase,
                name=f"Request {result.method} {result.path}",
                passed=passed,
                message=message,
            )
        )

    def add_invariant(self, phase: str, invariant: InvariantResult) -> None:
        self.entries.append(
            ReportEntry(
                phase=phase,
                name=f"Invariant {invariant.name}",
                passed=invariant.passed,
                message=invariant.message,
            )
        )

    def add_fuzz_case(self, phase: str, fuzz_result: FuzzCaseResult) -> None:
        self.entries.append(
            ReportEntry(
                phase=phase,
                name=f"Fuzz {fuzz_result.case_name}",
                passed=fuzz_result.passed,
                message=fuzz_result.message,
            )
        )

    def add_custom(self, phase: str, name: str, passed: bool, message: str) -> None:
        self.entries.append(ReportEntry(phase=phase, name=name, passed=passed, message=message))

    @property
    def has_failures(self) -> bool:
        return any(not entry.passed for entry in self.entries)

    def render(self) -> str:
        lines = ["========== TEST REPORT =========="]

        for entry in self.entries:
            marker = "[PASS]" if entry.passed else "[FAIL]"
            if self.use_color:
                color = Fore.GREEN if entry.passed else Fore.RED
                marker = f"{color}{marker}{Style.RESET_ALL}"
            lines.append(f"{marker} {entry.phase}: {entry.name} - {entry.message}")

        passed_count = sum(1 for entry in self.entries if entry.passed)
        failed_count = len(self.entries) - passed_count
        lines.append("==================================")
        lines.append(f"Summary: passed={passed_count}, failed={failed_count}, total={len(self.entries)}")
        return "\n".join(lines)

    def print(self) -> None:
        print(self.render())

    def write(self, path: str | Path) -> None:
        output_path = Path(path)
        output_path.write_text(self.render(), encoding="utf-8")
