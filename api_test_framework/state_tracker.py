from __future__ import annotations

from typing import Dict

from api_test_framework.request_engine import RequestEngine


class StateTracker:
    def __init__(self, request_engine: RequestEngine, balance_path: str = "/balance") -> None:
        self.request_engine = request_engine
        self.balance_path = balance_path

    def capture_state(self) -> Dict[str, float]:
        result = self.request_engine.request("GET", self.balance_path, endpoint_name="balance")
        if result.error is not None:
            raise RuntimeError(f"Could not capture state: {result.error}")
        if result.status_code != 200:
            raise RuntimeError(
                f"Could not capture state: HTTP {result.status_code} returned by {self.balance_path}"
            )
        if not isinstance(result.body, dict):
            raise RuntimeError("Could not capture state: /balance did not return a JSON object")

        accounts = result.body.get("accounts", result.body)
        if not isinstance(accounts, dict):
            raise RuntimeError("Could not capture state: accounts payload is not a mapping")

        snapshot: Dict[str, float] = {}
        for account, balance in accounts.items():
            snapshot[str(account)] = float(balance)
        return snapshot

    @staticmethod
    def total_balance(state: Dict[str, float]) -> float:
        return float(sum(state.values()))
