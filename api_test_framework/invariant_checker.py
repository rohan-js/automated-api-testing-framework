from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class InvariantResult:
    name: str
    passed: bool
    message: str


class InvariantChecker:
    def check_balance_non_negative(self, state_after: Dict[str, float]) -> InvariantResult:
        negatives = {account: balance for account, balance in state_after.items() if balance < 0}
        if negatives:
            details = ", ".join(f"{acct}={bal:.2f}" for acct, bal in sorted(negatives.items()))
            return InvariantResult(
                name="balance_non_negative",
                passed=False,
                message=f"Negative balances detected: {details}",
            )
        return InvariantResult(
            name="balance_non_negative",
            passed=True,
            message="All account balances are non-negative",
        )

    def check_money_conserved(
        self,
        state_before: Dict[str, float],
        state_after: Dict[str, float],
        tolerance: float = 1e-9,
    ) -> InvariantResult:
        total_before = sum(state_before.values())
        total_after = sum(state_after.values())
        delta = total_after - total_before
        passed = abs(delta) <= tolerance

        if passed:
            return InvariantResult(
                name="money_conserved",
                passed=True,
                message=(
                    f"Total money conserved (before={total_before:.2f}, after={total_after:.2f})"
                ),
            )

        return InvariantResult(
            name="money_conserved",
            passed=False,
            message=(
                f"Money drift detected (before={total_before:.2f}, "
                f"after={total_after:.2f}, delta={delta:.2f})"
            ),
        )

    def check_idempotent(
        self,
        state_after_first: Dict[str, float],
        state_after_retries: Dict[str, float],
        tolerance: float = 1e-9,
    ) -> InvariantResult:
        changed: List[str] = []
        all_accounts = sorted(set(state_after_first) | set(state_after_retries))
        for account in all_accounts:
            first = state_after_first.get(account, 0.0)
            retry = state_after_retries.get(account, 0.0)
            if abs(first - retry) > tolerance:
                changed.append(f"{account}: {first:.2f} -> {retry:.2f}")

        if changed:
            return InvariantResult(
                name="idempotent",
                passed=False,
                message="State changed across retries: " + "; ".join(changed),
            )
        return InvariantResult(
            name="idempotent",
            passed=True,
            message="Replayed request produced identical final state",
        )
